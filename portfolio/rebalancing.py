"""Rebalancing logic and realistic Indian equity transaction cost & slippage calculator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class IndianTransactionCostConfig:
    """Realistic NSE/BSE cash-equity delivery transaction cost parameters."""

    brokerage_bps: float = 5.0  # 0.05% (or discount broker effective rate)
    stt_delivery_bps: float = 10.0  # 0.10% on both buy and sell for equity delivery in India
    exchange_txn_bps: float = 0.325  # ~0.00325% NSE cash market
    sebi_turnover_bps: float = 0.01  # Rs 10 per crore
    stamp_duty_buy_bps: float = 1.5  # 0.015% on delivery buy
    gst_rate_pct: float = 18.0  # 18% on (brokerage + exchange + SEBI charges)
    base_slippage_bps: float = 10.0  # 0.10% base bid-ask + execution slippage for liquid large/mid caps
    small_cap_impact_Penalty_bps: float = 35.0  # Additional slippage when daily turnover < Rs 10 Cr


def estimate_trade_cost_inr(
    notional_inr: float,
    side: str = "BUY",
    avg_daily_turnover_inr_cr: float | None = 25.0,
    config: IndianTransactionCostConfig | None = None,
) -> dict[str, float]:
    """Calculate statutory Indian equity delivery charges + liquidity-scaled market impact for a trade leg."""
    if notional_inr <= 0:
        return {
            "notional_inr": 0.0,
            "statutory_and_brokerage_inr": 0.0,
            "slippage_impact_inr": 0.0,
            "total_cost_inr": 0.0,
            "effective_cost_bps": 0.0,
        }
    cfg = config or IndianTransactionCostConfig()
    side_u = side.upper()

    brokerage = notional_inr * (cfg.brokerage_bps / 10000.0)
    stt = notional_inr * (cfg.stt_delivery_bps / 10000.0)
    exch = notional_inr * (cfg.exchange_txn_bps / 10000.0)
    sebi = notional_inr * (cfg.sebi_turnover_bps / 10000.0)
    stamp = notional_inr * (cfg.stamp_duty_buy_bps / 10000.0) if side_u == "BUY" else 0.0
    gst = (brokerage + exch + sebi) * (cfg.gst_rate_pct / 100.0)

    statutory_and_brok = brokerage + stt + exch + sebi + stamp + gst

    # Liquidity-scaled slippage
    adv_cr = avg_daily_turnover_inr_cr if (avg_daily_turnover_inr_cr is not None and avg_daily_turnover_inr_cr > 0) else 5.0
    slip_bps = cfg.base_slippage_bps
    if adv_cr < 2.0:
        slip_bps += cfg.small_cap_impact_Penalty_bps * 2.0
    elif adv_cr < 10.0:
        slip_bps += cfg.small_cap_impact_Penalty_bps

    # Participation rate penalty if order exceeds 1% of average daily turnover
    order_cr = notional_inr / 1e7
    participation = order_cr / max(0.05, adv_cr)
    if participation > 0.01:
        slip_bps += min(150.0, (participation * 100.0) * 12.0)

    slippage_inr = notional_inr * (slip_bps / 10000.0)
    total_cost = statutory_and_brok + slippage_inr
    eff_bps = (total_cost / notional_inr) * 10000.0

    return {
        "notional_inr": round(notional_inr, 2),
        "statutory_and_brokerage_inr": round(statutory_and_brok, 2),
        "slippage_impact_inr": round(slippage_inr, 2),
        "total_cost_inr": round(total_cost, 2),
        "effective_cost_bps": round(eff_bps, 2),
    }


def compute_rebalance_trades(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    portfolio_value_inr: float,
    turnover_map_cr: dict[str, float] | None = None,
    drift_threshold_pct: float = 0.0,
) -> dict[str, Any]:
    """Generate buy/sell rebalance orders and total transaction cost estimate."""
    all_syms = sorted(list(set(current_weights.keys()) | set(target_weights.keys())))
    max_drift = max((abs(target_weights.get(s, 0.0) - current_weights.get(s, 0.0)) for s in all_syms), default=0.0)

    if drift_threshold_pct > 0 and max_drift < drift_threshold_pct:
        return {
            "rebalance_triggered": False,
            "max_drift_pct": round(max_drift, 2),
            "one_way_turnover_pct": 0.0,
            "total_transaction_cost_inr": 0.0,
            "trades": [],
        }

    trades: list[dict[str, Any]] = []
    total_cost = 0.0
    total_traded_notional = 0.0
    t_map = turnover_map_cr or {}

    for sym in all_syms:
        cw = current_weights.get(sym, 0.0)
        tw = target_weights.get(sym, 0.0)
        diff_pct = tw - cw
        if abs(diff_pct) < 0.05:
            continue
        side = "BUY" if diff_pct > 0 else "SELL"
        notional = abs(diff_pct / 100.0) * portfolio_value_inr
        cost_info = estimate_trade_cost_inr(
            notional_inr=notional,
            side=side,
            avg_daily_turnover_inr_cr=t_map.get(sym, 20.0),
        )
        total_cost += cost_info["total_cost_inr"]
        total_traded_notional += notional
        trades.append(
            {
                "symbol": sym,
                "side": side,
                "current_weight_pct": round(cw, 2),
                "target_weight_pct": round(tw, 2),
                "delta_weight_pct": round(diff_pct, 2),
                "notional_inr": cost_info["notional_inr"],
                "estimated_cost_inr": cost_info["total_cost_inr"],
                "effective_cost_bps": cost_info["effective_cost_bps"],
            }
        )

    one_way_turnover_pct = (total_traded_notional / (2.0 * max(1.0, portfolio_value_inr))) * 100.0
    return {
        "rebalance_triggered": True,
        "max_drift_pct": round(max_drift, 2),
        "one_way_turnover_pct": round(one_way_turnover_pct, 2),
        "total_transaction_cost_inr": round(total_cost, 2),
        "trades": trades,
    }
