"""ETF, Smallcase, and Direct Stock overlap and look-through exposure engine."""

from __future__ import annotations

import csv
import io
from typing import Any

from core.schemas import OverlapResult


def normalize_weights(raw_weights: dict[str, float]) -> dict[str, float]:
    """Normalize a dictionary of `{symbol: weight_pct_or_frac}` so positive weights sum to 100.0%."""
    clean = {k.strip().upper(): float(v) for k, v in raw_weights.items() if k and float(v) > 0}
    total = sum(clean.values())
    if total <= 0:
        return {}
    return {k: round((v / total) * 100.0, 4) for k, v in clean.items()}


def compute_basket_overlap(
    basket_a_name: str,
    weights_a: dict[str, float],
    basket_b_name: str,
    weights_b: dict[str, float],
    sector_map: dict[str, str] | None = None,
) -> OverlapResult:
    """Compute weighted overlap (`sum(min(w_i, v_i))`), Jaccard index, shared holdings, and sector overlap."""
    wa = normalize_weights(weights_a)
    wb = normalize_weights(weights_b)

    syms_a = set(wa.keys())
    syms_b = set(wb.keys())
    shared = sorted(syms_a & syms_b)
    union = syms_a | syms_b

    jaccard = round(len(shared) / len(union), 4) if union else 0.0
    weighted_overlap = round(sum(min(wa.get(s, 0.0), wb.get(s, 0.0)) for s in shared), 2)

    shared_details = [
        {
            "symbol": s,
            "weight_a_pct": round(wa[s], 2),
            "weight_b_pct": round(wb[s], 2),
            "overlap_contribution_pct": round(min(wa[s], wb[s]), 2),
        }
        for s in shared
    ]
    shared_details.sort(key=lambda x: x["overlap_contribution_pct"], reverse=True)

    sec_overlap = 0.0
    if sector_map:
        sec_a: dict[str, float] = {}
        sec_b: dict[str, float] = {}
        for s, w in wa.items():
            cat = sector_map.get(s, "OTHER")
            sec_a[cat] = sec_a.get(cat, 0.0) + w
        for s, w in wb.items():
            cat = sector_map.get(s, "OTHER")
            sec_b[cat] = sec_b.get(cat, 0.0) + w
        all_cats = set(sec_a.keys()) | set(sec_b.keys())
        sec_overlap = round(sum(min(sec_a.get(c, 0.0), sec_b.get(c, 0.0)) for c in all_cats), 2)

    return OverlapResult(
        basket_a_name=basket_a_name,
        basket_b_name=basket_b_name,
        weighted_overlap_pct=weighted_overlap,
        jaccard_similarity=jaccard,
        shared_symbols_count=len(shared),
        shared_symbols=shared_details,
        sector_overlap_pct=sec_overlap,
    )


