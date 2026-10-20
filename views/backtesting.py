"""Page 10: Point-in-Time Backtesting & Walk-Forward Validation Suite (Section 16 of Master Prompt)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_PAGES_DIR = str(Path(__file__).resolve().parent)
if _PAGES_DIR in sys.path:
    sys.path.remove(_PAGES_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backtesting.engine import BacktestConfig, PointInTimeBacktestEngine
from backtesting.walk_forward import run_walk_forward_validation
from core.schemas import OptimisationMethod, ScoringProfile
from data.ingestion import DataIngestionService
from database.repository import AI3Repository
from portfolio.paper_trading import rank_scoring_profiles_5y


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("⏱️ Point-in-Time Backtesting & Walk-Forward Validation Suite")
    st.markdown(
        "**Survivorship-aware, point-in-time backtesting** enforcing exact listing dates (newly listed stocks like `NETWEB`, `CYIENTDLM`, `AVALON`, `RRKABEL` "
        "only enter the eligible universe after their listing date), 60-day fundamental reporting lags, next-bar open execution, and Indian statutory delivery costs."
    )

    with st.expander("ℹ️ What is the Purpose of Tab 10 (Point-in-Time Backtesting)? — Click to Read", expanded=True):
        st.markdown(
            """
            **Why Tab 10 Exists:**
            Most retail backtests suffer from **look-ahead bias** and **IPO backfilling bias** — they accidentally include newly listed AI/EMS winners (such as `NETWEB` listed in July 2023 or `KAYNES` listed in Nov 2022) in a 2021 portfolio before those stocks even traded on NSE/BSE, or use FY financials before the quarterly results were publicly filed.

            **How Tab 10 Solves This:**
            1. **Strict Listing-Date Gatekeeper (`Point-in-Time Eligibility`):** On every historical rebalance date $t$, the engine checks each stock's exact NSE/BSE `listing_date`. Any company not yet listed on date $t$ is strictly excluded from that rebalance and only enters the investable universe on the first rebalance *after* its IPO listing.
            2. **60-Day Fundamental Reporting Lag:** Financial ratios and AI revenue disclosures are lagged by 60 days after quarter/year-end so the strategy never trades on unreleased earnings.
            3. **Next-Day Open Execution & Indian Delivery Friction:** Signals generated at rebalance close $t$ are executed at the next trading day's price ($t+1$) after deducting Indian statutory delivery costs (`STT 0.10%`, `Stamp Duty 0.015%`, `Exchange/SEBI/GST`, and liquidity-scaled slippage).
            4. **Rolling Walk-Forward Validation (`12M In-Sample / 6M Out-of-Sample`):** Tests whether the chosen allocation strategy (`CONVICTION_WEIGHTED`, `EQUAL_WEIGHT`, `INVERSE_VOLATILITY`, `RISK_PARITY`, etc.) continues to outperform an equal-weight benchmark in unseen future windows.
            """
        )

    all_secs = repo.get_securities(geography="INDIA", investable_only=True)
    avail_syms = [s["symbol"] for s in all_secs]
    default_bt_syms = [
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
        "BLUESTARCO",
        "ANANTRAJ",
        "PERSISTENT",
    ]
    default_bt_syms = [s for s in default_bt_syms if s in avail_syms]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        start_dt = st.date_input("Start Date", value=date(2022, 1, 3), min_value=date(2019, 1, 1), max_value=date(2025, 12, 31))
    with c2:
        end_dt = st.date_input("End Date", value=date(2026, 3, 31), min_value=date(2022, 6, 1), max_value=date.today())
    with c3:
        reb_freq = st.selectbox("Rebalance Frequency", ["QUARTERLY", "MONTHLY", "SEMI_ANNUAL", "ANNUAL"], index=0)
    with c4:
        opt_method = st.selectbox("Allocation Strategy", [m.value for m in OptimisationMethod], index=1)

    selected_syms = st.multiselect("Backtest Universe Candidates", options=avail_syms, default=default_bt_syms)
    if len(selected_syms) < 2:
        st.warning("Select at least 2 symbols to run the backtest.")
        return

    active_profile = st.session_state.get("active_scoring_profile", ScoringProfile.HIGH_GROWTH_INFRA.value)
    engine = PointInTimeBacktestEngine(ingestion=ingestion)
    cfg = BacktestConfig(
        start_date=start_dt,
        end_date=end_dt,
        initial_capital_inr=1_000_000.0,
        rebalance_frequency=reb_freq,
        optimisation_method=opt_method,
        scoring_profile=active_profile,
        fundamental_lag_days=60,
        execute_at_next_open=True,
    )

    res = engine.run_backtest(symbols=selected_syms, config=cfg)
    m = res["metrics"]

    with st.expander("🏆 5-Year Return Leaderboard Across All 9 Scoring Profiles (Why `HIGH_GROWTH_INFRA` is Default)", expanded=False):
        prof_rank = rank_scoring_profiles_5y(repo=repo, ingestion=ingestion)
        st.dataframe(pd.DataFrame(prof_rank["leaderboard"]), use_container_width=True, hide_index=True)

    for w in res["warnings"]:
        st.info(f"ℹ️ **Point-in-Time Guard:** {w}")

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Net CAGR (%)", f"{m['cagr_pct']}%", f"Gross: {m['gross_cagr_pct']}%")
    k2.metric("Benchmark CAGR (%)", f"{m['benchmark_cagr_pct']}%" if m["benchmark_cagr_pct"] is not None else "N/A", f"Active: {m['active_return_cagr_pct']}%")
    k3.metric("Sharpe / Sortino", f"{m['sharpe_ratio']}", f"Sortino: {m['sortino_ratio']}")
    k4.metric("Max Drawdown (%)", f"{m['max_drawdown_pct']}%", f"Calmar: {m['calmar_ratio']}")
    k5.metric("Information Ratio", f"{m['information_ratio']}" if m["information_ratio"] is not None else "N/A", f"TE: {m['tracking_error_pct']}%")
    k6.metric("Annual Turnover", f"{m['annualised_turnover_pct']}%", f"Tx Cost Drag: {m['total_transaction_cost_pct'] if 'total_transaction_cost_pct' in m else m['total_transaction_cost_drag_pct']}%/yr")

    # Equity curve plot
    fig_nav = go.Figure()
    fig_nav.add_trace(
        go.Scatter(x=res["net_nav_series"].index, y=res["net_nav_series"].values, name="Net Portfolio NAV (Post-Cost)", line=dict(width=2.5))
    )
    fig_nav.add_trace(
        go.Scatter(x=res["gross_nav_series"].index, y=res["gross_nav_series"].values, name="Gross Portfolio NAV (Pre-Cost)", line=dict(dash="dot"))
    )
    fig_nav.add_trace(
        go.Scatter(x=res["benchmark_nav_series"].index, y=res["benchmark_nav_series"].values, name="Equal-Weight Universe Benchmark", line=dict(dash="dash"))
    )
    fig_nav.update_layout(
        title="Cumulative NAV Growth (Initial Capital = Rs 10,00,000)",
        height=420,
        margin=dict(t=40, l=10, r=10, b=10),
    )
    st.plotly_chart(fig_nav, use_container_width=True)

    col_log, col_wf = st.columns([1, 1])
    with col_log:
        st.subheader("Point-in-Time Rebalance Execution Log")
        st.dataframe(pd.DataFrame(res["rebalance_log"]), use_container_width=True, hide_index=True)

    with col_wf:
        st.subheader("Walk-Forward Validation (In-Sample vs Out-of-Sample)")
        if st.button("Run Rolling Walk-Forward Analysis (12M IS / 6M OOS)"):
            wf_rows = run_walk_forward_validation(
                symbols=selected_syms,
                start_date=start_dt,
                end_date=end_dt,
                in_sample_months=12,
                out_of_sample_months=6,
                optimisation_method=opt_method,
                engine=engine,
            )
            st.dataframe(pd.DataFrame(wf_rows), use_container_width=True, hide_index=True)


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
