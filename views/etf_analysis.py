"""Page 5: ETF Research & Overlap Module (Section 6 of the Master Project Prompt)."""

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

from analytics.equity_enrichment import (
    get_live_etf_quote,
    load_live_market_snapshot,
    refresh_live_market_snapshot,
)
from data.ingestion import DataIngestionService
from database.repository import AI3Repository
from portfolio.overlap import compute_basket_overlap, compute_pairwise_overlap_matrix


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("📊 Indian ETF Research & AI/Data-Centre Exposure Module")
    st.caption(
        "Compare live NSE prices, expense ratios, AUM, tracking error, liquidity, quantified AI/Data-Centre thematic revenue exposure, and constituent overlap across Indian ETFs."
    )

    etfs = repo.get_etfs()
    if not etfs:
        st.warning("No ETFs found in repository.")
        return

    etf_rows = []
    for e in etfs:
        lq = get_live_etf_quote(e["symbol"]) or {}
        etf_rows.append(
            {
                "Symbol": e["symbol"],
                "ETF Name": e["name"],
                "Live CMP (Rs)": lq.get("cmp"),
                "1D (%)": lq.get("ret_1d_pct"),
                "1M (%)": lq.get("ret_1m_pct"),
                "6M (%)": lq.get("ret_6m_pct"),
                "1Y (%)": lq.get("ret_1y_pct"),
                "Issuer": e["issuer"],
                "Category": e["category"],
                "Underlying Index": e["underlying_index"],
                "Expense Ratio (%)": e["expense_ratio_pct"],
                "AUM (Rs Cr)": e["aum_inr_cr"],
                "Tracking Error (%)": e["tracking_error_pct"],
                "Daily Turnover (Rs Cr)": lq.get("avg_daily_turnover_cr") or e["avg_daily_turnover_inr_cr"],
                "AI & Data-Centre Exposure (%)": e["ai_infra_exposure_pct"],
                "Constituents Mapped": len(e["top_constituents"]),
            }
        )
    df_etf = pd.DataFrame(etf_rows)
    st.subheader("Indian ETF Universe Comparison (Live NSE Quotes & AI Exposure)")
    st.dataframe(df_etf, use_container_width=True, hide_index=True)

    eb1, eb2 = st.columns([1.5, 2.5])
    eb1.download_button(
        "📥 Export ETF Comparison Table (CSV)",
        data=df_etf.to_csv(index=False).encode("utf-8"),
        file_name="ai3_indian_etfs_live.csv",
        mime="text/csv",
        use_container_width=True,
    )
    if eb2.button("🔄 Refresh Live NSE ETF Quotes", type="primary"):
        with st.spinner("Refreshing live NSE ETF prices via Yahoo Finance..."):
            snap = refresh_live_market_snapshot(update_csv=False)
            st.success(f"Synced {len(snap.get('etfs', {}))} live NSE ETFs as of {snap.get('as_of_ist')}.")
            st.rerun()

    st.divider()
    col_l, col_r = st.columns([1, 1])

    etf_by_sym = {e["symbol"]: e for e in etfs}
    with col_l:
        sel_etf_sym = st.selectbox(
            "Inspect ETF Constituent Weights & Sector Allocation",
            options=list(etf_by_sym.keys()),
            format_func=lambda s: f"{s} — {etf_by_sym[s]['name']} (AI/DC Exposure: {etf_by_sym[s]['ai_infra_exposure_pct']}%)",
        )
        sel_etf = etf_by_sym[sel_etf_sym]
        st.markdown(f"**Research Notes:** {sel_etf.get('notes') or ''}")
        raw_tc = sel_etf["top_constituents"]
        tc_items = (
            raw_tc.items()
            if isinstance(raw_tc, dict)
            else [(c["symbol"], c["weight_pct"]) for c in raw_tc]
        )
        const_df = pd.DataFrame(
            [{"Constituent Symbol": k, "Weight (%)": v} for k, v in tc_items]
        ).sort_values("Weight (%)", ascending=False)
        st.dataframe(const_df, use_container_width=True, hide_index=True)

    with col_r:
        st.subheader("Pairwise Weighted Constituent Overlap (%)")
        baskets = {e["symbol"]: e["top_constituents"] for e in etfs}
        matrix = compute_pairwise_overlap_matrix(baskets)
        mat_df = pd.DataFrame(matrix)
        fig_hm = px.imshow(
            mat_df,
            text_auto=".1f",
            color_continuous_scale="Blues",
            aspect="auto",
        )
        fig_hm.update_layout(height=400, margin=dict(t=20, l=10, r=10, b=10))
        st.plotly_chart(fig_hm, use_container_width=True)

    st.divider()
    st.subheader("Detailed ETF vs ETF Constituent Overlap Inspector")
    c1, c2 = st.columns(2)
    with c1:
        etf_a = st.selectbox("ETF A", list(etf_by_sym.keys()), index=0)
    with c2:
        etf_b = st.selectbox("ETF B", list(etf_by_sym.keys()), index=min(5, len(etf_by_sym) - 1))

    ov = compute_basket_overlap(etf_a, etf_by_sym[etf_a]["top_constituents"], etf_b, etf_by_sym[etf_b]["top_constituents"])
    m1, m2, m3 = st.columns(3)
    m1.metric("Weighted Overlap (%)", f"{ov.weighted_overlap_pct}%")
    m2.metric("Jaccard Similarity", f"{ov.jaccard_similarity:.3f}")
    m3.metric("Shared Constituents", f"{ov.shared_symbols_count}")
    if ov.shared_symbols:
        st.dataframe(pd.DataFrame(ov.shared_symbols), use_container_width=True, hide_index=True)


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