def compute_pairwise_overlap_matrix(baskets: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """Compute an N x N matrix of weighted overlap percentages across multiple ETFs/smallcases/portfolios."""
    names = list(baskets.keys())
    matrix: dict[str, dict[str, float]] = {n: {} for n in names}
    for i, na in enumerate(names):
        for j, nb in enumerate(names):
            if i == j:
                matrix[na][nb] = 100.0
            else:
                res = compute_basket_overlap(na, baskets[na], nb, baskets[nb])
                matrix[na][nb] = res.weighted_overlap_pct
    return matrix


def compute_lookthrough_stock_exposure(
    direct_stock_weights: dict[str, float],
    etf_allocations: dict[str, float],
    smallcase_allocations: dict[str, float],
    etf_constituents_map: dict[str, dict[str, float]],
    smallcase_constituents_map: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    """Aggregate look-through underlying stock exposure across direct equities, ETFs, and Smallcase baskets.

    Input allocations are portfolio weights (summing to 100% across all sleeves or normalised automatically).
    """
    total_alloc = (
        sum(direct_stock_weights.values())
        + sum(etf_allocations.values())
        + sum(smallcase_allocations.values())
    )
    scale = (100.0 / total_alloc) if total_alloc > 0 else 1.0

    lookthrough: dict[str, dict[str, Any]] = {}

    def _add(sym: str, pct: float, source_label: str) -> None:
        s = sym.strip().upper()
        if pct <= 0:
            return
        if s not in lookthrough:
            lookthrough[s] = {"symbol": s, "total_weight_pct": 0.0, "sources": {}}
        lookthrough[s]["total_weight_pct"] += pct
        lookthrough[s]["sources"][source_label] = lookthrough[s]["sources"].get(source_label, 0.0) + pct

    for sym, w in direct_stock_weights.items():
        _add(sym, w * scale, "Direct Equity")

    for etf_sym, etf_w in etf_allocations.items():
        constituents = normalize_weights(etf_constituents_map.get(etf_sym, {}))
        for c_sym, c_w in constituents.items():
            _add(c_sym, (etf_w * scale) * (c_w / 100.0), f"ETF:{etf_sym}")

    for sc_id, sc_w in smallcase_allocations.items():
        constituents = normalize_weights(smallcase_constituents_map.get(sc_id, {}))
        for c_sym, c_w in constituents.items():
            _add(c_sym, (sc_w * scale) * (c_w / 100.0), f"Smallcase:{sc_id}")

    result = []
    for sym, info in lookthrough.items():
        result.append(
            {
                "symbol": sym,
                "total_weight_pct": round(info["total_weight_pct"], 2),
                "source_count": len(info["sources"]),
                "source_breakdown": {k: round(v, 2) for k, v in info["sources"].items()},
                "is_crowded_across_sleeves": len(info["sources"]) >= 2 and info["total_weight_pct"] >= 5.0,
            }
        )
    result.sort(key=lambda r: r["total_weight_pct"], reverse=True)
    return result


def parse_user_smallcase_csv(csv_text: str) -> list[dict[str, Any]]:
    """Parse a user-uploaded CSV of smallcase or custom basket constituents (`symbol,weight_pct,role`).

    Never fabricates constituents for locked smallcases; validates symbols and weights cleanly.
    """
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    parsed: list[dict[str, Any]] = []
    for row in reader:
        clean = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}
        sym = clean.get("symbol") or clean.get("ticker") or clean.get("nse_symbol") or ""
        if not sym:
            continue
        w_str = clean.get("weight_pct") or clean.get("weight") or "0"
        try:
            w = float(w_str.replace("%", ""))
        except ValueError:
            w = 1.0
        parsed.append(
            {
                "symbol": sym.upper(),
                "weight_pct": w,
                "role": clean.get("role") or clean.get("rationale") or "User-uploaded constituent",
            }
        )
    if not parsed:
        return []
    total_w = sum(p["weight_pct"] for p in parsed)
    if total_w > 0:
        for p in parsed:
            p["weight_pct"] = round((p["weight_pct"] / total_w) * 100.0, 2)
    return parsed


def compare_smallcase_fee_vs_diy(
    investment_amount_inr: float,
    subscription_fee_annual_inr: float,
    expected_gross_cagr_pct: float = 16.0,
    annual_turnover_pct: float = 35.0,
    horizon_years: int = 5,
) -> dict[str, float]:
    """Compare Smallcase subscription + rebalance drag against a Direct DIY Equity/ETF replication basket."""
    fee_drag_pct = (subscription_fee_annual_inr / max(1.0, investment_amount_inr)) * 100.0
    # Rebalance transaction + STCG tax drag on churn
    rebalance_tx_drag_pct = (annual_turnover_pct / 100.0) * 0.45

    sc_net_cagr = expected_gross_cagr_pct - fee_drag_pct - rebalance_tx_drag_pct
    diy_net_cagr = expected_gross_cagr_pct - (rebalance_tx_drag_pct * 0.5)

    sc_terminal = investment_amount_inr * ((1.0 + sc_net_cagr / 100.0) ** horizon_years)
    diy_terminal = investment_amount_inr * ((1.0 + diy_net_cagr / 100.0) ** horizon_years)

    return {
        "investment_amount_inr": round(investment_amount_inr, 2),
        "annual_fee_drag_pct": round(fee_drag_pct, 2),
        "annual_rebalance_drag_pct": round(rebalance_tx_drag_pct, 2),
        "smallcase_net_cagr_pct": round(sc_net_cagr, 2),
        "diy_net_cagr_pct": round(diy_net_cagr, 2),
        "smallcase_terminal_value_inr": round(sc_terminal, 2),
        "diy_terminal_value_inr": round(diy_terminal, 2),
        "cumulative_cost_savings_diy_inr": round(diy_terminal - sc_terminal, 2),
    }
