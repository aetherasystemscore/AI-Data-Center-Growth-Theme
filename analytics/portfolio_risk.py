"""Portfolio risk analytics: VaR, CVaR/Expected Shortfall, factor decomposition, drawdown duration, and stress testing."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


STRESS_SCENARIOS: dict[str, dict[str, Any]] = {
    "2020_MARKET_CRASH": {
        "name": "2020 COVID Liquidity Shock (-35% Broad Market)",
        "description": "Sharp liquidity-driven market sell-off with small-cap and high-beta industrial drawdowns.",
        "category_shocks_pct": {
            "A_COMPUTE_HARDWARE": -34.0,
            "B_ELECTRONIC_COMPONENTS": -38.0,
            "C_DATACENTRE_INFRA": -30.0,
            "D_POWER_AND_GRID": -28.0,
            "E_COOLING_THERMAL": -32.0,
            "F_CONNECTIVITY_FIBRE": -26.0,
            "G_ENTERPRISE_AI_IT": -24.0,
            "H_CIRCULAR_ELECTRONICS": -45.0,
        },
    },
    "2022_RATE_HIKE_TECH_DRAWDOWN": {
        "name": "2022 Global Rate Hike & High-P/E Multiple Compression",
        "description": "250+ bps global yield spike compressing >50x P/E growth multiples and IT spending.",
        "category_shocks_pct": {
            "A_COMPUTE_HARDWARE": -28.0,
            "B_ELECTRONIC_COMPONENTS": -25.0,
            "C_DATACENTRE_INFRA": -22.0,
            "D_POWER_AND_GRID": -10.0,
            "E_COOLING_THERMAL": -16.0,
            "F_CONNECTIVITY_FIBRE": -18.0,
            "G_ENTERPRISE_AI_IT": -30.0,
            "H_CIRCULAR_ELECTRONICS": -28.0,
        },
    },
    "AI_CAPEX_DIGESTION_SLOWDOWN": {
        "name": "Hyperscale AI Capex Digestion (-30% GPU/Server Order Pause)",
        "description": "Hyperscalers pause new GPU cluster orders for 4 quarters while digesting existing capacity.",
        "category_shocks_pct": {
            "A_COMPUTE_HARDWARE": -42.0,
            "B_ELECTRONIC_COMPONENTS": -26.0,
            "C_DATACENTRE_INFRA": -32.0,
            "D_POWER_AND_GRID": -14.0,
            "E_COOLING_THERMAL": -22.0,
            "F_CONNECTIVITY_FIBRE": -18.0,
            "G_ENTERPRISE_AI_IT": -12.0,
            "H_CIRCULAR_ELECTRONICS": -8.0,  # Refurbishment/ITAD resilient during capex optimization
        },
    },
    "POWER_GRID_INTERCONNECTION_DELAY": {
        "name": "Grid Interconnection & Transformer Bottleneck Delay",
        "description": "CRGO steel shortage and substation clearance delays push colocation commissioning out by 12M.",
        "category_shocks_pct": {
            "A_COMPUTE_HARDWARE": -18.0,
            "B_ELECTRONIC_COMPONENTS": -14.0,
            "C_DATACENTRE_INFRA": -28.0,
            "D_POWER_AND_GRID": -12.0,
            "E_COOLING_THERMAL": -16.0,
            "F_CONNECTIVITY_FIBRE": -10.0,
            "G_ENTERPRISE_AI_IT": -6.0,
            "H_CIRCULAR_ELECTRONICS": -10.0,
        },
    },
    "RUPEE_DEPRECIATION_IMPORT_SHOCK": {
        "name": "INR Depreciation (+8% USD/INR) & Imported Component Cost Spike",
        "description": "Sharp Rupee depreciation raises imported wafer/GPU/PCB laminate costs while aiding IT/generator exporters.",
        "category_shocks_pct": {
            "A_COMPUTE_HARDWARE": -14.0,
            "B_ELECTRONIC_COMPONENTS": -16.0,
            "C_DATACENTRE_INFRA": -12.0,
            "D_POWER_AND_GRID": -6.0,
            "E_COOLING_THERMAL": -10.0,
            "F_CONNECTIVITY_FIBRE": -8.0,
            "G_ENTERPRISE_AI_IT": +8.0,  # USD revenue beneficiary
            "H_CIRCULAR_ELECTRONICS": +4.0,  # Domestic metal recovery value rises in INR
        },
    },
    "SMALL_CAP_LIQUIDITY_FREEZE": {
        "name": "Small/Mid-Cap Liquidity Freeze & Mutual Fund Stress Test",
        "description": "Sharp outflow from small-cap funds triggering 25-40% drawdowns in low-turnover names.",
        "category_shocks_pct": {
            "A_COMPUTE_HARDWARE": -24.0,
            "B_ELECTRONIC_COMPONENTS": -32.0,
            "C_DATACENTRE_INFRA": -22.0,
            "D_POWER_AND_GRID": -16.0,
            "E_COOLING_THERMAL": -20.0,
            "F_CONNECTIVITY_FIBRE": -24.0,
            "G_ENTERPRISE_AI_IT": -12.0,
            "H_CIRCULAR_ELECTRONICS": -38.0,
        },
    },
}


def compute_return_series_risk_metrics(
    daily_returns: pd.Series,
    benchmark_returns: pd.Series | None = None,
    risk_free_rate_annual_pct: float = 6.8,
) -> dict[str, Any]:
    """Compute comprehensive quantitative risk metrics from a daily return series."""
    clean = daily_returns.dropna().astype(float)
    n = len(clean)
    if n < 5:
        return {
            "annualised_return_pct": 0.0,
            "annualised_volatility_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_duration_days": 0,
            "beta_vs_benchmark": None,
            "historical_var_95_daily_pct": 0.0,
            "historical_var_99_daily_pct": 0.0,
            "parametric_var_95_daily_pct": 0.0,
            "cvar_95_daily_pct": 0.0,
        }

    rf_daily = (risk_free_rate_annual_pct / 100.0) / 252.0
    cum_wealth = (1.0 + clean).cumprod()
    total_ret = float(cum_wealth.iloc[-1]) - 1.0
    years = max(n / 252.0, 1.0 / 252.0)
    cagr = ((1.0 + total_ret) ** (1.0 / years) - 1.0) if (1.0 + total_ret) > 0 else -1.0

    vol_daily = float(clean.std(ddof=1))
    vol_ann = vol_daily * np.sqrt(252.0)

    excess_daily = clean - rf_daily
    sharpe = (float(excess_daily.mean()) / vol_daily) * np.sqrt(252.0) if vol_daily > 1e-9 else 0.0

    downside = clean[clean < rf_daily] - rf_daily
    downside_std = float(np.sqrt(np.mean(np.square(downside)))) if len(downside) > 0 else 0.0
    sortino = (float(excess_daily.mean()) / downside_std) * np.sqrt(252.0) if downside_std > 1e-9 else 0.0

    running_peak = cum_wealth.cummax()
    dd_series = (cum_wealth / running_peak) - 1.0
    max_dd = float(dd_series.min())
    calmar = (cagr / abs(max_dd)) if abs(max_dd) > 1e-6 else 0.0

    # Max drawdown duration in trading days
    is_underwater = dd_series < -1e-6
    max_dur = 0
    cur_dur = 0
    for uw in is_underwater:
        if uw:
            cur_dur += 1
            max_dur = max(max_dur, cur_dur)
        else:
            cur_dur = 0

    # Historical & Parametric VaR and CVaR (Expected Shortfall)
    hist_var_95 = float(np.percentile(clean, 5))
    hist_var_99 = float(np.percentile(clean, 1))
    param_var_95 = float(clean.mean() - 1.64485 * vol_daily)
    tail_95 = clean[clean <= hist_var_95]
    cvar_95 = float(tail_95.mean()) if len(tail_95) > 0 else hist_var_95

    beta: float | None = None
    if benchmark_returns is not None and len(benchmark_returns.dropna()) >= 10:
        aligned = pd.concat([clean.rename("p"), benchmark_returns.rename("b")], axis=1).dropna()
        if len(aligned) >= 10 and float(aligned["b"].var(ddof=1)) > 1e-10:
            cov = float(np.cov(aligned["p"], aligned["b"], ddof=1)[0, 1])
            beta = round(cov / float(aligned["b"].var(ddof=1)), 2)

    return {
        "annualised_return_pct": round(cagr * 100.0, 2),
        "annualised_volatility_pct": round(vol_ann * 100.0, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "max_drawdown_duration_days": int(max_dur),
        "beta_vs_benchmark": beta,
        "historical_var_95_daily_pct": round(hist_var_95 * 100.0, 2),
        "historical_var_99_daily_pct": round(hist_var_99 * 100.0, 2),
        "parametric_var_95_daily_pct": round(param_var_95 * 100.0, 2),
        "cvar_95_daily_pct": round(cvar_95 * 100.0, 2),
    }


def run_portfolio_stress_tests(
    weights: dict[str, float],
    securities_map: dict[str, dict[str, Any]],
    fundamentals_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Simulate portfolio drawdown under each historical and thematic stress scenario."""
    total_w = sum(v for v in weights.values() if v > 0)
    if total_w <= 0:
        return []
    norm_w = {k.upper(): (v / total_w) for k, v in weights.items() if v > 0}

    results: list[dict[str, Any]] = []
    for code, scen in STRESS_SCENARIOS.items():
        shocks = scen["category_shocks_pct"]
        port_impact = 0.0
        worst_contributor = ""
        worst_contrib_val = 0.0

        for sym, w_frac in norm_w.items():
            sec = securities_map.get(sym, {})
            f = fundamentals_map.get(sym, {})
            cat = sec.get("primary_category", "D_POWER_AND_GRID")
            base_shock = shocks.get(cat, -20.0)

            # Adjust shock for valuation multiple and liquidity
            pe = f.get("trailing_pe")
            if code == "2022_RATE_HIKE_TECH_DRAWDOWN" and pe is not None and pe > 65.0:
                base_shock -= 8.0
            adv = f.get("avg_daily_turnover_inr_cr")
            if code == "SMALL_CAP_LIQUIDITY_FREEZE" and adv is not None and adv < 10.0:
                base_shock -= 10.0

            contrib = w_frac * base_shock
            port_impact += contrib
            if contrib < worst_contrib_val:
                worst_contrib_val = contrib
                worst_contributor = sym

        results.append(
            {
                "scenario_code": code,
                "scenario_name": scen["name"],
                "description": scen["description"],
                "estimated_portfolio_return_pct": round(port_impact, 2),
                "largest_drag_symbol": worst_contributor,
                "largest_drag_contribution_pct": round(worst_contrib_val, 2),
            }
        )
    return results
