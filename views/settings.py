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
from jobs.run_paper_trade_3pm import run_paper_trade_3pm_job
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

    st.subheader("1. Automated Discovery, Refresh & 3:00 PM IST Paper-Trade Jobs")
    st.caption(
        "Execute any of the 7 background discovery, data-validation, and daily 3:00 PM IST paper-trading jobs on demand. Every job logs its execution to `job_runs`."
    )

    with st.expander("📖 How to Use Each Job Button (Step-by-Step Operational Guide)", expanded=True):
        button_guide = [
            {
                "Button": "1. 🔄 Update Security Master",
                "When to Click": "First step after adding new tickers or after corporate actions (symbol changes/mergers).",
                "What It Does": "Validates all NSE/BSE/Global tickers, resolves legacy ticker aliases (e.g., POWERINDIA -> HITACHIEN, ABBINDIA -> ABB), verifies ISINs, and ensures high-risk e-waste names remain quarantined.",
                "Where Output Appears": "Updates the Security Master table & logs a SUCCESS entry in Section 4 (Job Execution Audit Log).",
            },
            {
                "Button": "2. 🆕 Discover New Listings",
                "When to Click": "Weekly or whenever new Mainboard/SME companies list on NSE/BSE.",
                "What It Does": "Scans recent NSE/BSE listings against AI infrastructure, transformer, EMS, cooling, cable, and e-waste keyword taxonomies, and stages matching candidates as CANDIDATE_PENDING_REVIEW.",
                "Where Output Appears": "Populates Section 2 (Discovery Queue) below for analyst verification.",
            },
            {
                "Button": "3. 📑 Discover SEBI IPOs",
                "When to Click": "Before reviewing Tab 7 (IPO, DRHP & New Listings Tracker).",
                "What It Does": "Scans SEBI DRHP/RHP filings and exchange IPO calendars for upcoming AI, data-centre EPC, power equipment, and circular-electronics public issues, scoring their Proceed Quality.",
                "Where Output Appears": "Updates Tab 7 (IPO Tracker) & logs run metrics in Section 4.",
            },
            {
                "Button": "4. 💹 Refresh Prices",
                "When to Click": "Daily (after market close or before running technicals/backtests).",
                "What It Does": "Fetches and updates OHLCV price history and 20-day Average Daily Turnover (ADV) across the security universe, tagging each series with its provenance (REPORTED vs DERIVED).",
                "Where Output Appears": "Updates CMP, Technical Scores, Moving Averages (Tab 3), and Backtest price series (Tab 10 & Tab 12).",
            },
            {
                "Button": "5. 📊 Refresh Financials",
                "When to Click": "Quarterly after earnings season or when screening valuation/ROCE.",
                "What It Does": "Re-validates quarterly & annual fundamentals (Revenue, EBITDA, ROCE, D/E, CFO/EBITDA, Order Book, Promoter/FII/DII holdings, and Auditor Flags) and recalculates 100-pt AI Exposure Scores.",
                "Where Output Appears": "Updates Fundamental Scores and Valuation tables across Tabs 1, 2, 3, 4, 8, and 9.",
            },
            {
                "Button": "6. 📰 Refresh Filing News",
                "When to Click": "Before inspecting company research memos in Tab 3.",
                "What It Does": "Runs the Fact-vs-Narrative NLP extractor on corporate announcements, investor presentations, and order-win filings to separate verified purchase orders from non-binding MOUs.",
                "Where Output Appears": "Updates Structured Institutional Research Memos & Evidence Badges in Tab 3.",
            },
            {
                "Button": "7. 🕒 Run 3 PM IST Paper Trade",
                "When to Click": "Runs automatically every working day (Mon–Fri) at 3:00 PM IST, or click manually to force a cycle.",
                "What It Does": "Marks all open forward paper-trading positions to the 3:00 PM IST market price, logs Indian delivery transaction costs, and updates the forward NAV ledger.",
                "Where Output Appears": "Updates Tab 12 (Paper Trade @ 3 PM IST & 5Y Audit) and logs execution in Section 4.",
            },
        ]
        st.dataframe(pd.DataFrame(button_guide), use_container_width=True, hide_index=True)

    jb1, jb2, jb3, jb4, jb5, jb6, jb7 = st.columns(7)
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
    if jb7.button("🕒 Run 3 PM IST Paper Trade", use_container_width=True):
        out = run_paper_trade_3pm_job(repo, force=True)
        st.success(out.get("message", str(out)))

    st.divider()
    col_dq, col_sm, col_jr = st.columns([2.2, 1.3, 1.8])
    with col_dq:
        st.subheader("2. Discovery Queue (`CANDIDATE_PENDING_REVIEW`)")
        queue_items = repo.get_discovery_queue()
        if not queue_items:
            if st.button("Populate Discovery Queue via New Listing Scan", type="primary"):
                run_discover_new_listings(repo)
                queue_items = repo.get_discovery_queue()
        if queue_items:
            st.dataframe(pd.DataFrame(queue_items), use_container_width=True, hide_index=True, height=220)
            cand_options = {f"#{c['id']} — {c['symbol']} ({c['company_name']}) [{c['status']}]": c["id"] for c in queue_items}
            sel_cand_label = st.selectbox("Select Candidate for Analyst Review", options=list(cand_options.keys()))
            dq_b1, dq_b2 = st.columns(2)
            if dq_b1.button("✅ Approve Candidate", use_container_width=True):
                if repo.update_discovery_candidate_status(cand_options[sel_cand_label], "APPROVED_INVESTABLE"):
                    st.success(f"Approved candidate {sel_cand_label}")
                    st.rerun()
            if dq_b2.button("❌ Reject / Quarantine", use_container_width=True):
                if repo.update_discovery_candidate_status(cand_options[sel_cand_label], "REJECTED_LOW_EXPOSURE"):
                    st.warning(f"Rejected candidate {sel_cand_label}")
                    st.rerun()
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
            df_runs = pd.DataFrame(runs)
            st.dataframe(df_runs, use_container_width=True, hide_index=True, height=220)
            st.download_button(
                "📥 Export Job Execution Audit Log (CSV)",
                data=df_runs.to_csv(index=False).encode("utf-8"),
                file_name="ai3_job_execution_audit_log.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.caption("No job runs recorded yet. Click any job button above to execute and log a run.")


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
