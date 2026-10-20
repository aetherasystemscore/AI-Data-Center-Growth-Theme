"""Value Alternative Finder engine (Section 12 of the Master Project Prompt)."""

from __future__ import annotations

from typing import Any

from analytics.comparable_companies import compute_business_similarity
from analytics.exposure_scoring import score_company_exposure
from core.schemas import ValueAlternativeCandidate, ValueAlternativeReport


def find_value_alternatives(
    target_symbol: str,
    securities: list[dict[str, Any]],
    fundamentals_map: dict[str, dict[str, Any]],
    top_n: int = 5,
    include_global_benchmarks: bool = False,
    min_daily_turnover_cr: float = 1.0,
) -> ValueAlternativeReport:
    """For any popular/expensive AI or data-centre stock, identify 3-5 better-value alternatives in the same supply chain.

    Each candidate returns:
    1. Similarity score (0-100)
    2. Valuation comparison (P/E & EV/EBITDA discounts, PEG, FCF yield)
    3. Quality comparison (ROCE, 3Y Rev CAGR, Debt/Equity, Order Book to Sales)
    4. Why the alternative is cheaper
    5. What could break the thesis
    6. Liquidity and position-sizing suitability
    """
    sec_by_sym = {s["symbol"].upper(): s for s in securities}
    t_sym = target_symbol.upper()
    if t_sym not in sec_by_sym:
        raise ValueError(f"Unknown target symbol '{target_symbol}'")

    t_sec = sec_by_sym[t_sym]
    t_f = fundamentals_map.get(t_sym, {})
    t_score = score_company_exposure(t_sec, t_f)

    t_pe = t_f.get("trailing_pe")
    t_ev = t_f.get("ev_ebitda")
    t_mcap = t_f.get("market_cap_inr_cr") or 0.0

    candidates: list[tuple[float, ValueAlternativeCandidate]] = []

    for c_sec in securities:
        c_sym = c_sec["symbol"].upper()
        if c_sym == t_sym:
            continue
        if not include_global_benchmarks and c_sec.get("geography") != t_sec.get("geography"):
            continue
        # Never recommend unverified / critical governance red-flag stocks as investable value alternatives
        if not c_sec.get("is_investable", True):
            continue

        c_f = fundamentals_map.get(c_sym, {})
        c_score = score_company_exposure(c_sec, c_f)
        if c_score.has_critical_red_flag or c_score.investability_blocked:
            continue

        sim = compute_business_similarity(t_sec, t_f, c_sec, c_f)
        if sim < 22.0:
            continue

        c_pe = c_f.get("trailing_pe")
        c_ev = c_f.get("ev_ebitda")

        pe_disc_pct: float | None = None
        if t_pe is not None and t_pe > 0 and c_pe is not None and c_pe > 0:
            pe_disc_pct = round(((t_pe - c_pe) / t_pe) * 100.0, 1)

        ev_disc_pct: float | None = None
        if t_ev is not None and t_ev > 0 and c_ev is not None and c_ev > 0:
            ev_disc_pct = round(((t_ev - c_ev) / t_ev) * 100.0, 1)

        # Require the alternative to either trade at a valuation discount OR have a superior PEG/FCF yield
        is_cheaper = (
            (pe_disc_pct is not None and pe_disc_pct > 3.0)
            or (ev_disc_pct is not None and ev_disc_pct > 3.0)
            or (
                c_f.get("peg_ratio") is not None
                and t_f.get("peg_ratio") is not None
                and c_f["peg_ratio"] < t_f["peg_ratio"]
            )
        )
        if not is_cheaper:
            continue

        why_cheaper = _explain_why_cheaper(t_sec, t_f, c_sec, c_f, pe_disc_pct, ev_disc_pct)
        what_breaks = _explain_thesis_risks(c_sec, c_f)
        liq_suitability = _assess_liquidity_suitability(c_sec, c_f, min_daily_turnover_cr)

        val_comp = {
            "target_trailing_pe": t_pe,
            "alternative_trailing_pe": c_pe,
            "pe_discount_pct": pe_disc_pct,
            "target_forward_pe": t_f.get("forward_pe"),
            "alternative_forward_pe": c_f.get("forward_pe"),
            "target_ev_ebitda": t_ev,
            "alternative_ev_ebitda": c_ev,
            "ev_ebitda_discount_pct": ev_disc_pct,
            "target_peg": t_f.get("peg_ratio"),
            "alternative_peg": c_f.get("peg_ratio"),
            "target_fcf_yield_pct": t_f.get("fcf_yield_pct"),
            "alternative_fcf_yield_pct": c_f.get("fcf_yield_pct"),
        }

        qual_comp = {
            "target_roce_pct": t_f.get("roce_pct"),
            "alternative_roce_pct": c_f.get("roce_pct"),
            "target_rev_cagr_3y_pct": t_f.get("rev_cagr_3y_pct"),
            "alternative_rev_cagr_3y_pct": c_f.get("rev_cagr_3y_pct"),
            "target_ebitda_margin_pct": t_f.get("ebitda_margin_pct"),
            "alternative_ebitda_margin_pct": c_f.get("ebitda_margin_pct"),
            "target_debt_to_equity": t_f.get("debt_to_equity"),
            "alternative_debt_to_equity": c_f.get("debt_to_equity"),
            "target_order_book_to_sales": t_f.get("order_book_to_LTM_sales"),
            "alternative_order_book_to_sales": c_f.get("order_book_to_LTM_sales"),
            "target_ai_exposure_score": t_score.total_score,
            "alternative_ai_exposure_score": c_score.total_score,
        }

        # Composite ranking score balancing business similarity, valuation discount, and fundamental quality
        disc_boost = max(0.0, min(40.0, (pe_disc_pct or ev_disc_pct or 10.0) * 0.65))
        rank_metric = 0.45 * sim + 0.30 * disc_boost + 0.25 * c_score.total_score

        candidates.append(
            (
                rank_metric,
                ValueAlternativeCandidate(
                    symbol=c_sym,
                    company_name=c_sec["company_name"],
                    similarity_score=sim,
                    shared_categories=sorted(list(set(t_sec.get("sector_tags", [])) & set(c_sec.get("sector_tags", [])))),
                    shared_subcategories=sorted(list(set(t_sec.get("subcategories", [])) & set(c_sec.get("subcategories", [])))),
                    valuation_comparison=val_comp,
                    quality_comparison=qual_comp,
                    why_cheaper=why_cheaper,
                    what_breaks_thesis=what_breaks,
                    liquidity_suitability=liq_suitability,
                    ai_exposure_score=c_score.total_score,
                ),
            )
        )

    candidates.sort(key=lambda item: item[0], reverse=True)
    shortlist = [c[1] for c in candidates[: max(3, min(5, top_n))]]

    return ValueAlternativeReport(
        target_symbol=t_sym,
        target_company_name=t_sec["company_name"],
        target_trailing_pe=t_pe,
        target_ev_ebitda=t_ev,
        target_ai_exposure_score=t_score.total_score,
        alternatives=shortlist,
    )


