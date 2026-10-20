"""Valuation metrics and peer-group percentile ranking engine."""

from __future__ import annotations

from typing import Any

import numpy as np


def compute_valuation_metrics(f: dict[str, Any], peer_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Compute derived valuation metrics and peer percentile ranks without fabricating missing denominators."""
    mcap = f.get("market_cap_inr_cr")
    ev = f.get("enterprise_value_inr_cr")
    rev = f.get("revenue_inr_cr")
    ob = f.get("order_book_inr_cr")
    fcf = f.get("fcf_inr_cr")
    pat = f.get("pat_inr_cr")
    t_pe = f.get("trailing_pe")
    f_pe = f.get("forward_pe")
    ev_ebitda = f.get("ev_ebitda")
    pb = f.get("price_to_book")
    peg = f.get("peg_ratio")

    # Derived yields and ratios (only when denominators are positive)
    ev_to_sales: float | None = None
    if ev is not None and rev is not None and rev > 0:
        ev_to_sales = round(ev / rev, 2)

    fcf_yield_pct: float | None = f.get("fcf_yield_pct")
    if fcf_yield_pct is None and fcf is not None and mcap is not None and mcap > 0:
        fcf_yield_pct = round((fcf / mcap) * 100.0, 2)

    earnings_yield_pct: float | None = None
    if pat is not None and mcap is not None and mcap > 0:
        earnings_yield_pct = round((pat / mcap) * 100.0, 2)
    elif t_pe is not None and t_pe > 0:
        earnings_yield_pct = round(100.0 / t_pe, 2)

    ev_to_order_book: float | None = f.get("ev_to_order_book")
    if ev_to_order_book is None and ev is not None and ob is not None and ob > 0:
        ev_to_order_book = round(ev / ob, 2)

    # Sector/peer percentile ranking (lower P/E or EV/EBITDA = cheaper = higher value score)
    pe_percentile_vs_peers: float | None = None
    ev_ebitda_percentile_vs_peers: float | None = None
    if peer_records:
        peer_pes = [p["trailing_pe"] for p in peer_records if p.get("trailing_pe") is not None and p["trailing_pe"] > 0]
        if t_pe is not None and t_pe > 0 and len(peer_pes) >= 2:
            cheaper_or_equal = sum(1 for x in peer_pes if x <= t_pe)
            pe_percentile_vs_peers = round((cheaper_or_equal / len(peer_pes)) * 100.0, 1)

        peer_evs = [p["ev_ebitda"] for p in peer_records if p.get("ev_ebitda") is not None and p["ev_ebitda"] > 0]
        if ev_ebitda is not None and ev_ebitda > 0 and len(peer_evs) >= 2:
            cheaper_or_equal_ev = sum(1 for x in peer_evs if x <= ev_ebitda)
            ev_ebitda_percentile_vs_peers = round((cheaper_or_equal_ev / len(peer_evs)) * 100.0, 1)

    # Valuation reasonableness score (0 to 10 points for the 100-pt model, plus 0-100 normalised)
    val_100 = _score_valuation_reasonableness_100(
        trailing_pe=t_pe,
        forward_pe=f_pe,
        ev_ebitda=ev_ebitda,
        peg_ratio=peg,
        fcf_yield_pct=fcf_yield_pct,
        pb=pb,
    )

    return {
        "symbol": f.get("symbol"),
        "trailing_pe": t_pe,
        "forward_pe": f_pe,
        "ev_ebitda": ev_ebitda,
        "ev_to_sales": ev_to_sales,
        "price_to_book": pb,
        "fcf_yield_pct": fcf_yield_pct,
        "earnings_yield_pct": earnings_yield_pct,
        "peg_ratio": peg,
        "ev_to_order_book": ev_to_order_book,
        "pe_percentile_vs_peers": pe_percentile_vs_peers,
        "ev_ebitda_percentile_vs_peers": ev_ebitda_percentile_vs_peers,
        "valuation_score_100": val_100,
        "valuation_score_10": round(val_100 / 10.0, 2) if val_100 is not None else 3.0,
    }


def _score_valuation_reasonableness_100(
    trailing_pe: float | None,
    forward_pe: float | None,
    ev_ebitda: float | None,
    peg_ratio: float | None,
    fcf_yield_pct: float | None,
    pb: float | None,
) -> float:
    """Compute a 0-100 valuation attractiveness score (higher = cheaper / better value)."""
    scores: list[float] = []
    effective_pe = forward_pe if (forward_pe is not None and forward_pe > 0) else trailing_pe
    if effective_pe is not None:
        if effective_pe <= 0:
            scores.append(10.0)
        elif effective_pe <= 18.0:
            scores.append(92.0)
        elif effective_pe <= 28.0:
            scores.append(80.0)
        elif effective_pe <= 40.0:
            scores.append(64.0)
        elif effective_pe <= 55.0:
            scores.append(46.0)
        elif effective_pe <= 75.0:
            scores.append(28.0)
        else:
            scores.append(12.0)

    if ev_ebitda is not None:
        if ev_ebitda <= 0:
            scores.append(10.0)
        elif ev_ebitda <= 12.0:
            scores.append(90.0)
        elif ev_ebitda <= 20.0:
            scores.append(75.0)
        elif ev_ebitda <= 30.0:
            scores.append(58.0)
        elif ev_ebitda <= 45.0:
            scores.append(36.0)
        else:
            scores.append(15.0)

    if peg_ratio is not None and peg_ratio > 0:
        if peg_ratio <= 1.0:
            scores.append(95.0)
        elif peg_ratio <= 1.5:
            scores.append(80.0)
        elif peg_ratio <= 2.2:
            scores.append(60.0)
        elif peg_ratio <= 3.0:
            scores.append(40.0)
        else:
            scores.append(20.0)

    if fcf_yield_pct is not None:
        if fcf_yield_pct >= 4.0:
            scores.append(90.0)
        elif fcf_yield_pct >= 2.0:
            scores.append(72.0)
        elif fcf_yield_pct >= 0.5:
            scores.append(52.0)
        else:
            scores.append(28.0)

    if not scores and pb is not None and pb > 0:
        scores.append(max(10.0, min(90.0, 100.0 - pb * 8.0)))

    if not scores:
        return 30.0
    return round(float(np.mean(scores)), 1)
