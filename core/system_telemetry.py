"""Host hardware, container cgroup, memory, CPU, disk, and runtime telemetry for AI3."""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import socket
import sys
from pathlib import Path
from typing import Any

from core.config import get_settings


def _read_first_line(path: str) -> str | None:
    try:
        p = Path(path)
        if p.exists():
            return p.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
    except Exception:
        pass
    return None


def _detect_cpu_model() -> str:
    # 1. Linux /proc/cpuinfo
    try:
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            for line in cpuinfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "model name" in line or "Hardware" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2 and parts[1].strip():
                        return parts[1].strip()
    except Exception:
        pass

    # 2. Windows environment or platform.processor()
    proc = platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "")
    if proc:
        return proc.strip()
    return platform.machine() or "Generic CPU"


def _detect_cgroup_cpu_quota() -> float | None:
    """Return container CPU limit in cores if constrained by cgroup v2 or v1."""
    # cgroup v2: /sys/fs/cgroup/cpu.max -> "<quota> <period>"
    line = _read_first_line("/sys/fs/cgroup/cpu.max")
    if line:
        parts = line.split()
        if len(parts) == 2 and parts[0] != "max":
            try:
                quota = float(parts[0])
                period = float(parts[1])
                if period > 0:
                    return round(quota / period, 2)
            except ValueError:
                pass

    # cgroup v1
    q_line = _read_first_line("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    p_line = _read_first_line("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if q_line and p_line:
        try:
            q = float(q_line)
            p = float(p_line)
            if q > 0 and p > 0:
                return round(q / p, 2)
        except ValueError:
            pass
    return None


def _detect_cgroup_memory() -> tuple[float | None, float | None]:
    """Return (container_limit_mb, container_used_mb) from cgroup v2/v1 if applicable."""
    limit_bytes: int | None = None
    used_bytes: int | None = None

    # cgroup v2
    max_line = _read_first_line("/sys/fs/cgroup/memory.max")
    if max_line and max_line != "max":
        try:
            val = int(max_line)
            if 0 < val < (1 << 50):
                limit_bytes = val
        except ValueError:
            pass

    cur_line = _read_first_line("/sys/fs/cgroup/memory.current")
    if cur_line:
        try:
            used_bytes = int(cur_line)
        except ValueError:
            pass

    # cgroup v1 fallback
    if limit_bytes is None:
        v1_max = _read_first_line("/sys/fs/cgroup/memory/memory.limit_in_bytes")
        if v1_max:
            try:
                val = int(v1_max)
                if 0 < val < (1 << 50):
                    limit_bytes = val
            except ValueError:
                pass
    if used_bytes is None:
        v1_cur = _read_first_line("/sys/fs/cgroup/memory/memory.usage_in_bytes")
        if v1_cur:
            try:
                used_bytes = int(v1_cur)
            except ValueError:
                pass

    limit_mb = round(limit_bytes / (1024 * 1024), 1) if limit_bytes else None
    used_mb = round(used_bytes / (1024 * 1024), 1) if used_bytes else None
    return limit_mb, used_mb


def _detect_host_memory_fallback() -> tuple[float, float, float]:
    """Return (total_gb, used_gb, pct) without psutil using /proc/meminfo or Windows ctypes."""
    # Linux /proc/meminfo
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        info: dict[str, int] = {}
        for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                toks = v.strip().split()
                if toks and toks[0].isdigit():
                    info[k.strip()] = int(toks[0]) * 1024  # kB to bytes
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        if total > 0:
            used = max(0, total - avail)
            return (
                round(total / (1024**3), 2),
                round(used / (1024**3), 2),
                round((used / total) * 100.0, 1),
            )

    # Windows GlobalMemoryStatusEx
    if os.name == "nt":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total = stat.ullTotalPhys
            avail = stat.ullAvailPhys
            used = max(0, total - avail)
            return (
                round(total / (1024**3), 2),
                round(used / (1024**3), 2),
                float(stat.dwMemoryLoad),
            )
        except Exception:
            pass

    return (0.0, 0.0, 0.0)


def _detect_process_rss_mb() -> float:
    """Return current Python process RSS memory in MB."""
    try:
        import psutil

        return round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 1)
    except Exception:
        pass

    # Linux /proc/self/status fallback
    status = Path("/proc/self/status")
    if status.exists():
        for line in status.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("VmRSS:"):
                toks = line.split()
                if len(toks) >= 2 and toks[1].isdigit():
                    return round(int(toks[1]) / 1024.0, 1)
    return 0.0


