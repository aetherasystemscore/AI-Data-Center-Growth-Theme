"""Point-in-time backtesting engine with listing-date guards, fundamental reporting lags, and next-open execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from analytics.exposure_scoring import score_company_exposure
from analytics.portfolio_optimisation import optimise_portfolio_weights
from backtesting.metrics import compute_backtest_metrics, compute_rolling_returns
from core.schemas import OptimisationMethod, ScoringProfile
from data.ingestion import DataIngestionService
from portfolio.rebalancing import IndianTransactionCostConfig, estimate_trade_cost_inr


@dataclass
class BacktestConfig:
    """Configuration for a point-in-time portfolio backtest."""

    start_date: date
    end_date: date
    initial_capital_inr: float = 1_000_000.0
    rebalance_frequency: str = "QUARTERLY"  # MONTHLY, QUARTERLY, SEMI_ANNUAL, ANNUAL
    optimisation_method: str = OptimisationMethod.CONVICTION_WEIGHT.value
    scoring_profile: str = ScoringProfile.DEFAULT_100PT.value
    fundamental_lag_days: int = 60  # 60-90 day lag after reporting period before fundamentals are tradable
    execute_at_next_open: bool = True  # Signal at close(t), execute at open(t+1)
    max_single_stock_pct: float = 12.0
    max_subsector_pct: float = 35.0
    benchmark_symbol: str = "NIFTYBEES"


class PointInTimeBacktestEngine:
    """Executes survivorship-aware, point-in-time portfolio backtests with realistic Indian delivery costs."""

    def __init__(self, ingestion: DataIngestionService | None = None) -> None:
        self.ingestion = ingestion or DataIngestionService()
        self.repo = self.ingestion.repo
        self._series_cache: dict[tuple[str, date, date], tuple[pd.Series | None, pd.Series | None, list[str]]] = {}

    @staticmethod
    def is_security_eligible_at_date(
        sec: dict[str, Any],
        as_of_date: date,
        fundamental_reporting_date: date | None = None,
        fundamental_lag_days: int = 0,
    ) -> bool:
        """Verify that a security was actively listed on `as_of_date` and its fundamental filing lag has elapsed."""
        if not sec.get("is_investable", True):
            return False
        ld_str = sec.get("listing_date")
        if ld_str:
            try:
                ld = datetime.strptime(ld_str, "%Y-%m-%d").date()
                if as_of_date < ld:
                    return False
            except ValueError:
                pass
        eff_to = sec.get("effective_to")
        if eff_to:
            try:
                et = datetime.strptime(eff_to, "%Y-%m-%d").date()
                if as_of_date > et:
                    return False
            except ValueError:
                pass
        if fundamental_reporting_date is not None and fundamental_lag_days > 0:
            if as_of_date < (fundamental_reporting_date + timedelta(days=fundamental_lag_days)):
                return False
        return True

    def run_backtest(
        self,
        symbols: list[str],
        config: BacktestConfig,
        custom_target_weights: dict[str, float] | None = None,
        tx_cost_config: IndianTransactionCostConfig | None = None,
    ) -> dict[str, Any]:
        """Run a point-in-time backtest across `symbols` from `config.start_date` to `config.end_date`."""
        sec_map = {s["symbol"]: s for s in self.repo.get_securities()}
        f_map = self.repo.get_latest_fundamentals_map()

        clean_syms = [s.strip().upper() for s in symbols if s.strip().upper() in sec_map]
        if not clean_syms:
            raise ValueError("No valid symbols provided for backtest.")

        # Load price histories (open and close) for all candidate symbols
        close_dict: dict[str, pd.Series] = {}
        open_dict: dict[str, pd.Series] = {}
        warnings: list[str] = []

        for sym in clean_syms:
            cache_key = (sym, config.start_date, config.end_date)
            if cache_key in self._series_cache:
                c_ser, o_ser, w_list = self._series_cache[cache_key]
            else:
                res = self.ingestion.get_or_generate_price_history(
                    symbol=sym,
                    start_date=config.start_date,
                    end_date=config.end_date,
                )
                df = res.get("df")
                w_list = list(res.get("warnings", []))
                if df is not None and not df.empty:
                    df_sorted = df.sort_values("trade_date")
                    idx = pd.to_datetime(df_sorted["trade_date"])
                    c_ser = pd.Series(df_sorted["close"].astype(float).values, index=idx)
                    o_ser = pd.Series(df_sorted["open"].astype(float).values, index=idx)
                else:
                    c_ser, o_ser = None, None
                self._series_cache[cache_key] = (c_ser, o_ser, w_list)

            if c_ser is not None and o_ser is not None:
                close_dict[sym] = c_ser
                open_dict[sym] = o_ser
            else:
                warnings.extend(w_list)

        if not close_dict:
            raise ValueError("No price history available in the selected date window.")

        close_df = pd.DataFrame(close_dict).sort_index()
        open_df = pd.DataFrame(open_dict).reindex(close_df.index)

        # Forward-fill missing holiday gaps ONLY after a stock's first valid listing observation
        for sym in close_df.columns:
            first_valid = close_df[sym].first_valid_index()
            if first_valid is not None:
                close_df.loc[first_valid:, sym] = close_df.loc[first_valid:, sym].ffill()
                open_df.loc[first_valid:, sym] = open_df.loc[first_valid:, sym].ffill()

        dates = close_df.index
        n_days = len(dates)
        if n_days < 5:
            raise ValueError("Backtest window must contain at least 5 trading days.")

        rebalance_step = {
            "MONTHLY": 21,
            "QUARTERLY": 63,
            "SEMI_ANNUAL": 126,
            "ANNUAL": 252,
        }.get(config.rebalance_frequency.upper(), 63)

        rebalance_indices = set(range(0, n_days - 1, rebalance_step))

        net_nav = np.zeros(n_days, dtype=float)
        gross_nav = np.zeros(n_days, dtype=float)
        net_nav[0] = config.initial_capital_inr
        gross_nav[0] = config.initial_capital_inr

        current_weights: dict[str, float] = {}
        pending_target_weights: dict[str, float] | None = None
        rebalance_log: list[dict[str, Any]] = []
        skipped_pre_listing: set[str] = set()

        scores_map: dict[str, float] = {}
        for s in clean_syms:
            bd = score_company_exposure(sec_map[s], f_map.get(s, {}), profile=config.scoring_profile)
            scores_map[s] = float(bd.profile_adjusted_score)
        mcaps_map = {s: float(f_map.get(s, {}).get("market_cap_inr_cr") or 10000.0) for s in clean_syms}
        cat_map = {s: sec_map[s].get("primary_category", "OTHER") for s in clean_syms}
        adv_map = {s: float(f_map.get(s, {}).get("avg_daily_turnover_inr_cr") or 20.0) for s in clean_syms}

        for t in range(n_days):
            cur_dt = dates[t].date()

            # 1. If a signal was generated at t-1 close, execute rebalance at today's open (t)
            if pending_target_weights is not None:
                one_way_to, cost_inr = self._execute_rebalance_cost(
                    current_weights=current_weights,
                    target_weights=pending_target_weights,
                    portfolio_value_inr=net_nav[t - 1] if t > 0 else config.initial_capital_inr,
                    adv_map=adv_map,
                    tx_cost_config=tx_cost_config,
                )
                prev_net = net_nav[t - 1] if t > 0 else config.initial_capital_inr
                prev_gross = gross_nav[t - 1] if t > 0 else config.initial_capital_inr

                # Deduct transaction & slippage cost at execution
                post_tx_net = max(1.0, prev_net - cost_inr)
                current_weights = dict(pending_target_weights)
                pending_target_weights = None

                rebalance_log.append(
                    {
                        "execution_date": cur_dt.isoformat(),
                        "active_symbols_count": len(current_weights),
                        "one_way_turnover_pct": round(one_way_to, 2),
                        "transaction_cost_inr": round(cost_inr, 2),
                        "top_holdings": dict(sorted(current_weights.items(), key=lambda x: x[1], reverse=True)[:5]),
                    }
                )
                if t > 0:
                    # Intraday return on execution day: open(t) -> close(t) when execute_at_next_open=True
                    day_ret = self._compute_weighted_return_open_to_close(
                        current_weights, open_df.iloc[t], close_df.iloc[t], close_df.iloc[t - 1], config.execute_at_next_open
                    )
                    net_nav[t] = post_tx_net * (1.0 + day_ret)
                    gross_nav[t] = prev_gross * (1.0 + day_ret)
                else:
                    net_nav[0] = post_tx_net
                    gross_nav[0] = prev_gross
            elif t > 0:
                # Normal holding day: close(t-1) -> close(t)
                day_ret, drifted = self._compute_holding_day_return(
                    current_weights, close_df.iloc[t - 1], close_df.iloc[t]
                )
                net_nav[t] = net_nav[t - 1] * (1.0 + day_ret)
                gross_nav[t] = gross_nav[t - 1] * (1.0 + day_ret)
                current_weights = drifted

            # 2. Check if signal is generated at close of day t for execution on t+1
            if t in rebalance_indices:
                eligible_syms: list[str] = []
                for s in clean_syms:
                    if pd.notna(close_df.iloc[t].get(s)) and self.is_security_eligible_at_date(sec_map[s], cur_dt):
                        eligible_syms.append(s)
                    else:
                        skipped_pre_listing.add(s)

                if eligible_syms:
                    if custom_target_weights:
                        raw_custom = {s: custom_target_weights.get(s, 0.0) for s in eligible_syms if custom_target_weights.get(s, 0.0) > 0}
                        tot_c = sum(raw_custom.values())
                        if tot_c > 0:
                            pending_target_weights = {s: (v / tot_c) * 100.0 for s, v in raw_custom.items()}
                        else:
                            pending_target_weights = {s: 100.0 / len(eligible_syms) for s in eligible_syms}
                    else:
                        opt_syms = list(eligible_syms)
                        eff_max_single = config.max_single_stock_pct
                        if (
                            config.optimisation_method.upper()
                            in (OptimisationMethod.CONVICTION_WEIGHT.value, "CONVICTION_WEIGHTED")
                            and len(eligible_syms) >= 8
                        ):
                            keep_k = max(8, int(round(len(eligible_syms) * 0.65)))
                            opt_syms = [
                                s
                                for s, _ in sorted(
                                    [(sym, scores_map.get(sym, 50.0)) for sym in eligible_syms],
                                    key=lambda item: (item[1], item[0]),
                                    reverse=True,
                                )[:keep_k]
                            ]
                            eff_max_single = max(
                                config.max_single_stock_pct,
                                round((100.0 / max(1, len(opt_syms))) + 3.0, 2),
                            )

                        hist_window = close_df.iloc[max(0, t - 126) : t + 1][opt_syms].pct_change().dropna(how="all")
                        pending_target_weights = optimise_portfolio_weights(
                            symbols=opt_syms,
                            method=config.optimisation_method,
                            returns_df=hist_window if len(hist_window) >= 20 else None,
                            conviction_scores=scores_map,
                            market_caps=mcaps_map,
                            category_map=cat_map,
                            max_single_stock_pct=eff_max_single,
                            max_subsector_pct=config.max_subsector_pct,
                        )

        net_series = pd.Series(net_nav, index=dates, name="Net Portfolio NAV")
        gross_series = pd.Series(gross_nav, index=dates, name="Gross Portfolio NAV")

        # Equal-weight eligible universe benchmark
        ew_rets = close_df.pct_change().mean(axis=1).fillna(0.0)
        ew_rets.iloc[0] = 0.0
        bench_series = config.initial_capital_inr * (1.0 + ew_rets).cumprod()
        bench_series.name = f"Benchmark ({config.benchmark_symbol} / Equal-Weight)"

        metrics = compute_backtest_metrics(
            portfolio_nav=net_series,
            gross_nav=gross_series,
            benchmark_nav=bench_series,
            rebalance_events=rebalance_log,
        )

        if skipped_pre_listing:
            warnings.append(
                f"Point-in-time listing guard held out newly listed stocks prior to their NSE/BSE listing date: {sorted(list(skipped_pre_listing))}"
            )

        return {
            "config": config,
            "net_nav_series": net_series,
            "gross_nav_series": gross_series,
            "benchmark_nav_series": bench_series,
            "rolling_1y_returns_pct": compute_rolling_returns(net_series, 252),
            "metrics": metrics,
            "final_weights": current_weights,
            "rebalance_log": rebalance_log,
            "warnings": warnings,
        }

    @staticmethod
    def _execute_rebalance_cost(
        current_weights: dict[str, float],
        target_weights: dict[str, float],
        portfolio_value_inr: float,
        adv_map: dict[str, float],
        tx_cost_config: IndianTransactionCostConfig | None = None,
    ) -> tuple[float, float]:
        all_syms = set(current_weights.keys()) | set(target_weights.keys())
        total_notional = 0.0
        total_cost = 0.0
        for s in all_syms:
            cw = current_weights.get(s, 0.0)
            tw = target_weights.get(s, 0.0)
            delta = tw - cw
            if abs(delta) < 0.05:
                continue
            notional = abs(delta / 100.0) * portfolio_value_inr
            side = "BUY" if delta > 0 else "SELL"
            c_info = estimate_trade_cost_inr(
                notional_inr=notional,
                side=side,
                avg_daily_turnover_inr_cr=adv_map.get(s, 20.0),
                config=tx_cost_config,
            )
            total_notional += notional
            total_cost += c_info["total_cost_inr"]
        one_way_to = (total_notional / (2.0 * max(1.0, portfolio_value_inr))) * 100.0
        return one_way_to, total_cost

    @staticmethod
    def _compute_weighted_return_open_to_close(
        weights: dict[str, float],
        open_row: pd.Series,
        close_row: pd.Series,
        prev_close_row: pd.Series,
        execute_at_next_open: bool,
    ) -> float:
        port_ret = 0.0
        for s, w_pct in weights.items():
            if w_pct <= 0:
                continue
            c_now = close_row.get(s)
            ref = open_row.get(s) if execute_at_next_open else prev_close_row.get(s)
            if pd.notna(c_now) and pd.notna(ref) and float(ref) > 0:
                r = (float(c_now) / float(ref)) - 1.0
                port_ret += (w_pct / 100.0) * r
        return port_ret

    @staticmethod
    def _compute_holding_day_return(
        weights: dict[str, float],
        prev_close_row: pd.Series,
        close_row: pd.Series,
    ) -> tuple[float, dict[str, float]]:
        if not weights:
            return 0.0, {}
        new_vals: dict[str, float] = {}
        port_ret = 0.0
        for s, w_pct in weights.items():
            if w_pct <= 0:
                continue
            c0 = prev_close_row.get(s)
            c1 = close_row.get(s)
            if pd.notna(c0) and pd.notna(c1) and float(c0) > 0:
                r = (float(c1) / float(c0)) - 1.0
            else:
                r = 0.0
            port_ret += (w_pct / 100.0) * r
            new_vals[s] = w_pct * (1.0 + r)
        tot = sum(new_vals.values())
        drifted = {s: (v / tot) * 100.0 for s, v in new_vals.items()} if tot > 0 else dict(weights)
        return port_ret, drifted
