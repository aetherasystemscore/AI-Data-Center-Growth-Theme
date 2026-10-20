"""Shared Streamlit page bootstrapper, compact UI styling, top quick-navigation bar, and live host resource telemetry."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import streamlit as st

from core.config import get_settings
from core.schemas import ScoringProfile
from core.system_telemetry import get_system_telemetry
from data.ingestion import DataIngestionService
from database.repository import AI3Repository

_IN_NAVIGATION_RUNNER: bool = False

NAV_ITEMS: list[tuple[str, str, str, str]] = [
    ("pages/dashboard.py", "1. Dashboard", "📊", "dashboard"),
    ("pages/stock_screener.py", "2. Screener", "🔍", "stock_screener"),
    ("pages/company_research.py", "3. Company", "🏢", "company_research"),
    ("pages/value_alternatives.py", "4. Value Alts", "💎", "value_alternatives"),
    ("pages/etf_analysis.py", "5. ETFs", "📦", "etf_analysis"),
    ("pages/smallcase_analysis.py", "6. Smallcases", "🧩", "smallcase_analysis"),
    ("pages/ipo_tracker.py", "7. IPOs", "🚀", "ipo_tracker"),
    ("pages/circular_electronics.py", "8. Circular", "♻️", "circular_electronics"),
    ("pages/portfolio_builder.py", "9. Portfolio", "📐", "portfolio_builder"),
    ("pages/backtesting.py", "10. Backtest", "📈", "backtesting"),
    ("pages/settings.py", "11. Settings", "⚙️", "settings"),
]


@st.cache_resource
def init_platform() -> tuple[AI3Repository, DataIngestionService]:
    """Initialize SQLite repository and seed/bootstrap data once per server process."""
    repo = AI3Repository()
    ingestion = DataIngestionService(repo=repo)
    ingestion.ensure_bootstrapped()
    return repo, ingestion


def inject_compact_styles() -> None:
    """Inject CSS to make the entire Streamlit view denser, more compact, and easier to scan."""
    st.markdown(
        """
        <style>
        /* Compact main container padding */
        .block-container {
            padding-top: 1.1rem !important;
            padding-bottom: 1.0rem !important;
            padding-left: 1.25rem !important;
            padding-right: 1.25rem !important;
            max-width: 100% !important;
        }
        /* Tighten vertical rhythm between Streamlit blocks */
        div[data-testid="stVerticalBlock"] > div {
            gap: 0.38rem !important;
        }
        /* Compact headings */
        h1 {
            font-size: 1.32rem !important;
            line-height: 1.25 !important;
            margin-top: 0.1rem !important;
            margin-bottom: 0.15rem !important;
            padding-top: 0 !important;
        }
        h2 {
            font-size: 1.06rem !important;
            line-height: 1.25 !important;
            margin-top: 0.25rem !important;
            margin-bottom: 0.15rem !important;
        }
        h3 {
            font-size: 0.94rem !important;
            line-height: 1.25 !important;
            margin-top: 0.2rem !important;
            margin-bottom: 0.1rem !important;
        }
        hr {
            margin-top: 0.35rem !important;
            margin-bottom: 0.35rem !important;
        }
        /* Compact KPI metric cards */
        div[data-testid="stMetric"] {
            background-color: rgba(128, 128, 128, 0.05);
            border: 1px solid rgba(128, 128, 128, 0.18);
            border-radius: 6px;
            padding: 0.32rem 0.55rem !important;
        }
        div[data-testid="stMetricLabel"] p {
            font-size: 0.72rem !important;
            margin-bottom: 0 !important;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.10rem !important;
            line-height: 1.2 !important;
        }
        div[data-testid="stMetricDelta"] {
            font-size: 0.68rem !important;
        }
        /* Compact sidebar navigation items */
        section[data-testid="stSidebar"] .block-container {
            padding-top: 0.75rem !important;
            padding-bottom: 0.75rem !important;
        }
        div[data-testid="stSidebarNav"] ul {
            padding-top: 0.15rem !important;
            padding-bottom: 0.15rem !important;
        }
        div[data-testid="stSidebarNav"] li a {
            padding-top: 0.22rem !important;
            padding-bottom: 0.22rem !important;
            font-size: 0.84rem !important;
        }
        /* Compact top telemetry banner */
        .ai3-telemetry-strip {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 0.45rem;
            padding: 0.32rem 0.65rem;
            border-radius: 6px;
            background: rgba(30, 41, 59, 0.06);
            border: 1px solid rgba(128, 128, 128, 0.22);
            font-size: 0.76rem;
            line-height: 1.3;
            margin-bottom: 0.2rem;
        }
        .ai3-telemetry-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            padding: 0.1rem 0.42rem;
            border-radius: 4px;
            background: rgba(128, 128, 128, 0.10);
            font-weight: 500;
            white-space: nowrap;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_host_specs_table(tel: dict) -> None:
    """Render structured hardware, container cgroup, CPU, RAM, and disk specs."""
    spec_rows = [
        {"Category": "Hosting Environment", "Metric": "Platform / Provider", "Value": tel["hosting_provider"]},
        {"Category": "Hosting Environment", "Metric": "Node Hostname / Pod ID", "Value": tel["hostname"]},
        {"Category": "Hosting Environment", "Metric": "OS & Kernel", "Value": tel["os_platform"]},
        {"Category": "Hosting Environment", "Metric": "Python Runtime", "Value": f"Python {tel['python_version']}"},
        {"Category": "CPU & Compute", "Metric": "Processor Model", "Value": tel["cpu_model"]},
        {"Category": "CPU & Compute", "Metric": "Allocated / Host vCPUs", "Value": tel["effective_cpu_label"]},
        {
            "Category": "CPU & Compute",
            "Metric": "Current CPU Load",
            "Value": f"{tel['cpu_usage_pct']}%" if tel["cpu_usage_pct"] is not None else "Shared / N/A",
        },
        {
            "Category": "Memory (RAM)",
            "Metric": "App Process RSS Memory",
            "Value": f"{tel['process_rss_mb']} MB",
        },
        {
            "Category": "Memory (RAM)",
            "Metric": f"Effective RAM ({tel['mem_scope']})",
            "Value": f"{tel['effective_mem_used_mb']} MB / {tel['effective_mem_limit_mb']} MB ({tel['effective_mem_pct']}%)",
        },
        {
            "Category": "Memory (RAM)",
            "Metric": "Underlying Host Node RAM",
            "Value": f"{tel['host_used_gb']} GB / {tel['host_total_gb']} GB ({tel['host_mem_pct']}%)",
        },
        {
            "Category": "Storage & Database",
            "Metric": "Container / Host Disk",
            "Value": f"{tel['disk_free_gb']} GB free of {tel['disk_total_gb']} GB ({tel['disk_pct']}% used)",
        },
        {
            "Category": "Storage & Database",
            "Metric": "SQLite Database Size",
            "Value": f"{tel['sqlite_db_kb']} KB",
        },
    ]
    st.dataframe(pd.DataFrame(spec_rows), use_container_width=True, hide_index=True)


