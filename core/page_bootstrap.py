"""Shared Streamlit bootstrapper, compact UI styling, top-left navigation, and live host CPU/RAM telemetry."""

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

# Canonical ordered modules: (slug, sidebar_label, short_top_label)
MODULES: list[tuple[str, str, str]] = [
    ("dashboard", "📊 1. Executive Dashboard", "📊 1. Dashboard"),
    ("stock_screener", "🔍 2. AI Value-Chain Screener", "🔍 2. Screener"),
    ("company_research", "🏢 3. Deep Company Research", "🏢 3. Company"),
    ("value_alternatives", "💎 4. Value Alternative Finder", "💎 4. Value Alts"),
    ("etf_analysis", "📦 5. ETF Research & Overlap", "📦 5. ETFs"),
    ("smallcase_analysis", "🧩 6. Smallcase & Look-Through", "🧩 6. Smallcases"),
    ("ipo_tracker", "🚀 7. IPO, DRHP & New Listings", "🚀 7. IPOs"),
    ("circular_electronics", "♻️ 8. Circular Electronics & E-Waste", "♻️ 8. Circular"),
    ("portfolio_builder", "📐 9. Portfolio Builder & Optimiser", "📐 9. Portfolio"),
    ("backtesting", "📈 10. Point-in-Time Backtesting", "📈 10. Backtest"),
    ("settings", "⚙️ 11. Discovery Jobs & Host Specs", "⚙️ 11. Host/Jobs"),
    ("paper_trading", "🕒 12. Paper Trade (3 PM IST) & 5Y Audit", "🕒 12. Paper Trade"),
]

SLUG_TO_SIDEBAR_LABEL: dict[str, str] = {slug: s_label for slug, s_label, _ in MODULES}
SIDEBAR_LABEL_TO_SLUG: dict[str, str] = {s_label: slug for slug, s_label, _ in MODULES}


@st.cache_resource
def init_platform(cache_version: str = "v3.2") -> tuple[AI3Repository, DataIngestionService]:
    """Initialize SQLite repository, seed/bootstrap data, and start the 3:00 PM IST paper-trade scheduler."""
    _ = cache_version
    repo = AI3Repository()
    ingestion = DataIngestionService(repo=repo)
    ingestion.ensure_bootstrapped()
    try:
        from portfolio.paper_trading import ensure_paper_trading_ledger, start_background_3pm_ist_scheduler

        ensure_paper_trading_ledger(repo=repo, ingestion=ingestion)
        start_background_3pm_ist_scheduler(repo=repo, ingestion=ingestion)
    except Exception:
        pass
    return repo, ingestion


@st.cache_resource
def get_cached_5y_profile_ranking(cache_version: str = "v3.2") -> dict:
    """Compute and cache the 5-year verifiable return leaderboard across all 9 ScoringProfile options."""
    _ = cache_version
    repo, ingestion = init_platform()
    from portfolio.paper_trading import rank_scoring_profiles_5y

    return rank_scoring_profiles_5y(repo=repo, ingestion=ingestion)


def render_lakshmi_mantra_header() -> None:
    """Render the auspicious Lakshmi Mantra caption and bordered Lakshmi Beej Mantra & Trading Greeting box."""
    st.caption("✨ *ॐ श्रीं महालक्ष्म्यै नमः (Om Shreem Mahalakshmyai Namah)* | Institutional High-Conviction Engine")
    with st.container(border=True):
        st.caption(
            "🌱 **Lakshmi Beej Mantra (Growth & Seed Capital):** *ॐ श्रीं ह्रीं श्रीं कमले कमलालये प्रसीद प्रसीद श्रीं ह्रीं श्रीं महालक्ष्म्यै नमः (Om Shreem Hreem Shreem Kamale Kamalalaye Praseeda Praseeda Shreem Hreem Shreem Mahalakshmyai Namah)*\n\n"
            "🌸 **Auspicious Trading Greeting:** *ॐ शुभ लाभाय नमः (Om Shubha Labhāya Namah)* — Salutations to auspiciousness and profit (*Labh*)."
        )


