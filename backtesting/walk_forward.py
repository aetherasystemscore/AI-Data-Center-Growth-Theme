"""Walk-forward validation module separating In-Sample (training) and Out-of-Sample (testing) windows."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backtesting.engine import BacktestConfig, PointInTimeBacktestEngine


def run_walk_forward_validation(
    symbols: list[str],
    start_date: date,
    end_date: date,
    in_sample_months: int = 12,
    out_of_sample_months: int = 6,
    optimisation_method: str = "MAXIMUM_SHARPE",
    engine: PointInTimeBacktestEngine | None = None,
) -> list[dict[str, Any]]:
    """Run rolling In-Sample / Out-of-Sample walk-forward evaluation windows."""
    bt_engine = engine or PointInTimeBacktestEngine()
    windows: list[dict[str, Any]] = []

    cursor = start_date
    in_days = in_sample_months * 30
    out_days = out_of_sample_months * 30

    fold = 1
    while True:
        is_end = cursor + timedelta(days=in_days)
        oos_start = is_end + timedelta(days=1)
        oos_end = oos_start + timedelta(days=out_days)
        if oos_end > end_date:
            oos_end = end_date
        if (oos_end - oos_start).days < 30:
            break

        is_cfg = BacktestConfig(
            start_date=cursor,
            end_date=is_end,
            rebalance_frequency="QUARTERLY",
            optimisation_method=optimisation_method,
        )
        is_res = bt_engine.run_backtest(symbols=symbols, config=is_cfg)
        learned_weights = is_res.get("final_weights", {})

        oos_cfg = BacktestConfig(
            start_date=oos_start,
            end_date=oos_end,
            rebalance_frequency="QUARTERLY",
            optimisation_method=optimisation_method,
        )
        oos_res = bt_engine.run_backtest(
            symbols=symbols,
            config=oos_cfg,
            custom_target_weights=learned_weights if learned_weights else None,
        )

        windows.append(
            {
                "fold": fold,
                "in_sample_period": f"{cursor.isoformat()} to {is_end.isoformat()}",
                "out_of_sample_period": f"{oos_start.isoformat()} to {oos_end.isoformat()}",
                "in_sample_cagr_pct": is_res["metrics"]["cagr_pct"],
                "in_sample_sharpe": is_res["metrics"]["sharpe_ratio"],
                "out_of_sample_cagr_pct": oos_res["metrics"]["cagr_pct"],
                "out_of_sample_sharpe": oos_res["metrics"]["sharpe_ratio"],
                "out_of_sample_max_dd_pct": oos_res["metrics"]["max_drawdown_pct"],
            }
        )
        fold += 1
        cursor = cursor + timedelta(days=out_days)
        if oos_end >= end_date:
            break

    return windows