def _explain_why_cheaper(
    t_sec: dict[str, Any],
    t_f: dict[str, Any],
    c_sec: dict[str, Any],
    c_f: dict[str, Any],
    pe_disc_pct: float | None,
    ev_disc_pct: float | None,
) -> str:
    reasons: list[str] = []
    t_mcap = t_f.get("market_cap_inr_cr") or 0.0
    c_mcap = c_f.get("market_cap_inr_cr") or 0.0
    if c_mcap > 0 and t_mcap > c_mcap * 1.8:
        reasons.append(
            f"Smaller market-cap footprint (Rs {c_mcap:,.0f} Cr vs {t_sec['symbol']} Rs {t_mcap:,.0f} Cr) with lower passive ETF/FII index inclusion premium"
        )
    t_roce = t_f.get("roce_pct")
    c_roce = c_f.get("roce_pct")
    if t_roce is not None and c_roce is not None and t_roce - c_roce > 4.0:
        reasons.append(f"Slightly lower historical ROCE ({c_roce:.1f}% vs {t_roce:.1f}%) due to ongoing capex/working-capital intensity")
    c_wc = c_f.get("working_capital_days")
    t_wc = t_f.get("working_capital_days")
    if c_wc is not None and t_wc is not None and c_wc > t_wc + 15:
        reasons.append(f"Longer working-capital cycle ({c_wc:.0f} days vs {t_wc:.0f} days) typical of B2B/utility order execution")
    if not reasons:
        reasons.append(
            "Less retail/media 'pure-play AI' narrative premium despite supplying critical components into the same power/cooling/compute buildout"
        )
    disc_txt = f" (~{pe_disc_pct:.1f}% P/E discount)" if pe_disc_pct is not None else (
        f" (~{ev_disc_pct:.1f}% EV/EBITDA discount)" if ev_disc_pct is not None else ""
    )
    return "; ".join(reasons) + disc_txt + "."


def _explain_thesis_risks(c_sec: dict[str, Any], c_f: dict[str, Any]) -> str:
    risks: list[str] = []
    wc = c_f.get("working_capital_days")
    if wc is not None and wc > 85:
        risks.append(f"Working-capital stretch ({wc:.0f} days) if state utility or EPC customer payments delay")
    ob = c_f.get("order_book_to_LTM_sales")
    if ob is not None and ob > 1.5:
        risks.append("Raw material (copper/CRGO steel/semiconductor) price volatility on fixed-price order backlog")
    d_to_e = c_f.get("debt_to_equity")
    if d_to_e is not None and d_to_e > 0.6:
        risks.append(f"Balance-sheet leverage ({d_to_e:.2f}x D/E) if interest rates remain elevated or capex ramp slips")
    if not risks:
        risks.append("Slowdown in domestic hyperscale colocation capex, export tariff headwinds, or margin compression from competitive bidding")
    return "; ".join(risks) + "."


def _assess_liquidity_suitability(
    c_sec: dict[str, Any],
    c_f: dict[str, Any],
    min_daily_turnover_cr: float,
) -> str:
    turnover = c_f.get("avg_daily_turnover_inr_cr") or 0.0
    mcap = c_f.get("market_cap_inr_cr") or 0.0
    if turnover >= 50.0 and mcap >= 25000.0:
        return f"HIGH_LIQUIDITY (Rs {turnover:.1f} Cr/day ADV): Suitable for core portfolio weights up to 8-10%."
    if turnover >= 10.0 and mcap >= 4000.0:
        return f"MODERATE_LIQUIDITY (Rs {turnover:.1f} Cr/day ADV): Suitable for satellite weights of 3-6% with limit orders."
    if turnover >= min_daily_turnover_cr:
        return f"SMALL_CAP_LIQUIDITY (Rs {turnover:.1f} Cr/day ADV): Cap position size at <=3% and stagger entries."
    return f"LOW_LIQUIDITY_WARNING (Rs {turnover:.2f} Cr/day ADV): Below institutional liquidity threshold; research/micro-sizing only."