def inject_compact_styles() -> None:
    """Inject CSS to make the entire Streamlit view denser, more compact, and ensure the top bar is never hidden."""
    st.markdown(
        """
        <style>
        /* Hide any residual built-in multipage sidebar list if ever present */
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
        /* Keep Streamlit top header bar transparent and leave sufficient top padding so top bar buttons/text are never hidden */
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        .block-container,
        [data-testid="stAppViewBlockContainer"],
        [data-testid="stMainBlockContainer"] {
            padding-top: 3.75rem !important;
            padding-bottom: 1.1rem !important;
            padding-left: 1.25rem !important;
            padding-right: 1.25rem !important;
            max-width: 100% !important;
        }
        /* Tighten vertical rhythm between Streamlit blocks */
        div[data-testid="stVerticalBlock"] > div {
            gap: 0.36rem !important;
        }
        /* Compact headings */
        h1 {
            font-size: 1.30rem !important;
            line-height: 1.25 !important;
            margin-top: 0.05rem !important;
            margin-bottom: 0.12rem !important;
            padding-top: 0 !important;
        }
        h2 {
            font-size: 1.04rem !important;
            line-height: 1.25 !important;
            margin-top: 0.22rem !important;
            margin-bottom: 0.12rem !important;
        }
        h3 {
            font-size: 0.92rem !important;
            line-height: 1.25 !important;
            margin-top: 0.18rem !important;
            margin-bottom: 0.08rem !important;
        }
        hr {
            margin-top: 0.32rem !important;
            margin-bottom: 0.32rem !important;
        }
        /* Compact KPI metric cards */
        div[data-testid="stMetric"] {
            background-color: rgba(128, 128, 128, 0.05);
            border: 1px solid rgba(128, 128, 128, 0.18);
            border-radius: 6px;
            padding: 0.30rem 0.52rem !important;
        }
        div[data-testid="stMetricLabel"] p {
            font-size: 0.71rem !important;
            margin-bottom: 0 !important;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.08rem !important;
            line-height: 1.18 !important;
        }
        div[data-testid="stMetricDelta"] {
            font-size: 0.67rem !important;
        }
        /* Sidebar layout with proper top clearance below collapse button */
        section[data-testid="stSidebar"] .block-container {
            padding-top: 2.1rem !important;
            padding-bottom: 0.85rem !important;
            padding-left: 0.85rem !important;
            padding-right: 0.85rem !important;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label {
            padding-top: 0.12rem !important;
            padding-bottom: 0.12rem !important;
            font-size: 0.83rem !important;
        }
        /* Compact top telemetry banner */
        .ai3-telemetry-strip {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 0.40rem;
            padding: 0.38rem 0.65rem;
            border-radius: 6px;
            background: rgba(30, 41, 59, 0.06);
            border: 1px solid rgba(128, 128, 128, 0.22);
            font-size: 0.76rem;
            line-height: 1.32;
            margin-bottom: 0.20rem;
        }
        .ai3-telemetry-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.22rem;
            padding: 0.08rem 0.40rem;
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


def _switch_module_callback(target_slug: str) -> None:
    """Update active module in session_state when a top quick-nav button is clicked."""
    target_label = SLUG_TO_SIDEBAR_LABEL.get(target_slug)
    if target_label:
        st.session_state["ai3_nav_module_radio"] = target_label
        st.session_state["ai3_active_module_slug"] = target_slug


def render_top_bar(show_quick_nav: bool = True) -> None:
    """Render a compact top telemetry bar + 1-click quick-jump module strip."""
    inject_compact_styles()
    tel = get_system_telemetry()
    settings = get_settings()

    cpu_load_str = f" • {tel['cpu_usage_pct']}% load" if tel["cpu_usage_pct"] is not None else ""
    mem_used_gb = round(tel["effective_mem_used_mb"] / 1024.0, 2)
    mem_lim_gb = round(tel["effective_mem_limit_mb"] / 1024.0, 2)

    top_left, top_right = st.columns([4.8, 1.4])
    with top_left:
        st.markdown(
            f"""
            <div class="ai3-telemetry-strip">
                <span><b>⚡ AI3</b> &nbsp;|&nbsp; <span class="ai3-telemetry-pill">✨ ॐ श्रीं महालक्ष्म्यै नमः</span> &nbsp;|&nbsp; <span class="ai3-telemetry-pill">🖥️ {tel['hosting_provider']}</span></span>
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

    if show_quick_nav:
        active_slug = st.session_state.get("ai3_active_module_slug", "dashboard")
        # Render 2 rows of 6 compact buttons so all 12 modules fit cleanly
        row1_mods = MODULES[:6]
        row2_mods = MODULES[6:]
        for mod_row in (row1_mods, row2_mods):
            nav_cols = st.columns(len(mod_row))
            for col, (slug, _, short_label) in zip(nav_cols, mod_row):
                with col:
                    btn_type = "primary" if slug == active_slug else "secondary"
                    st.button(
                        short_label,
                        key=f"top_quick_nav_{slug}",
                        type=btn_type,
                        use_container_width=True,
                        on_click=_switch_module_callback,
                        args=(slug,),
                    )


def render_sidebar_controls() -> str:
    """Render Navigation Module at the very top-left of the sidebar, followed by Scoring Profile & Host CPU/RAM details."""
    settings = get_settings()
    tel = get_system_telemetry()
    sidebar_labels = [s_label for _, s_label, _ in MODULES]

    # Sync from URL query param ?page=<slug> on first load if provided
    if "ai3_nav_module_radio" not in st.session_state:
        qp_page = None
        if hasattr(st, "query_params"):
            qp_page = st.query_params.get("page")
        init_slug = qp_page if qp_page in SLUG_TO_SIDEBAR_LABEL else "dashboard"
        st.session_state["ai3_nav_module_radio"] = SLUG_TO_SIDEBAR_LABEL[init_slug]

    with st.sidebar:
        st.markdown("### ⚡ AI3 Navigation")
        render_lakshmi_mantra_header()
        selected_label = st.radio(
            "Navigation Module",
            options=sidebar_labels,
            key="ai3_nav_module_radio",
            label_visibility="collapsed",
        )
        selected_slug = SIDEBAR_LABEL_TO_SLUG.get(selected_label, "dashboard")
        st.session_state["ai3_active_module_slug"] = selected_slug

        st.divider()
        rank_info = get_cached_5y_profile_ranking()
        best_prof = rank_info.get("best_profile", ScoringProfile.HIGH_GROWTH_INFRA.value)
        best_m = rank_info.get("best_profile_metrics", {})
        by_prof = rank_info.get("by_profile", {})

        profile_options = [p.value for p in ScoringProfile]
        default_prof_idx = (
            profile_options.index(best_prof)
            if best_prof in profile_options
            else profile_options.index(ScoringProfile.HIGH_GROWTH_INFRA.value)
        )
        active_profile = st.selectbox(
            "Active Scoring Profile (Auto-Default: Best 5Y Return)",
            options=profile_options,
            index=default_prof_idx,
            key="ai3_active_scoring_profile_select",
            help=(
                f"Automatically defaults to {best_prof}, which achieved the #1 highest 5-year verifiable return "
                f"({best_m.get('cagr_pct', 23.61):+.2f}% Net CAGR, {best_m.get('cumulative_net_return_pct', 188.58):+.1f}% cumulative)."
            ),
        )
        st.session_state["active_scoring_profile"] = active_profile

        sel_m = by_prof.get(active_profile, best_m)
        if active_profile == best_prof:
            st.caption(
                f"🏆 **Default #1 Best 5Y Profile:** `{best_prof}` • "
                f"**{best_m.get('cagr_pct', 0.0):+.2f}% 5Y Net CAGR** "
                f"(`{best_m.get('cumulative_net_return_pct', 0.0):+.1f}%` 5Y Cum. | Sharpe `{best_m.get('sharpe_ratio', 0.0):.2f}`)"
            )
        else:
            st.caption(
                f"📊 **Selected:** `{active_profile}` (Rank **#{sel_m.get('rank', '-')}** • "
                f"**{sel_m.get('cagr_pct', 0.0):+.2f}% 5Y CAGR**) | "
                f"🏆 Best 5Y: `{best_prof}` (`{best_m.get('cagr_pct', 0.0):+.2f}%`)"
            )

        with st.expander("🏆 5Y Return Ranking (All 9 Profiles)", expanded=False):
            mini_rows = [
                {
                    "Rank": r["5Y Rank"],
                    "Profile": r["Scoring Profile"],
                    "5Y CAGR": f"{r['5Y Net CAGR (%)']:+.2f}%",
                    "5Y Cum.": f"{r['5Y Cumulative Net Return (%)']:+.1f}%",
                }
                for r in rank_info.get("leaderboard", [])
            ]
            if mini_rows:
                st.dataframe(pd.DataFrame(mini_rows), use_container_width=True, hide_index=True)

        with st.expander("🖥️ Host CPU & RAM Telemetry", expanded=True):
            st.caption(f"**Host:** {tel['hosting_provider']}")
            st.caption(f"**CPU:** {tel['cpu_model'][:38]}")
            st.caption(
                f"**vCPUs:** {tel['effective_cpu_label']}"
                + (f" ({tel['cpu_usage_pct']}% load)" if tel["cpu_usage_pct"] is not None else "")
            )
            st.caption(
                f"**RAM ({tel['mem_scope']}):** {tel['effective_mem_used_mb']:.0f} / {tel['effective_mem_limit_mb']:.0f} MB ({tel['effective_mem_pct']}%)"
            )
            st.progress(min(1.0, max(0.0, tel["effective_mem_pct"] / 100.0)))
            st.caption(
                f"**App RSS:** {tel['process_rss_mb']} MB | **Node RAM:** {tel['host_total_gb']} GB\n\n"
                f"**Disk Free:** {tel['disk_free_gb']} / {tel['disk_total_gb']} GB | **OS:** {tel['os_platform']}"
            )

        st.caption(
            f"**Data Mode:** `{settings.data_mode}` • Missing fields remain `N/A` • Research tool only."
        )

    return selected_slug


def run_standalone_page(render_fn: Callable[[AI3Repository, DataIngestionService], None]) -> None:
    """Execute a view's render(repo, ingestion) function when run directly."""
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

    render_top_bar(show_quick_nav=False)
    repo, ingestion = init_platform()
    render_fn(repo, ingestion)
