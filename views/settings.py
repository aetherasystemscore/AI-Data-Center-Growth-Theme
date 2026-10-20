"""Page 11: Discovery Queue, Automated Refresh Jobs, Host Resource Telemetry & Platform Settings."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_PAGES_DIR = str(Path(__file__).resolve().parent)
if _PAGES_DIR in sys.path:
    sys.path.remove(_PAGES_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd
import streamlit as st

from ai.research_summariser import get_active_ai_provider
from core.config import get_settings
from core.page_bootstrap import render_host_specs_table
from core.security_master import SecurityMasterService
from core.system_telemetry import get_system_telemetry
from data.ingestion import DataIngestionService
from database.repository import AI3Repository
from jobs.discover_ipos import run_discover_ipos
from jobs.discover_new_listings import run_discover_new_listings
from jobs.refresh_financials import run_refresh_financials
from jobs.refresh_prices import run_refresh_prices
from jobs.research_news import run_research_news
from jobs.update_security_master import run_update_security_master


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("⚙️ Discovery Engine, Automated Jobs, Security Master & Host Telemetry")

    settings = get_settings()
    ai_prov = get_active_ai_provider()
    tel = get_system_telemetry()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Host Environment", tel["hosting_provider"].split("(")[0].strip(), tel["os_platform"].split()[0])
    c2.metric(
        "CPU Allocation",
        tel["effective_cpu_label"],
        f"{tel['cpu_usage_pct']}% Load" if tel["cpu_usage_pct"] is not None else tel["cpu_model"][:22],
    )
    c3.metric(
        f"RAM ({tel['mem_scope']})",
        f"{tel['effective_mem_used_mb']:.0f} / {tel['effective_mem_limit_mb']:.0f} MB",
        f"{tel['effective_mem_pct']}% Utilised",
    )
    c4.metric("App Process RSS", f"{tel['process_rss_mb']} MB", f"Host RAM: {tel['host_total_gb']} GB")
    c5.metric("Disk Available", f"{tel['disk_free_gb']} GB Free", f"{tel['disk_pct']}% of {tel['disk_total_gb']} GB")
    c6.metric("Data Mode & DB", settings.data_mode, f"SQLite {tel['sqlite_db_kb']} KB • {ai_prov.provider_name}")

    st.divider()
    with st.expander("🖥️ Detailed Hosting Infrastructure, CPU, RAM & Container Specifications", expanded=True):
        render_host_specs_table(tel)

    st.subheader("1. Automated Discovery & Refresh Jobs")
    st.caption(
        "Execute any of the 6 background discovery and data-validation jobs on demand. Every job logs its execution to `job_runs`."
    )

    jb1, jb2, jb3, jb4, jb5, jb6 = st.columns(6)
    if jb1.button("🔄 Update Security Master", use_container_width=True):
        out = run_update_security_master(repo)
        st.success(out.get("message", str(out)))
    if jb2.button("🆕 Discover New Listings", use_container_width=True):
        out = run_discover_new_listings(repo)
        st.success(out.get("message", str(out)))
    if jb3.button("📑 Discover SEBI IPOs", use_container_width=True):
        out = run_discover_ipos(repo)
        st.success(out.get("message", str(out)))
    if jb4.button("💹 Refresh Prices", use_container_width=True):
        out = run_refresh_prices(repo)
        st.success(out.get("message", str(out)))
    if jb5.button("📊 Refresh Financials", use_container_width=True):
        out = run_refresh_financials(repo)
        st.success(out.get("message", str(out)))
    if jb6.button("📰 Refresh Filing News", use_container_width=True):
        out = run_research_news(repo)
        st.success(out.get("message", str(out)))

    st.divider()
    col_dq, col_sm, col_jr = st.columns([2.2, 1.3, 1.8])
    with col_dq:
        st.subheader("2. Discovery Queue (`CANDIDATE_PENDING_REVIEW`)")
        queue_items = repo.get_discovery_queue()
        if not queue_items:
            if st.button("Populate Discovery Queue via New Listing Scan"):
                run_discover_new_listings(repo)
                queue_items = repo.get_discovery_queue()
        if queue_items:
            st.dataframe(pd.DataFrame(queue_items), use_container_width=True, hide_index=True, height=220)
        else:
            st.caption("Queue empty. Click above or run 'Discover New Listings' to scan.")

    with col_sm:
        st.subheader("3. Ticker Alias Map")
        sm = SecurityMasterService()
        alias_df = pd.DataFrame(
            [{"Legacy Ticker": k, "Canonical Symbol": v} for k, v in sm.KNOWN_ALIASES.items()]
        )
        st.dataframe(alias_df, use_container_width=True, hide_index=True, height=220)

    with col_jr:
        st.subheader("4. Job Execution Audit Log")
        runs = repo.get_recent_job_runs(limit=15)
        if runs:
            st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True, height=220)
        else:
            st.caption("No job runs recorded yet. Click any job button above to execute and log a run.")


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
