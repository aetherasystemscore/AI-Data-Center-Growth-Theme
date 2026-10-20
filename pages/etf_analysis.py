"""Page 5: ETF Research & Overlap Module (Section 6 of the Master Project Prompt)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from data.ingestion import DataIngestionService
from database.repository import AI3Repository
from portfolio.overlap import compute_basket_overlap, compute_pairwise_overlap_matrix


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("📊 Indian ETF Research & AI/Data-Centre Exposure Module")
    st.caption(
        "Compare expense ratios, AUM, tracking error, liquidity, quantified AI/Data-Centre thematic revenue exposure, and constituent overlap across Indian ETFs."
    )

    etfs = repo.get_etfs()
    if not etfs:
        st.warning("No ETFs found in repository.")
        return

    df_etf = pd.DataFrame(
        [
            {
                "Symbol": e["symbol"],
                "ETF Name": e["name"],
                "Issuer": e["issuer"],
                "Category": e["category"],
                "Underlying Index": e["underlying_index"],
                "Expense Ratio (%)": e["expense_ratio_pct"],
                "AUM (Rs Cr)": e["aum_inr_cr"],
                "Tracking Error (%)": e["tracking_error_pct"],
                "Daily Turnover (Rs Cr)": e["avg_daily_turnover_inr_cr"],
                "AI & Data-Centre Exposure (%)": e["ai_infra_exposure_pct"],
                "Constituents Mapped": len(e["top_constituents"]),
            }
            for e in etfs
        ]
    )
    st.subheader("Indian ETF Universe Comparison")
    st.dataframe(df_etf, use_container_width=True, hide_index=True)

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
        const_df = pd.DataFrame(
            [{"Constituent Symbol": k, "Weight (%)": v} for k, v in sel_etf["top_constituents"].items()]
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
