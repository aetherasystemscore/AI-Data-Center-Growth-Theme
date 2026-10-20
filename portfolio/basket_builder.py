"""Custom thematic basket builder and regulatory/market-access advisor."""

from __future__ import annotations

from typing import Any

from analytics.exposure_scoring import score_company_exposure


MARKET_ACCESS_GUIDANCE: dict[str, dict[str, str]] = {
    "INDIA": {
        "access_route": "Direct NSE/BSE Demat Account (SEBI-regulated Indian resident equity/ETF trading).",
        "taxation_note": "Listed Indian Equity/ETF: STCG (<12M) at 20%, LTCG (>12M) at 12.5% above Rs 1.25 Lakh annual exemption (FY25/26 Finance Act).",
        "currency_risk": "INR-denominated (no direct FX conversion cost; underlying exporters/importers have operational FX sensitivity).",
        "regulatory_note": "Standard STT (0.1% delivery), exchange charges, SEBI turnover fee, and stamp duty apply.",
    },
    "US": {
        "access_route": "RBI Liberalised Remittance Scheme (LRS) up to USD 250,000/FY via IFSC GIFT City / international broker, or select domestic FoFs (subject to SEBI overseas ETF limit availability).",
        "taxation_note": "Unlisted/Foreign Equity rules for Indian residents: LTCG (>24M holding) at 12.5%; STCG (<=24M) taxed at applicable income-tax slab rate; 20% TCS above Rs 7 Lakh LRS remittance threshold.",
        "currency_risk": "USD/INR currency exposure + bank FX remittance spread (typically 0.50% - 1.50% per leg).",
        "regulatory_note": "Research Benchmark by default in AI3; do not assume every retail investor can execute direct international orders.",
    },
    "TAIWAN": {
        "access_route": "Primarily via US ADRs (e.g., TSM) or global semiconductor UCITS/US ETFs under LRS; direct TWSE access is restricted for Indian retail investors.",
        "taxation_note": "Foreign asset reporting in Schedule FA of ITR is mandatory for Indian residents holding overseas securities.",
        "currency_risk": "TWD / USD / INR cross-currency exposure.",
        "regulatory_note": "Included as a Global Supply-Chain Benchmark.",
    },
    "JAPAN": {
        "access_route": "Global international brokerage under RBI LRS or ADR/ETF wrappers; research benchmark for Indian investors.",
        "taxation_note": "Foreign equity taxation (24M LTCG threshold) + Schedule FA disclosure.",
        "currency_risk": "JPY/INR currency risk.",
        "regulatory_note": "Included as a Global Supply-Chain Benchmark.",
    },
    "SOUTH_KOREA": {
        "access_route": "Global Emerging Market / Semiconductor ETFs or GDRs; direct KRX retail access is generally unavailable to Indian residents.",
        "taxation_note": "Foreign equity taxation (24M LTCG threshold) + Schedule FA disclosure.",
        "currency_risk": "KRW/INR currency risk.",
        "regulatory_note": "Included as a Global Supply-Chain Benchmark.",
    },
    "EUROPE": {
        "access_route": "International broker under RBI LRS or US/UCITS listings; included as Global Supply-Chain Benchmark (whose Indian subsidiaries like ABB, SIEMENS, HITACHIEN are directly listed on NSE).",
        "taxation_note": "Foreign equity taxation (24M LTCG threshold) + Schedule FA disclosure.",
        "currency_risk": "EUR/INR currency risk.",
        "regulatory_note": "Compare parent valuation with NSE-listed Indian subsidiary in Value Alternative Finder.",
    },
}


def build_portfolio_summary(
    weights: dict[str, float],
    securities_map: dict[str, dict[str, Any]],
    fundamentals_map: dict[str, dict[str, Any]],
    profile: str = "DEFAULT_100PT",
) -> dict[str, Any]:
    """Compute weighted portfolio fundamentals, AI exposure score, subsector concentration, and constraint checks."""
    clean_w = {k.upper(): float(v) for k, v in weights.items() if float(v) > 0}
    total_w = sum(clean_w.values())
    if total_w <= 0:
        return {
            "holdings": [],
            "weighted_ai_exposure_score": 0.0,
            "weighted_direct_ai_rev_pct": 0.0,
            "weighted_pe": None,
            "weighted_roce_pct": None,
            "category_weights": {},
            "constraint_violations": [],
        }

    norm_w = {k: (v / total_w) * 100.0 for k, v in clean_w.items()}
    holdings: list[dict[str, Any]] = []
    cat_weights: dict[str, float] = {}
    high_risk_weight = 0.0

    weighted_score = 0.0
    weighted_direct_rev = 0.0
    pe_num = 0.0
    pe_den = 0.0
    roce_num = 0.0
    roce_den = 0.0

    violations: list[str] = []

    for sym, w_pct in sorted(norm_w.items(), key=lambda x: x[1], reverse=True):
        sec = securities_map.get(sym, {"symbol": sym, "company_name": sym, "primary_category": "OTHER", "is_investable": True})
        f = fundamentals_map.get(sym, {})
        score_bd = score_company_exposure(sec, f, profile=profile)

        cat = sec.get("primary_category", "OTHER")
        cat_weights[cat] = round(cat_weights.get(cat, 0.0) + w_pct, 2)

        if not sec.get("is_investable", True) or score_bd.investability_blocked:
            high_risk_weight += w_pct
            violations.append(
                f"{sym} ({w_pct:.1f}%) is flagged as HIGH_RISK_RESEARCH / non-investable ({[rf.code for rf in score_bd.risk_flags]})."
            )

        if w_pct > 10.05:
            violations.append(f"Single-stock weight cap exceeded: {sym} at {w_pct:.2f}% (> 10.0% default cap).")

        weighted_score += (w_pct / 100.0) * score_bd.profile_adjusted_score
        weighted_direct_rev += (w_pct / 100.0) * (f.get("direct_ai_dc_rev_share_pct") or 0.0)

        t_pe = f.get("trailing_pe")
        if t_pe is not None and t_pe > 0:
            pe_num += w_pct * t_pe
            pe_den += w_pct

        roce = f.get("roce_pct")
        if roce is not None:
            roce_num += w_pct * roce
            roce_den += w_pct

        holdings.append(
            {
                "symbol": sym,
                "company_name": sec.get("company_name", sym),
                "weight_pct": round(w_pct, 2),
                "primary_category": cat,
                "ai_exposure_score": score_bd.total_score,
                "profile_score": score_bd.profile_adjusted_score,
                "direct_ai_dc_rev_pct": f.get("direct_ai_dc_rev_share_pct"),
                "trailing_pe": t_pe,
                "roce_pct": roce,
                "avg_daily_turnover_inr_cr": f.get("avg_daily_turnover_inr_cr"),
                "evidence_type": score_bd.evidence_type.value,
                "risk_flags": [rf.code for rf in score_bd.risk_flags],
            }
        )

    for cat, cw in cat_weights.items():
        if cw > 30.05:
            violations.append(f"Subsector concentration cap exceeded: {cat} at {cw:.2f}% (> 30.0% cap).")

    return {
        "holdings": holdings,
        "weighted_ai_exposure_score": round(weighted_score, 2),
        "weighted_direct_ai_rev_pct": round(weighted_direct_rev, 2),
        "weighted_pe": round(pe_num / pe_den, 2) if pe_den > 0 else None,
        "weighted_roce_pct": round(roce_num / roce_den, 2) if roce_den > 0 else None,
        "category_weights": cat_weights,
        "high_risk_bucket_weight_pct": round(high_risk_weight, 2),
        "constraint_violations": violations,
    }
