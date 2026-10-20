"""Page 11: Discovery Queue, Automated Refresh Jobs & Platform Settings (Section 17 & 18 of Master Prompt)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ai.research_summariser import get_active_ai_provider
from core.config import get_settings
from core.security_master import SecurityMasterService
from data.ingestion import DataIngestionService
from database.repository import AI3Repository
from jobs.discover_ipos import run_discover_ipos
from jobs.discover_new_listings import run_discover_new_listings
from jobs.refresh_financials import run_refresh_financials
from jobs.refresh_prices import run_refresh_prices
from jobs.research_news import run_research_news
from jobs.update_security_master import run_update_security_master


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("⚙️ Discovery Engine, Automated Jobs, Security Master & AI Settings")

    settings = get_settings()
    ai_prov = get_active_ai_provider()

    c1, c2, c3 = st.columns(3)
    c1.metric("Active Data Mode", settings.data_mode)
    c2.metric("Active AI Provider", ai_prov.provider_name)
    c3.metric("SQLite Database Path", str(settings.sqlite_db_path.name))

    st.divider()
    st.subheader("1. Automated Discovery & Refresh Jobs")
    st.caption(
        "Execute any of the 6 background discovery and data-validation jobs on demand. Every job logs its execution to `job_runs`."
    )

    jb1, jb2, jb3, jb4, jb5, jb6 = st.columns(6)
    if jb1.button("🔄 Update Security Master"):
        out = run_update_security_master(repo)
        st.success(out.get("message", str(out)))
    if jb2.button("🆕 Discover New Listings"):
        out = run_discover_new_listings(repo)
        st.success(out.get("message", str(out)))
    if jb3.button("📑 Discover SEBI IPOs"):
        out = run_discover_ipos(repo)
        st.success(out.get("message", str(out)))
    if jb4.button("💹 Refresh Prices"):
        out = run_refresh_prices(repo)
        st.success(out.get("message", str(out)))
    if jb5.button("📊 Refresh Financials"):
        out = run_refresh_financials(repo)
        st.success(out.get("message", str(out)))
    if jb6.button("📰 Refresh Filing News"):
        out = run_research_news(repo)
        st.success(out.get("message", str(out)))

    st.divider()
    st.subheader("2. Automated Discovery Queue (`CANDIDATE_PENDING_REVIEW`)")
    st.info(
        "Newly discovered listings and DRHP filings are placed here as `CANDIDATE_PENDING_REVIEW` and **never** promoted "
        "into the active investable universe without analyst validation."
    )
    queue_items = repo.get_discovery_queue()
    if not queue_items:
        if st.button("Populate Discovery Queue via New Listing Scan"):
            run_discover_new_listings(repo)
            queue_items = repo.get_discovery_queue()

    if queue_items:
        st.dataframe(pd.DataFrame(queue_items), use_container_width=True, hide_index=True)

    st.divider()
    col_sm, col_jr = st.columns(2)
    with col_sm:
        st.subheader("3. Security Master Alias & Ticker Verification")
        sm = SecurityMasterService()
        alias_df = pd.DataFrame(
            [{"Legacy / Alternate Ticker": k, "Canonical AI3 Symbol": v} for k, v in sm.KNOWN_ALIASES.items()]
        )
        st.dataframe(alias_df, use_container_width=True, hide_index=True)

    with col_jr:
        st.subheader("4. Recent Job Execution Audit Log")
        runs = repo.get_recent_job_runs(limit=15)
        if runs:
            st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)
        else:
            st.caption("No job runs recorded yet. Click any job button above to execute and log a run.")