def render_top_bar() -> None:
    """Render a compact top telemetry bar + quick-jump module navigation strip across all pages."""
    inject_compact_styles()
    tel = get_system_telemetry()
    settings = get_settings()

    cpu_load_str = f" • {tel['cpu_usage_pct']}% load" if tel["cpu_usage_pct"] is not None else ""
    mem_used_gb = round(tel["effective_mem_used_mb"] / 1024.0, 2)
    mem_lim_gb = round(tel["effective_mem_limit_mb"] / 1024.0, 2)

    top_left, top_right = st.columns([5.2, 1.3])
    with top_left:
        st.markdown(
            f"""
            <div class="ai3-telemetry-strip">
                <span><b>⚡ AI3 Terminal</b> &nbsp;|&nbsp; <span class="ai3-telemetry-pill">🖥️ {tel['hosting_provider']}</span></span>
                <span class="ai3-telemetry-pill">⚙️ CPU: {tel['effective_cpu_label']}{cpu_load_str}</span>
                <span class="ai3-telemetry-pill">🧠 RAM: {tel['process_rss_mb']} MB App • {mem_used_gb}/{mem_lim_gb} GB ({tel['effective_mem_pct']}%)</span>
                <span class="ai3-telemetry-pill">💾 Disk: {tel['disk_free_gb']} GB Free</span>
                <span class="ai3-telemetry-pill">🐍 Py {tel['python_version']} • DB {tel['sqlite_db_kb']} KB • {settings.data_mode}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with top_right:
        if hasattr(st, "popover"):
            with st.popover("🖥️ Host CPU/RAM", use_container_width=True):
                st.markdown(f"**{tel['hosting_provider']}**")
                st.caption(f"CPU: `{tel['cpu_model']}`")
                render_host_specs_table(tel)
        else:
            with st.expander("🖥️ Host Specs"):
                render_host_specs_table(tel)

    # Compact 1-click horizontal navigation bar across all 11 modules
    if hasattr(st, "page_link"):
        nav_cols = st.columns(len(NAV_ITEMS))
        for col, (page_path, label, icon, _) in zip(nav_cols, NAV_ITEMS):
            with col:
                try:
                    st.page_link(page_path, label=label, icon=icon, use_container_width=True)
                except Exception:
                    pass


def render_sidebar_controls() -> None:
    """Render compact AI3 sidebar controls, scoring profile selector, and live host CPU/RAM telemetry."""
    settings = get_settings()
    tel = get_system_telemetry()
    with st.sidebar:
        st.markdown("### ⚡ AI3 Intelligence")
        profile_options = [p.value for p in ScoringProfile]
        default_prof_idx = profile_options.index(ScoringProfile.DEFAULT_100PT.value)
        active_profile = st.selectbox(
            "Scoring Profile",
            options=profile_options,
            index=default_prof_idx,
            key="ai3_active_scoring_profile_select",
            help="Adjusts the 6-component weights in the 100-point AI Infrastructure Exposure Model.",
        )
        st.session_state["active_scoring_profile"] = active_profile

        with st.expander("🖥️ Host CPU & RAM Telemetry", expanded=True):
            st.caption(f"**Env:** {tel['hosting_provider']}")
            st.caption(f"**CPU:** {tel['cpu_model'][:38]}")
            st.caption(
                f"**Cores:** {tel['effective_cpu_label']}"
                + (f" ({tel['cpu_usage_pct']}%)" if tel["cpu_usage_pct"] is not None else "")
            )
            st.caption(
                f"**RAM ({tel['mem_scope']}):** {tel['effective_mem_used_mb']:.0f} / {tel['effective_mem_limit_mb']:.0f} MB ({tel['effective_mem_pct']}%)"
            )
            st.progress(min(1.0, max(0.0, tel["effective_mem_pct"] / 100.0)))
            st.caption(
                f"**App Process RSS:** {tel['process_rss_mb']} MB  |  **Host RAM:** {tel['host_total_gb']} GB\n\n"
                f"**Disk Free:** {tel['disk_free_gb']} GB / {tel['disk_total_gb']} GB  |  **OS:** {tel['os_platform']}"
            )

        st.caption(
            f"**Mode:** `{settings.data_mode}` • Missing values kept `N/A` • Research tool only (not SEBI advice)."
        )


def run_standalone_page(render_fn: Callable[[AI3Repository, DataIngestionService], None]) -> None:
    """Execute a page's render(repo, ingestion) function whether invoked via st.navigation or direct /<page> URL."""
    if not _IN_NAVIGATION_RUNNER:
        try:
            st.set_page_config(
                page_title="AI3 | AI Infrastructure Investment Intelligence",
                page_icon="⚡",
                layout="wide",
                initial_sidebar_state="expanded",
            )
        except Exception:
            pass
        render_sidebar_controls()

    render_top_bar()
    repo, ingestion = init_platform()
    render_fn(repo, ingestion)
