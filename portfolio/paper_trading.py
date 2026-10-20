"""Automated 3:00 PM IST Daily Working-Day Paper-Trading Engine & 5-Year Historical Verifiable Backtest."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import threading
import time as time_mod
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from analytics.equity_enrichment import compute_enriched_equity_metrics
from analytics.exposure_scoring import score_company_exposure
from analytics.portfolio_optimisation import optimise_portfolio_weights
from backtesting.engine import BacktestConfig, PointInTimeBacktestEngine
from data.ingestion import DataIngestionService
from database.repository import AI3Repository
from portfolio.rebalancing import estimate_trade_cost_inr

IST = ZoneInfo("Asia/Kolkata")

PAPER_LEDGER_PATH = (
    Path(__file__).resolve().parent.parent / "data_store" / "paper_trading_ledger.json"
)

DEFAULT_PAPER_BASKET = [
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

# Standard trading-day horizons requested by user
TIME_HORIZON_SPECS: list[tuple[str, str, int]] = [
    ("1W", "1 Week", 5),
    ("1M", "1 Month", 21),
    ("3M", "3 Months", 63),
    ("6M", "6 Months", 126),
    ("1Y", "1 Year", 252),
    ("2Y", "2 Years", 504),
    ("3Y", "3 Years", 756),
    ("5Y", "5 Years", 1260),
]


def get_ist_now() -> datetime:
    """Return current timestamp in Indian Standard Time (IST, UTC+5:30)."""
    return datetime.now(IST)


def is_working_day(d: date) -> bool:
    """Return True if date d is a weekday (Mon-Fri)."""
    return d.weekday() < 5


def latest_3pm_ist_slot(now_ist: datetime | None = None) -> tuple[date, str]:
    """Determine the most recent eligible 3:00 PM IST working-day execution slot."""
    now_ist = now_ist or get_ist_now()
    cur_date = now_ist.date()
    while not is_working_day(cur_date):
        cur_date -= timedelta(days=1)
    slot_ts = f"{cur_date.isoformat()} 15:00:00 IST"
    return cur_date, slot_ts


def next_3pm_ist_slot(now_ist: datetime | None = None) -> str:
    """Return human-readable timestamp of the next scheduled 3:00 PM IST working-day run."""
    now_ist = now_ist or get_ist_now()
    d = now_ist.date()
    if is_working_day(d) and now_ist.time() < time(15, 0):
        return f"{d.isoformat()} 15:00:00 IST (Today)"
    d += timedelta(days=1)
    while not is_working_day(d):
        d += timedelta(days=1)
    return f"{d.isoformat()} 15:00:00 IST"


def _compute_composite_conviction_weights(
    repo: AI3Repository,
    profile: str = "DEFAULT_100PT",
    max_single_stock_pct: float = 10.0,
    max_subsector_pct: float = 30.0,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    """Compute target weights at 3:00 PM IST using AI Exposure (50%) + Fundamental (30%) + Technical (20%)."""
    all_secs = repo.get_securities(geography="INDIA", investable_only=True)
    f_map = repo.get_latest_fundamentals_map()
    sec_map = {s["symbol"]: s for s in all_secs if s["symbol"] in DEFAULT_PAPER_BASKET}
    if len(sec_map) < 5:
        sec_map = {s["symbol"]: s for s in all_secs}

    syms = sorted(list(sec_map.keys()))
    composite_scores: dict[str, float] = {}
    mcaps: dict[str, float] = {}
    cats: dict[str, str] = {}
    enrichment_by_sym: dict[str, dict[str, Any]] = {}

    for s in syms:
        sec = sec_map[s]
        f = f_map.get(s, {})
        enr = compute_enriched_equity_metrics(sec, f, profile=profile)
        enrichment_by_sym[s] = enr
        comp_score = (
            0.50 * float(enr["profile_adjusted_score"])
            + 0.30 * float(enr["fundamental_score"])
            + 0.20 * float(enr["technical_score"])
        )
        composite_scores[s] = round(comp_score, 2)
        mcaps[s] = float(f.get("market_cap_inr_cr") or 10000.0)
        cats[s] = sec.get("primary_category", "OTHER")

    weights = optimise_portfolio_weights(
        symbols=syms,
        method="CONVICTION_WEIGHTED",
        conviction_scores=composite_scores,
        market_caps=mcaps,
        category_map=cats,
        max_single_stock_pct=max_single_stock_pct,
        max_subsector_pct=max_subsector_pct,
    )
    return weights, enrichment_by_sym


def ensure_paper_trading_ledger(
    repo: AI3Repository,
    ingestion: DataIngestionService,
    initial_capital_inr: float = 1_000_000.0,
    force_run_today: bool = False,
) -> dict[str, Any]:
    """Load or initialize the forward 3:00 PM IST paper-trading ledger starting from today onwards."""
    PAPER_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    now_ist = get_ist_now()
    slot_date, slot_ts = latest_3pm_ist_slot(now_ist)

    if PAPER_LEDGER_PATH.exists() and not force_run_today:
        try:
            ledger = json.loads(PAPER_LEDGER_PATH.read_text(encoding="utf-8"))
            if ledger.get("positions") and ledger.get("nav_history"):
                # Update mark-to-market if a new working day 3 PM IST slot has arrived
                last_recorded = ledger["nav_history"][-1]["date"]
                if last_recorded < slot_date.isoformat():
                    ledger = _append_daily_3pm_mtm(ledger, repo, ingestion, slot_date, slot_ts)
                    PAPER_LEDGER_PATH.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
                return ledger
        except Exception:
            pass

    # Initialize fresh paper-trading book from today's 3:00 PM IST slot
    weights, enr_map = _compute_composite_conviction_weights(repo)
    all_secs = {s["symbol"]: s for s in repo.get_securities()}
    f_map = repo.get_latest_fundamentals_map()

    positions: list[dict[str, Any]] = []
    trades_log: list[dict[str, Any]] = []
    total_invested = 0.0
    total_tx_cost = 0.0

    for sym, w_pct in sorted(weights.items(), key=lambda x: x[1], reverse=True):
        if w_pct <= 0.05:
            continue
        sec = all_secs.get(sym, {"symbol": sym, "company_name": sym})
        f = f_map.get(sym, {})
        enr = enr_map[sym]
        exec_price = float(enr["cmp"] or 100.0)
        target_notional = initial_capital_inr * (w_pct / 100.0)
        qty = int(target_notional // max(1.0, exec_price))
        if qty <= 0:
            qty = 1
        invested_inr = round(qty * exec_price, 2)
        adv_cr = float(f.get("avg_daily_turnover_inr_cr") or 20.0)
        cost_info = estimate_trade_cost_inr(
            notional_inr=invested_inr,
            side="BUY",
            avg_daily_turnover_inr_cr=adv_cr,
        )
        tx_cost = cost_info["total_cost_inr"]
        total_invested += invested_inr
        total_tx_cost += tx_cost

        positions.append(
            {
                "Symbol": sym,
                "Company": sec.get("company_name", sym),
                "Category": sec.get("primary_category", "OTHER"),
                "Target Weight (%)": round(w_pct, 2),
                "Qty (Shares)": qty,
                "Entry Price @ 3PM IST (Rs)": round(exec_price, 2),
                "Current CMP (Rs)": round(exec_price, 2),
                "Invested Value (Rs)": invested_inr,
                "Current Market Value (Rs)": invested_inr,
                "Delivery Tx Cost (Rs)": round(tx_cost, 2),
                "Unrealised P&L (Rs)": 0.0,
                "Net P&L Post-Cost (Rs)": round(-tx_cost, 2),
                "Net Return (%)": round((-tx_cost / max(1.0, invested_inr)) * 100.0, 2),
                "AI Exposure Score": enr["ai_exposure_score"],
                "Fundamental Score": enr["fundamental_score"],
                "Technical Score": enr["technical_score"],
                "Analyst Rating": enr["analyst_rating"],
                "Price Trend (1M | 6M | 1Y | 2Y)": enr["price_trend_summary"],
                "Promoter % (2Y Trend)": enr["promoter_trend"],
                "FII % (2Y Trend)": enr["fii_trend"],
                "DII % (2Y Trend)": enr["dii_trend"],
            }
        )

        trades_log.append(
            {
                "Execution Timestamp (IST)": slot_ts,
                "Symbol": sym,
                "Company": sec.get("company_name", sym),
                "Action": "INITIAL_BUY_3PM_IST",
                "Target Weight (%)": round(w_pct, 2),
                "Shares Qty": qty,
                "Execution Price (Rs)": round(exec_price, 2),
                "Gross Notional (Rs)": invested_inr,
                "Indian Delivery Tx Cost (Rs)": round(tx_cost, 2),
                "Cost (bps)": cost_info["effective_cost_bps"],
                "Order Rationales": (
                    f"AI Score {enr['ai_exposure_score']}/100 | Fund {enr['fundamental_score']}/100 | "
                    f"Tech {enr['technical_score']}/100 ({enr['technical_regime']})"
                ),
            }
        )

    cash_balance = round(initial_capital_inr - total_invested - total_tx_cost, 2)
    net_nav = round(total_invested + cash_balance, 2)

    ledger = {
        "strategy_name": "AI3 Conviction-Weighted Daily 3:00 PM IST Paper-Trading Book",
        "execution_schedule": "Every NSE/BSE Working Day (Mon–Fri) at 15:00:00 IST (3:00 PM IST)",
        "inception_date": slot_date.isoformat(),
        "inception_timestamp_ist": slot_ts,
        "last_executed_timestamp_ist": slot_ts,
        "next_scheduled_timestamp_ist": next_3pm_ist_slot(now_ist),
        "initial_capital_inr": round(initial_capital_inr, 2),
        "invested_market_value_inr": round(total_invested, 2),
        "cash_balance_inr": cash_balance,
        "cumulative_tx_cost_inr": round(total_tx_cost, 2),
        "current_net_nav_inr": net_nav,
        "current_gross_nav_inr": round(initial_capital_inr, 2),
        "net_pnl_inr": round(net_nav - initial_capital_inr, 2),
        "net_return_pct": round(((net_nav / initial_capital_inr) - 1.0) * 100.0, 3),
        "positions": positions,
        "trades_log": trades_log,
        "nav_history": [
            {
                "date": slot_date.isoformat(),
                "timestamp_ist": slot_ts,
                "gross_nav_inr": round(initial_capital_inr, 2),
                "net_nav_inr": net_nav,
                "benchmark_nav_inr": round(initial_capital_inr, 2),
                "cash_inr": cash_balance,
                "cumulative_tx_cost_inr": round(total_tx_cost, 2),
                "note": "Inception 3:00 PM IST portfolio deployment",
            }
        ],
    }

    PAPER_LEDGER_PATH.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return ledger


def _append_daily_3pm_mtm(
    ledger: dict[str, Any],
    repo: AI3Repository,
    ingestion: DataIngestionService,
    slot_date: date,
    slot_ts: str,
) -> dict[str, Any]:
    """Mark open positions to market at 3:00 PM IST on a new working day."""
    all_secs = {s["symbol"]: s for s in repo.get_securities()}
    f_map = repo.get_latest_fundamentals_map()

    total_mv = 0.0
    for pos in ledger.get("positions", []):
        sym = pos["Symbol"]
        sec = all_secs.get(sym, {"symbol": sym, "company_name": sym})
        f = f_map.get(sym, {})
        enr = compute_enriched_equity_metrics(sec, f)
        new_cmp = float(enr["cmp"] or pos["Entry Price @ 3PM IST (Rs)"])
        qty = int(pos["Qty (Shares)"])
        mv = round(qty * new_cmp, 2)
        inv = float(pos["Invested Value (Rs)"])
        tx_cost = float(pos["Delivery Tx Cost (Rs)"])
        unreal = round(mv - inv, 2)
        net_pnl = round(unreal - tx_cost, 2)

        pos["Current CMP (Rs)"] = round(new_cmp, 2)
        pos["Current Market Value (Rs)"] = mv
        pos["Unrealised P&L (Rs)"] = unreal
        pos["Net P&L Post-Cost (Rs)"] = net_pnl
        pos["Net Return (%)"] = round((net_pnl / max(1.0, inv)) * 100.0, 2)
        total_mv += mv

    cash = float(ledger.get("cash_balance_inr", 0.0))
    init_cap = float(ledger.get("initial_capital_inr", 1_000_000.0))
    cum_tx = float(ledger.get("cumulative_tx_cost_inr", 0.0))
    net_nav = round(total_mv + cash, 2)
    gross_nav = round(net_nav + cum_tx, 2)

    ledger["invested_market_value_inr"] = round(total_mv, 2)
    ledger["current_net_nav_inr"] = net_nav
    ledger["current_gross_nav_inr"] = gross_nav
    ledger["net_pnl_inr"] = round(net_nav - init_cap, 2)
    ledger["net_return_pct"] = round(((net_nav / init_cap) - 1.0) * 100.0, 3)
    ledger["last_executed_timestamp_ist"] = slot_ts
    ledger["next_scheduled_timestamp_ist"] = next_3pm_ist_slot()

    ledger["nav_history"].append(
        {
            "date": slot_date.isoformat(),
            "timestamp_ist": slot_ts,
            "gross_nav_inr": gross_nav,
            "net_nav_inr": net_nav,
            "benchmark_nav_inr": gross_nav,
            "cash_inr": cash,
            "cumulative_tx_cost_inr": cum_tx,
            "note": "Daily 3:00 PM IST working-day mark-to-market",
        }
    )
    return ledger


def run_5y_historical_verifiable_backtest(
    repo: AI3Repository,
    ingestion: DataIngestionService,
    end_date: date | None = None,
    initial_capital_inr: float = 1_000_000.0,
) -> dict[str, Any]:
    """Run the 5-Year Historical Verifiable Backtest of the 3:00 PM IST strategy logic."""
    end_dt = end_date or date.today()
    while not is_working_day(end_dt):
        end_dt -= timedelta(days=1)
    start_dt = date(end_dt.year - 5, end_dt.month, min(end_dt.day, 28))

    all_secs = repo.get_securities(geography="INDIA", investable_only=True)
    avail_syms = [s["symbol"] for s in all_secs]
    bt_syms = [s for s in DEFAULT_PAPER_BASKET if s in avail_syms]
    if len(bt_syms) < 5:
        bt_syms = avail_syms

    engine = PointInTimeBacktestEngine(ingestion=ingestion)
    cfg = BacktestConfig(
        start_date=start_dt,
        end_date=end_dt,
        initial_capital_inr=initial_capital_inr,
        rebalance_frequency="QUARTERLY",
        optimisation_method="CONVICTION_WEIGHTED",
        max_single_stock_pct=10.0,
        max_subsector_pct=30.0,
        fundamental_lag_days=60,
        execute_at_next_open=True,
    )

    bt_res = engine.run_backtest(symbols=bt_syms, config=cfg)
    net_nav: pd.Series = bt_res["net_nav_series"]
    gross_nav: pd.Series = bt_res["gross_nav_series"]
    bench_nav: pd.Series = bt_res["benchmark_nav_series"]
    base_metrics = bt_res["metrics"]

    # Compute additional verifiable KPIs (Win rate, Profit factor, Best/Worst day, Recovery days)
    daily_rets = net_nav.pct_change().dropna()
    pos_days = int((daily_rets > 0).sum())
    total_days = max(1, len(daily_rets))
    daily_win_rate_pct = round((pos_days / total_days) * 100.0, 2)

    gains_sum = float(daily_rets[daily_rets > 0].sum())
    losses_sum = abs(float(daily_rets[daily_rets < 0].sum()))
    profit_factor = round(gains_sum / losses_sum, 2) if losses_sum > 1e-9 else 2.5

    # Monthly win rate
    monthly_nav = net_nav.resample("ME").last().dropna()
    monthly_rets = monthly_nav.pct_change().dropna()
    monthly_win_rate_pct = (
        round(float((monthly_rets > 0).sum() / max(1, len(monthly_rets))) * 100.0, 2)
        if not monthly_rets.empty
        else daily_win_rate_pct
    )

    # Underwater drawdown series
    running_max = net_nav.cummax()
    drawdown_series = ((net_nav / running_max) - 1.0) * 100.0

    # Compute Multi-Horizon Interval Table (1W, 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y)
    interval_rows: list[dict[str, Any]] = []
    n_bars = len(net_nav)

    for code, label, td_count in TIME_HORIZON_SPECS:
        lookback = min(td_count, max(1, n_bars - 1))
        sub_net = net_nav.iloc[-(lookback + 1) :]
        sub_gross = gross_nav.iloc[-(lookback + 1) :]
        sub_bench = bench_nav.iloc[-(lookback + 1) :] if not bench_nav.empty else sub_net

        start_v = float(sub_net.iloc[0])
        end_v = float(sub_net.iloc[-1])
        net_ret_pct = ((end_v / max(1.0, start_v)) - 1.0) * 100.0

        g_start = float(sub_gross.iloc[0])
        g_end = float(sub_gross.iloc[-1])
        gross_ret_pct = ((g_end / max(1.0, g_start)) - 1.0) * 100.0

        b_start = float(sub_bench.iloc[0])
        b_end = float(sub_bench.iloc[-1])
        bench_ret_pct = ((b_end / max(1.0, b_start)) - 1.0) * 100.0
        alpha_pct = net_ret_pct - bench_ret_pct

        years_len = max(lookback / 252.0, 1.0 / 252.0)
        if lookback >= 252:
            ann_net_cagr = (((end_v / max(1.0, start_v)) ** (1.0 / years_len)) - 1.0) * 100.0
        else:
            # For sub-1Y horizons, report simple period return and annualised equivalent
            ann_net_cagr = net_ret_pct * (252.0 / max(1, lookback))

        sub_rets = sub_net.pct_change().dropna()
        ann_vol = float(sub_rets.std() * np.sqrt(252) * 100.0) if len(sub_rets) > 1 else 0.0
        rf_daily = 0.065 / 252.0
        ex_rets = sub_rets - rf_daily
        sharpe = (
            float((ex_rets.mean() / sub_rets.std()) * np.sqrt(252))
            if (len(sub_rets) > 2 and sub_rets.std() > 1e-9)
            else 0.0
        )
        sub_dd = float(((sub_net / sub_net.cummax()) - 1.0).min() * 100.0)
        sub_win = (
            round(float((sub_rets > 0).sum() / max(1, len(sub_rets))) * 100.0, 1)
            if len(sub_rets) > 0
            else 0.0
        )
        rs_10l_end = round(initial_capital_inr * (1.0 + net_ret_pct / 100.0), 0)

        interval_rows.append(
            {
                "Time Interval": f"{label} ({code})",
                "Trading Days": lookback,
                "Window Start": str(sub_net.index[0].date()),
                "Window End": str(sub_net.index[-1].date()),
                "Net Return (%)": round(net_ret_pct, 2),
                "Gross Return (%)": round(gross_ret_pct, 2),
                "Benchmark Return (%)": round(bench_ret_pct, 2),
                "Active Alpha (%)": round(alpha_pct, 2),
                "Annualised Return / CAGR (%)": round(ann_net_cagr, 2),
                "Max Drawdown (%)": round(sub_dd, 2),
                "Ann. Volatility (%)": round(ann_vol, 2),
                "Sharpe Ratio": round(sharpe, 2),
                "Win Rate (% Days)": sub_win,
                "Rs 10L Grown To (Rs)": f"Rs {rs_10l_end:,.0f}",
            }
        )

    # Compute Year-by-Year Verifiable Performance Breakdown
    annual_rows: list[dict[str, Any]] = []
    years_present = sorted(list(set(net_nav.index.year)))
    for yr in years_present:
        yr_net = net_nav[net_nav.index.year == yr]
        yr_bench = bench_nav[bench_nav.index.year == yr] if not bench_nav.empty else yr_net
        if len(yr_net) < 2:
            continue
        yr_ret = ((float(yr_net.iloc[-1]) / float(yr_net.iloc[0])) - 1.0) * 100.0
        yr_b_ret = ((float(yr_bench.iloc[-1]) / float(yr_bench.iloc[0])) - 1.0) * 100.0
        yr_dd = float(((yr_net / yr_net.cummax()) - 1.0).min() * 100.0)
        yr_d_rets = yr_net.pct_change().dropna()
        yr_vol = float(yr_d_rets.std() * np.sqrt(252) * 100.0) if len(yr_d_rets) > 1 else 0.0
        annual_rows.append(
            {
                "Calendar Year": str(yr),
                "Trading Days": len(yr_net),
                "Strategy Net Return (%)": round(yr_ret, 2),
                "Benchmark Return (%)": round(yr_b_ret, 2),
                "Active Alpha (%)": round(yr_ret - yr_b_ret, 2),
                "Max Drawdown (%)": round(yr_dd, 2),
                "Annualised Vol (%)": round(yr_vol, 2),
                "Closing Net NAV (Rs)": round(float(yr_net.iloc[-1]), 2),
            }
        )

    final_net = round(float(net_nav.iloc[-1]), 2) if not net_nav.empty else initial_capital_inr
    final_gross = round(float(gross_nav.iloc[-1]), 2) if not gross_nav.empty else initial_capital_inr
    final_bench = round(float(bench_nav.iloc[-1]), 2) if not bench_nav.empty else initial_capital_inr
    cum_net_ret_pct = round(((final_net / max(1.0, initial_capital_inr)) - 1.0) * 100.0, 2)
    cum_gross_ret_pct = round(((final_gross / max(1.0, initial_capital_inr)) - 1.0) * 100.0, 2)

    summary_kpis = {
        **base_metrics,
        "start_date": start_dt.isoformat(),
        "end_date": end_dt.isoformat(),
        "initial_capital_inr": initial_capital_inr,
        "final_net_nav_inr": final_net,
        "final_gross_nav_inr": final_gross,
        "final_benchmark_nav_inr": final_bench,
        "cumulative_net_return_pct": cum_net_ret_pct,
        "cumulative_gross_return_pct": cum_gross_ret_pct,
        "daily_win_rate_pct": daily_win_rate_pct,
        "monthly_win_rate_pct": monthly_win_rate_pct,
        "profit_factor": profit_factor,
    }

    return {
        "summary_kpis": summary_kpis,
        "interval_table": interval_rows,
        "annual_table": annual_rows,
        "net_nav_series": net_nav,
        "gross_nav_series": gross_nav,
        "benchmark_nav_series": bench_nav,
        "drawdown_series": drawdown_series,
        "rebalance_log": bt_res["rebalance_log"],
        "warnings": bt_res["warnings"],
    }


def build_forward_horizon_kpi_table(
    ledger: dict[str, Any],
    historical_interval_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the forward paper-trade KPI table across 1W, 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y horizons."""
    nav_hist = ledger.get("nav_history", [])
    elapsed_days = len(nav_hist)
    init_cap = float(ledger.get("initial_capital_inr", 1_000_000.0))
    cur_nav = float(ledger.get("current_net_nav_inr", init_cap))
    live_ret_pct = round(((cur_nav / max(1.0, init_cap)) - 1.0) * 100.0, 3)

    hist_by_label = {r["Time Interval"]: r for r in historical_interval_rows}
    forward_rows: list[dict[str, Any]] = []

    for code, label, td_count in TIME_HORIZON_SPECS:
        key = f"{label} ({code})"
        h_row = hist_by_label.get(key, {})
        if elapsed_days >= td_count and elapsed_days > 1:
            start_nav = float(nav_hist[-td_count]["net_nav_inr"])
            p_ret = round(((cur_nav / max(1.0, start_nav)) - 1.0) * 100.0, 2)
            fwd_status = f"LIVE COMPLETED ({td_count}D)"
            fwd_ret_str = f"{p_ret:+.2f}%"
            fwd_nav_str = f"Rs {cur_nav:,.2f}"
        else:
            fwd_status = f"LIVE ACCRUING (Day {elapsed_days} of {td_count}D — Started {ledger['inception_date']} @ 3 PM IST)"
            fwd_ret_str = f"{live_ret_pct:+.3f}% (Inception-to-Date)"
            fwd_nav_str = f"Rs {cur_nav:,.2f}"

        forward_rows.append(
            {
                "Horizon": key,
                "Required Working Days": td_count,
                "Forward Paper-Trade Status": fwd_status,
                "Live Forward Net Return (Since Today 3 PM IST)": fwd_ret_str,
                "Live Forward Net NAV": fwd_nav_str,
                "5Y Historical Verifiable Net Return (%)": f"{h_row.get('Net Return (%)', 0.0):+.2f}%",
                "5Y Historical Verifiable CAGR (%)": f"{h_row.get('Annualised Return / CAGR (%)', 0.0):+.2f}%",
                "5Y Historical Benchmark Return (%)": f"{h_row.get('Benchmark Return (%)', 0.0):+.2f}%",
                "5Y Historical Active Alpha (%)": f"{h_row.get('Active Alpha (%)', 0.0):+.2f}%",
                "5Y Historical Sharpe": h_row.get("Sharpe Ratio"),
                "5Y Historical Max DD (%)": f"{h_row.get('Max Drawdown (%)', 0.0):.2f}%",
            }
        )

    return forward_rows


_SCHEDULER_STARTED = False
_SCHEDULER_LOCK = threading.Lock()


def start_background_3pm_ist_scheduler(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    """Start a lightweight background daemon thread that triggers the 3:00 PM IST paper trade every working day."""
    global _SCHEDULER_STARTED
    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED:
            return
        _SCHEDULER_STARTED = True

    def _worker() -> None:
        last_run_date_str = ""
        while True:
            try:
                now_ist = get_ist_now()
                d_str = now_ist.date().isoformat()
                if is_working_day(now_ist.date()) and now_ist.time() >= time(15, 0) and last_run_date_str != d_str:
                    ensure_paper_trading_ledger(repo=repo, ingestion=ingestion)
                    last_run_date_str = d_str
            except Exception:
                pass
            time_mod.sleep(60)

    t = threading.Thread(target=_worker, name="ai3-3pm-ist-paper-trader", daemon=True)
    t.start()
