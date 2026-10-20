"""Backtest performance metrics: CAGR, Sharpe, Sortino, Calmar, Information Ratio, Tracking Error, Rolling Returns."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from analytics.portfolio_risk import compute_return_series_risk_metrics


def compute_backtest_metrics(
    portfolio_nav: pd.Series,
    gross_nav: pd.Series,
    benchmark_nav: pd.Series | None = None,
    rebalance_events: list[dict[str, Any]] | None = None,
    risk_free_rate_pct: float = 6.8,
) -> dict[str, Any]:
    """Compute full institutional backtest statistics from net/gross NAV series and benchmark NAV."""
    if portfolio_nav is None or len(portfolio_nav) < 5:
        return {
            "total_return_pct": 0.0,
            "gross_total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "gross_cagr_pct": 0.0,
            "annualised_volatility_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_daily_pct": 0.0,
            "win_rate_monthly_pct": 0.0,
            "annualised_turnover_pct": 0.0,
            "total_transaction_cost_drag_pct": 0.0,
            "information_ratio": None,
            "tracking_error_pct": None,
            "benchmark_cagr_pct": None,
            "active_return_cagr_pct": None,
        }

    net_rets = portfolio_nav.pct_change().dropna()
    gross_rets = gross_nav.pct_change().dropna()
    bench_rets = benchmark_nav.pct_change().dropna() if (benchmark_nav is not None and len(benchmark_nav) >= 5) else None

    base_risk = compute_return_series_risk_metrics(
        net_rets,
        benchmark_returns=bench_rets,
        risk_free_rate_annual_pct=risk_free_rate_pct,
    )
    gross_risk = compute_return_series_risk_metrics(
        gross_rets,
        risk_free_rate_annual_pct=risk_free_rate_pct,
    )

    total_ret_pct = ((float(portfolio_nav.iloc[-1]) / float(portfolio_nav.iloc[0])) - 1.0) * 100.0
    gross_total_ret_pct = ((float(gross_nav.iloc[-1]) / float(gross_nav.iloc[0])) - 1.0) * 100.0
    tx_drag_cagr = round(gross_risk["annualised_return_pct"] - base_risk["annualised_return_pct"], 2)

    win_daily = round(float((net_rets > 0).mean() * 100.0), 2) if len(net_rets) > 0 else 0.0

    # Monthly win rate
    nav_dt = portfolio_nav.copy()
    nav_dt.index = pd.to_datetime(nav_dt.index)
    monthly_nav = nav_dt.resample("ME").last().dropna()
    monthly_rets = monthly_nav.pct_change().dropna()
    win_monthly = round(float((monthly_rets > 0).mean() * 100.0), 2) if len(monthly_rets) > 0 else win_daily

    # Turnover from rebalance events
    years = max(len(net_rets) / 252.0, 0.25)
    events = rebalance_events or []
    total_one_way_turnover = sum(float(e.get("one_way_turnover_pct", 0.0)) for e in events)
    ann_turnover = round(total_one_way_turnover / years, 2)

    info_ratio: float | None = None
    tracking_err_pct: float | None = None
    bench_cagr_pct: float | None = None
    active_cagr_pct: float | None = None

    if bench_rets is not None and len(bench_rets) >= 10:
        b_risk = compute_return_series_risk_metrics(bench_rets, risk_free_rate_annual_pct=risk_free_rate_pct)
        bench_cagr_pct = b_risk["annualised_return_pct"]
        active_cagr_pct = round(base_risk["annualised_return_pct"] - bench_cagr_pct, 2)

        aligned = pd.concat([net_rets.rename("p"), bench_rets.rename("b")], axis=1).dropna()
        if len(aligned) >= 10:
            active_daily = aligned["p"] - aligned["b"]
            te_daily = float(active_daily.std(ddof=1))
            if te_daily > 1e-9:
                tracking_err_pct = round(te_daily * np.sqrt(252.0) * 100.0, 2)
                info_ratio = round((float(active_daily.mean()) * 252.0) / (te_daily * np.sqrt(252.0)), 2)

    return {
        "total_return_pct": round(total_ret_pct, 2),
        "gross_total_return_pct": round(gross_total_ret_pct, 2),
        "cagr_pct": base_risk["annualised_return_pct"],
        "gross_cagr_pct": gross_risk["annualised_return_pct"],
        "annualised_volatility_pct": base_risk["annualised_volatility_pct"],
        "sharpe_ratio": base_risk["sharpe_ratio"],
        "sortino_ratio": base_risk["sortino_ratio"],
        "calmar_ratio": base_risk["calmar_ratio"],
        "max_drawdown_pct": base_risk["max_drawdown_pct"],
        "max_drawdown_duration_days": base_risk["max_drawdown_duration_days"],
        "beta_vs_benchmark": base_risk["beta_vs_benchmark"],
        "historical_var_95_daily_pct": base_risk["historical_var_95_daily_pct"],
        "cvar_95_daily_pct": base_risk["cvar_95_daily_pct"],
        "win_rate_daily_pct": win_daily,
        "win_rate_monthly_pct": win_monthly,
        "annualised_turnover_pct": ann_turnover,
        "total_transaction_cost_drag_pct": tx_drag_cagr,
        "information_ratio": info_ratio,
        "tracking_error_pct": tracking_err_pct,
        "benchmark_cagr_pct": bench_cagr_pct,
        "active_return_cagr_pct": active_cagr_pct,
    }


def compute_rolling_returns(nav_series: pd.Series, window_days: int = 252) -> pd.Series:
    """Compute rolling window percentage returns (e.g., 252 trading days = 1Y, 756 = 3Y)."""
    if nav_series is None or len(nav_series) <= window_days:
        return pd.Series(dtype=float)
    return ((nav_series / nav_series.shift(window_days)) - 1.0) * 100.0