def _detect_hosting_provider() -> str:
    """Identify whether running on Streamlit Community Cloud, Docker/K8s container, or local host."""
    env = os.environ
    hostname = socket.gethostname()
    if (
        env.get("STREAMLIT_SHARING_MODE")
        or env.get("IS_STREAMLIT_CLOUD")
        or Path("/mount/src").exists()
        or "streamlit" in hostname.lower()
    ):
        return "Streamlit Community Cloud (Container)"
    if Path("/.dockerenv").exists() or env.get("KUBERNETES_SERVICE_HOST"):
        return "Linux Container (Docker / Kubernetes)"
    return f"Local / Dedicated Host ({platform.system()})"


def get_system_telemetry() -> dict[str, Any]:
    """Collect comprehensive CPU, RAM, Container Cgroup, Disk, and Runtime telemetry."""
    logical_cpus = os.cpu_count() or 1
    physical_cpus = logical_cpus
    cpu_usage_pct: float | None = None
    host_total_gb, host_used_gb, host_mem_pct = _detect_host_memory_fallback()

    try:
        import psutil

        physical_cpus = psutil.cpu_count(logical=False) or logical_cpus
        cpu_usage_pct = round(psutil.cpu_percent(interval=0.05), 1)
        vm = psutil.virtual_memory()
        host_total_gb = round(vm.total / (1024**3), 2)
        host_used_gb = round((vm.total - vm.available) / (1024**3), 2)
        host_mem_pct = round(vm.percent, 1)
    except Exception:
        # Fallback to os.getloadavg on Unix if available
        if hasattr(os, "getloadavg"):
            try:
                load1, _, _ = os.getloadavg()
                cpu_usage_pct = round(min(100.0, (load1 / max(1, logical_cpus)) * 100.0), 1)
            except Exception:
                pass

    cgroup_cpu_cores = _detect_cgroup_cpu_quota()
    cgroup_mem_limit_mb, cgroup_mem_used_mb = _detect_cgroup_memory()
    proc_rss_mb = _detect_process_rss_mb()

    # Effective RAM budget for this app instance
    if cgroup_mem_limit_mb and cgroup_mem_limit_mb < (host_total_gb * 1024):
        eff_mem_limit_mb = cgroup_mem_limit_mb
        eff_mem_used_mb = cgroup_mem_used_mb if cgroup_mem_used_mb is not None else proc_rss_mb
        eff_mem_pct = round(min(100.0, (eff_mem_used_mb / max(1.0, eff_mem_limit_mb)) * 100.0), 1)
        mem_scope = "Container Quota"
    else:
        eff_mem_limit_mb = round(host_total_gb * 1024, 1)
        eff_mem_used_mb = round(host_used_gb * 1024, 1)
        eff_mem_pct = host_mem_pct
        mem_scope = "Host RAM"

    # Disk telemetry
    try:
        du = shutil.disk_usage(Path.cwd())
        disk_total_gb = round(du.total / (1024**3), 2)
        disk_used_gb = round(du.used / (1024**3), 2)
        disk_free_gb = round(du.free / (1024**3), 2)
        disk_pct = round((du.used / max(1, du.total)) * 100.0, 1)
    except Exception:
        disk_total_gb = disk_used_gb = disk_free_gb = disk_pct = 0.0

    settings = get_settings()
    db_path = settings.sqlite_db_path
    db_size_kb = round(db_path.stat().st_size / 1024.0, 1) if db_path.exists() else 0.0

    eff_cpus = f"{cgroup_cpu_cores} vCPU (Quota) / {logical_cpus} Host" if cgroup_cpu_cores else f"{logical_cpus} vCPUs ({physical_cpus} Cores)"

    return {
        "hosting_provider": _detect_hosting_provider(),
        "hostname": socket.gethostname(),
        "os_platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python_version": sys.version.split()[0],
        "cpu_model": _detect_cpu_model(),
        "logical_cpus": logical_cpus,
        "physical_cpus": physical_cpus,
        "cgroup_cpu_cores": cgroup_cpu_cores,
        "effective_cpu_label": eff_cpus,
        "cpu_usage_pct": cpu_usage_pct,
        "process_rss_mb": proc_rss_mb,
        "cgroup_mem_limit_mb": cgroup_mem_limit_mb,
        "cgroup_mem_used_mb": cgroup_mem_used_mb,
        "host_total_gb": host_total_gb,
        "host_used_gb": host_used_gb,
        "host_mem_pct": host_mem_pct,
        "effective_mem_used_mb": eff_mem_used_mb,
        "effective_mem_limit_mb": eff_mem_limit_mb,
        "effective_mem_pct": eff_mem_pct,
        "mem_scope": mem_scope,
        "disk_total_gb": disk_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_free_gb": disk_free_gb,
        "disk_pct": disk_pct,
        "sqlite_db_kb": db_size_kb,
    }
