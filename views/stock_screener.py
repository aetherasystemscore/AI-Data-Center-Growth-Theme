"""Page 2: AI Value-Chain Stock Screener."""

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

from analytics.equity_enrichment import compute_enriched_equity_metrics
from analytics.exposure_scoring import score_company_exposure
from analytics.fundamentals import evaluate_fundamental_health
from analytics.valuation import compute_valuation_metrics
from core.config import load_sector_taxonomy
from data.ingestion import DataIngestionService
from database.repository import AI3Repository


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("🔍 AI Infrastructure & Component Supply-Chain Screener")
    st.caption(
        "Filter across all 8 value-chain categories, 8 scoring profiles, Fundamental/Technical/Analyst scores, 2Y Price & Ownership trends, and ROCE."
    )

    profile = st.session_state.get("active_scoring_profile", "HIGH_GROWTH_INFRA")
    taxonomy = load_sector_taxonomy().get("categories", {})
    all_secs = repo.get_securities()
    f_map = repo.get_latest_fundamentals_map()

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        geo_filter = st.selectbox("Geography", ["INDIA", "ALL", "US", "TAIWAN", "JAPAN", "SOUTH_KOREA", "EUROPE"])
    with col_f2:
        tier_filter = st.selectbox(
            "Universe Filter",
            ["INVESTABLE_ONLY", "ALL_INCLUDING_HIGH_RISK", "HIGH_RISK_RESEARCH_ONLY"],
        )
    with col_f3:
        cat_options = ["ALL"] + list(taxonomy.keys())
        cat_filter = st.selectbox(
            "Value-Chain Category",
            options=cat_options,
            format_func=lambda c: "All 8 Categories" if c == "ALL" else f"{c}: {taxonomy[c]['name']}",
        )
    with col_f4:
        min_direct_rev = st.slider("Min Direct AI/DC Revenue (%)", 0.0, 80.0, 0.0, 2.5)

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        max_pe = st.slider("Max Trailing P/E (x)", 10.0, 150.0, 150.0, 5.0)
    with col_s2:
        min_roce = st.slider("Min ROCE (%)", -10.0, 40.0, 0.0, 2.0)
    with col_s3:
        min_turnover = st.slider("Min Daily Turnover (Rs Cr)", 0.0, 100.0, 1.0, 1.0)
    with col_s4:
        exclude_narrative = st.checkbox("Confirmed Contracts / Segments Only", value=False)

    records = []
    for sec in all_secs:
        if geo_filter != "ALL" and sec["geography"] != geo_filter:
            continue
        if cat_filter != "ALL" and cat_filter not in sec.get("sector_tags", []):
            continue

        f = f_map.get(sec["symbol"], {})
        bd = score_company_exposure(sec, f, profile=profile)
        fh = evaluate_fundamental_health(f, sec)
        vm = compute_valuation_metrics(f)
        enr = compute_enriched_equity_metrics(sec, f, profile=profile)

        is_inv = bool(sec["is_investable"]) and not bd.investability_blocked
        if tier_filter == "INVESTABLE_ONLY" and not is_inv:
            continue
        if tier_filter == "HIGH_RISK_RESEARCH_ONLY" and is_inv:
            continue

        direct_rev = f.get("direct_ai_dc_rev_share_pct") or 0.0
        if direct_rev < min_direct_rev:
            continue

        t_pe = f.get("trailing_pe")
        if max_pe < 150.0 and (t_pe is None or t_pe > max_pe):
            continue

        roce = f.get("roce_pct")
        if min_roce > -10.0 and (roce is None or roce < min_roce):
            continue

        adv = f.get("avg_daily_turnover_inr_cr") or 0.0
        if adv < min_turnover:
            continue

        if exclude_narrative and bd.evidence_type.value not in ("AUDITED_SEGMENT", "CONTRACT_DISCLOSURE"):
            continue

        records.append(
            {
                "Symbol": sec["symbol"],
                "Company": sec["company_name"],
                "Exchange": sec["exchange"],
                "Primary Category": sec["primary_category"],
                "CMP": enr["cmp"],
                "AI Exposure Score": bd.total_score,
                f"Profile ({profile})": bd.profile_adjusted_score,
                "Fundamental Score": enr["fundamental_score"],
                "Technical Score": enr["technical_score"],
                "Analyst Score": enr["analyst_score"],
                "Analyst Rating": enr["analyst_rating"],
                "Direct AI/DC Rev (%)": f.get("direct_ai_dc_rev_share_pct"),
                "3Y Rev CAGR (%)": f.get("rev_cagr_3y_pct"),
                "ROCE (%)": roce,
                "EBITDA Margin (%)": f.get("ebitda_margin_pct"),
                "Debt/Equity": f.get("debt_to_equity"),
                "Order Book / Sales (x)": f.get("order_book_to_LTM_sales"),
                "Trailing P/E": t_pe,
                "Forward P/E": f.get("forward_pe"),
                "EV/EBITDA": f.get("ev_ebitda"),
                "PEG Ratio": f.get("peg_ratio"),
                "FCF Yield (%)": vm.get("fcf_yield_pct"),
                "Price Trend (1M | 6M | 1Y | 2Y)": enr["price_trend_summary"],
                "Promoter % (2Y Trend)": enr["promoter_trend"],
                "FII % (2Y Trend)": enr["fii_trend"],
                "DII % (2Y Trend)": enr["dii_trend"],
                "Daily Turnover (Rs Cr)": adv,
                "Sector KPI": fh.get("sector_kpi_summary"),
                "Evidence Type": bd.evidence_type.value,
                "Risk Flags": ", ".join(rf.code for rf in bd.risk_flags) if bd.risk_flags else "NONE",
            }
        )

    df = pd.DataFrame(records)
    st.markdown(f"**Matching Securities:** `{len(df)}`")

    if df.empty:
        st.info("No securities match the current filter combination. Relax one or more sliders above.")
        return

    df = df.sort_values(f"Profile ({profile})", ascending=False)
    st.dataframe(df, use_container_width=True, hide_index=True)

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Export Screener Results (CSV)",
        data=csv_bytes,
        file_name=f"ai3_screener_{profile.lower()}.csv",
        mime="text/csv",
    )

    st.divider()
    st.subheader("Valuation (Trailing P/E) vs AI Infrastructure Exposure Score")
    df_plot = df.dropna(subset=["Trailing P/E", "AI Exposure Score"])
    if not df_plot.empty:
        fig = px.scatter(
            df_plot,
            x="Trailing P/E",
            y="AI Exposure Score",
            color="Primary Category",
            size="Daily Turnover (Rs Cr)",
            hover_name="Symbol",
            hover_data=["Company", "CMP", "Fundamental Score", "Technical Score", "Analyst Rating", "ROCE (%)"],
            height=380,
        )
        st.plotly_chart(fig, use_container_width=True)


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
