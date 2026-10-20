"""Page 9: Portfolio Construction, Optimisation & Risk Stress-Test Engine (Sections 14-15 of Master Prompt)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.exposure_scoring import score_company_exposure
from analytics.portfolio_optimisation import optimise_portfolio_weights
from analytics.portfolio_risk import run_portfolio_stress_tests
from core.schemas import OptimisationMethod
from data.ingestion import DataIngestionService
from database.repository import AI3Repository
from portfolio.basket_builder import build_portfolio_summary
from portfolio.rebalancing import compute_rebalance_trades


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("⚖️ Portfolio Construction, Optimisation & Stress-Test Engine")
    st.markdown(
        "Construct and optimise multi-sector AI infrastructure portfolios using **8 quantitative allocation methods**, "
        "single-stock and subsector concentration caps, Indian delivery transaction-cost estimates, and **6 stress scenarios**."
    )

    profile = st.session_state.get("active_scoring_profile", "DEFAULT_100PT")
    all_secs = repo.get_securities(geography="INDIA", investable_only=True)
    f_map = repo.get_latest_fundamentals_map()
    sec_map = {s["symbol"]: s for s in repo.get_securities()}

    default_basket = [
        "POWERGRID",
        "HITACHIEN",
        "CGPOWER",
        "TRIL",
        "TDPOWERSYS",
        "CUMMINSIND",
        "KIRLOSENG",
        "POLYCAB",
        "APARINDS",
        "NETWEB",
        "KAYNES",
        "SYRMA",
        "BLUESTARCO",
        "ANANTRAJ",
        "PERSISTENT",
    ]
    avail_syms = [s["symbol"] for s in all_secs]
    default_sel = [s for s in default_basket if s in avail_syms]

    col_c1, col_c2, col_c3, col_c4 = st.columns([2, 1, 1, 1])
    with col_c1:
        selected_syms = st.multiselect(
            "Select Investable Indian Equities (Minimum 5 Recommended)",
            options=avail_syms,
            default=default_sel,
        )
    with col_c2:
        opt_method = st.selectbox(
            "Optimisation Method",
            options=[m.value for m in OptimisationMethod],
            index=1,
        )
    with col_c3:
        max_stock_cap = st.slider("Max Single-Stock Cap (%)", 5.0, 25.0, 10.0, 1.0)
    with col_c4:
        max_sector_cap = st.slider("Max Subsector Cap (%)", 20.0, 50.0, 30.0, 5.0)

    if len(selected_syms) < 2:
        st.warning("Select at least 2 securities to run portfolio optimisation.")
        return

    scores_map = {
        s: score_company_exposure(sec_map[s], f_map.get(s, {}), profile=profile).profile_adjusted_score
        for s in selected_syms
    }
    mcaps_map = {s: float(f_map.get(s, {}).get("market_cap_inr_cr") or 10000.0) for s in selected_syms}
    cat_map = {s: sec_map[s].get("primary_category", "OTHER") for s in selected_syms}

    weights = optimise_portfolio_weights(
        symbols=selected_syms,
        method=opt_method,
        conviction_scores=scores_map,
        market_caps=mcaps_map,
        category_map=cat_map,
        max_single_stock_pct=max_stock_cap,
        max_subsector_pct=max_sector_cap,
    )

    summary = build_portfolio_summary(weights, sec_map, f_map, profile=profile)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Weighted AI Exposure Score", f"{summary['weighted_ai_exposure_score']}/100")
    m2.metric("Weighted Direct AI/DC Rev", f"{summary['weighted_direct_ai_rev_pct']}%")
    m3.metric("Portfolio Harmonic/Weighted P/E", f"{summary['weighted_pe']}x" if summary["weighted_pe"] else "N/A")
    m4.metric("Portfolio Weighted ROCE", f"{summary['weighted_roce_pct']}%" if summary["weighted_roce_pct"] else "N/A")

    if summary["constraint_violations"]:
        for v in summary["constraint_violations"]:
            st.warning(v)

    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.subheader(f"Optimised Holdings (`{opt_method}`)")
        df_hold = pd.DataFrame(summary["holdings"])
        st.dataframe(df_hold, use_container_width=True, hide_index=True)

    with col_r:
        st.subheader("Value-Chain Category Allocation")
        cat_df = pd.DataFrame(
            [{"Category": k, "Weight (%)": v} for k, v in summary["category_weights"].items()]
        ).sort_values("Weight (%)", ascending=False)
        fig_pie = px.bar(cat_df, x="Weight (%)", y="Category", orientation="h", color="Weight (%)")
        fig_pie.update_layout(height=360, margin=dict(t=20, l=10, r=10, b=10))
        st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()
    st.subheader("🌩️ Historical & Thematic Portfolio Stress Scenarios")
    stress_results = run_portfolio_stress_tests(weights, sec_map, f_map)
    st.dataframe(pd.DataFrame(stress_results), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("💱 Rebalance & Indian Delivery Transaction Cost Simulator")
    cap_inr = st.number_input("Portfolio Notional Capital (Rs)", min_value=100000.0, value=1000000.0, step=100000.0)
    adv_map = {s: float(f_map.get(s, {}).get("avg_daily_turnover_inr_cr") or 20.0) for s in selected_syms}
    reb = compute_rebalance_trades(
        current_weights={},  # Initial deployment from 100% cash
        target_weights=weights,
        portfolio_value_inr=cap_inr,
        turnover_map_cr=adv_map,
    )
    st.caption(
        f"**Initial Deployment Cost (STT 0.10% + Stamp Duty 0.015% + Exchange/SEBI/GST + Liquidity Slippage):** "
        f"`Rs {reb['total_transaction_cost_inr']:,.2f}` (`{(reb['total_transaction_cost_inr'] / cap_inr) * 100:.3f}%` of capital)"
    )
    st.dataframe(pd.DataFrame(reb["trades"]), use_container_width=True, hide_index=True)
