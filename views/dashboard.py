"""Page 1: Executive Overview Dashboard."""

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
import plotly.express as px
import streamlit as st

from analytics.exposure_scoring import score_company_exposure
from core.config import load_sector_taxonomy
from data.ingestion import DataIngestionService
from database.repository import AI3Repository


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("⚡ AI Infrastructure Investment Intelligence (AI3)")
    st.caption(
        "Institutional Equity, Component Supply-Chain, ETF/Smallcase Overlap, Circular Electronics & IPO Research Platform"
    )

    profile = st.session_state.get("active_scoring_profile", "DEFAULT_100PT")
    all_secs = repo.get_securities()
    f_map = repo.get_latest_fundamentals_map()
    etfs = repo.get_etfs()
    ipos = repo.get_ipos()
    taxonomy = load_sector_taxonomy().get("categories", {})

    india_secs = [s for s in all_secs if s["geography"] == "INDIA"]
    investable_india = [s for s in india_secs if s["is_investable"]]
    high_risk_india = [s for s in india_secs if not s["is_investable"]]
    global_secs = [s for s in all_secs if s["geography"] != "INDIA"]

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Indian Investable Universe", f"{len(investable_india)} Stocks", "NSE / BSE Verified")
    col2.metric("High-Risk Research Bucket", f"{len(high_risk_india)} Stocks", "Isolated from Portfolios")
    col3.metric("Global Benchmark Stocks", f"{len(global_secs)} Stocks", "US / TW / JP / KR / EU")
    col4.metric("Tracked Indian ETFs", f"{len(etfs)} ETFs", "Look-Through Enabled")
    col5.metric("IPO & DRHP Pipeline", f"{len(ipos)} Filings", "Dates Verified Guard")

    st.divider()

    # Build scored summary dataframe
    rows = []
    for sec in all_secs:
        f = f_map.get(sec["symbol"], {})
        bd = score_company_exposure(sec, f, profile=profile)
        cat_code = sec.get("primary_category", "OTHER")
        cat_name = taxonomy.get(cat_code, {}).get("name", cat_code)
        rows.append(
            {
                "Symbol": sec["symbol"],
                "Company": sec["company_name"],
                "Exchange": sec["exchange"],
                "Geography": sec["geography"],
                "Category Code": cat_code,
                "Value Chain Segment": cat_name,
                "Universe Tier": sec["universe_tier"],
                "Investable": sec["is_investable"] and not bd.investability_blocked,
                "Base AI Score (100)": bd.total_score,
                f"Profile Score ({profile})": bd.profile_adjusted_score,
                "Direct AI/DC Rev (%)": f.get("direct_ai_dc_rev_share_pct"),
                "Order Book / Sales (x)": f.get("order_book_to_LTM_sales"),
                "Market Cap (Rs Cr)": f.get("market_cap_inr_cr"),
                "Trailing P/E": f.get("trailing_pe"),
                "ROCE (%)": f.get("roce_pct"),
                "Evidence Type": bd.evidence_type.value,
                "Risk Flags": ", ".join(rf.code for rf in bd.risk_flags) if bd.risk_flags else "NONE",
                "Data Provenance": f.get("value_type", "SEED_REFERENCE_SNAPSHOT"),
            }
        )
    df_all = pd.DataFrame(rows)

    left_col, right_col = st.columns([3, 2])
    with left_col:
        st.subheader("AI Infrastructure Value-Chain Coverage (India Investable)")
        df_ind_inv = df_all[(df_all["Geography"] == "INDIA") & (df_all["Investable"] == True)]
        if not df_ind_inv.empty:
            fig_tree = px.treemap(
                df_ind_inv,
                path=["Value Chain Segment", "Symbol"],
                values="Market Cap (Rs Cr)",
                color="Base AI Score (100)",
                color_continuous_scale="Viridis",
                hover_data=["Company", "Direct AI/DC Rev (%)", "Trailing P/E", "ROCE (%)", "Evidence Type"],
            )
            fig_tree.update_layout(margin=dict(t=15, l=5, r=5, b=5), height=320)
            st.plotly_chart(fig_tree, use_container_width=True)

    with right_col:
        st.subheader("Category Score & Valuation Summary")
        cat_summary = (
            df_ind_inv.groupby("Value Chain Segment", as_index=False)
            .agg(
                Companies=("Symbol", "count"),
                Avg_AI_Score=("Base AI Score (100)", "mean"),
                Median_PE=("Trailing P/E", "median"),
                Median_ROCE=("ROCE (%)", "median"),
            )
            .sort_values("Avg_AI_Score", ascending=False)
        )
        cat_summary["Avg_AI_Score"] = cat_summary["Avg_AI_Score"].round(1)
        cat_summary["Median_PE"] = cat_summary["Median_PE"].round(1)
        cat_summary["Median_ROCE"] = cat_summary["Median_ROCE"].round(1)
        st.dataframe(cat_summary, use_container_width=True, hide_index=True, height=320)

    st.divider()
    tab1, tab2, tab3 = st.tabs(
        [
            "🏆 Top Rated Indian AI Infrastructure Leaders",
            "⚠️ Isolated High-Risk & Governance Watchlist",
            "🌏 Global Supply-Chain Benchmarks",
        ]
    )

    with tab1:
        top_ind = df_ind_inv.sort_values(f"Profile Score ({profile})", ascending=False).head(20)
        st.dataframe(
            top_ind[
                [
                    "Symbol",
                    "Company",
                    "Value Chain Segment",
                    "Base AI Score (100)",
                    f"Profile Score ({profile})",
                    "Direct AI/DC Rev (%)",
                    "Order Book / Sales (x)",
                    "Trailing P/E",
                    "ROCE (%)",
                    "Evidence Type",
                    "Risk Flags",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            height=290,
        )

    with tab2:
        st.warning(
            "Securities below are held in `HIGH_RISK_RESEARCH` due to auditor qualifications, negative net worth, "
            "low liquidity, or unverified AI/component business relevance. They are blocked from standard investable portfolios."
        )
        df_hr = df_all[df_all["Investable"] == False].sort_values("Geography")
        st.dataframe(
            df_hr[
                [
                    "Symbol",
                    "Company",
                    "Exchange",
                    "Value Chain Segment",
                    "Universe Tier",
                    "Base AI Score (100)",
                    "Evidence Type",
                    "Risk Flags",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            height=240,
        )

    with tab3:
        st.info(
            "Global securities serve as valuation & technological benchmarks across compute (NVDA, AMD, TSM, ASML), "
            "power/cooling (VRT, ETN, GEV, SU, SIE), interconnect (ANET, GLW), and circular ITAD (ERI)."
        )
        df_glob = df_all[df_all["Geography"] != "INDIA"].sort_values("Base AI Score (100)", ascending=False)
        st.dataframe(
            df_glob[
                [
                    "Symbol",
                    "Company",
                    "Exchange",
                    "Geography",
                    "Value Chain Segment",
                    "Base AI Score (100)",
                    "Direct AI/DC Rev (%)",
                    "Trailing P/E",
                    "ROCE (%)",
                    "Evidence Type",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            height=260,
        )


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
