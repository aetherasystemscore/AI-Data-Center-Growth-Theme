"""AI Infrastructure Exposure Scoring Engine (100-point model + 8 configurable profiles + mandatory risk flags)."""

from __future__ import annotations

from typing import Any

from analytics.valuation import _score_valuation_reasonableness_100
from core.schemas import (
    EvidenceType,
    ExposureScoreBreakdown,
    RiskFlag,
    RiskFlagSeverity,
    ScoringProfile,
)

# Profile weights across the 7 scoring components (must sum to 1.0; rescaled to 100 points)
# Default base weights per Section 11 of Master Prompt:
# Direct AI/DC rev: 25%, Confirmed contract: 15%, Customer quality: 15%,
# Supply-chain criticality: 15%, Margin & ROCE: 10%, Balance sheet: 10%, Valuation: 10%
SCORING_PROFILE_WEIGHTS: dict[str, dict[str, float]] = {
    ScoringProfile.DEFAULT_100PT.value: {
        "direct_ai_dc_revenue_score": 0.25,
        "contract_backlog_visibility_score": 0.15,
        "customer_quality_score": 0.15,
        "supply_chain_criticality_score": 0.15,
        "margin_and_roce_score": 0.10,
        "balance_sheet_strength_score": 0.10,
        "valuation_reasonableness_score": 0.10,
    },
    ScoringProfile.CONSERVATIVE_QUALITY.value: {
        "direct_ai_dc_revenue_score": 0.18,
        "contract_backlog_visibility_score": 0.15,
        "customer_quality_score": 0.17,
        "supply_chain_criticality_score": 0.12,
        "margin_and_roce_score": 0.15,
        "balance_sheet_strength_score": 0.15,
        "valuation_reasonableness_score": 0.08,
    },
    ScoringProfile.BALANCED_GARP.value: {
        "direct_ai_dc_revenue_score": 0.20,
        "contract_backlog_visibility_score": 0.15,
        "customer_quality_score": 0.13,
        "supply_chain_criticality_score": 0.12,
        "margin_and_roce_score": 0.13,
        "balance_sheet_strength_score": 0.10,
        "valuation_reasonableness_score": 0.17,
    },
    ScoringProfile.HIGH_GROWTH_INFRA.value: {
        "direct_ai_dc_revenue_score": 0.30,
        "contract_backlog_visibility_score": 0.20,
        "customer_quality_score": 0.15,
        "supply_chain_criticality_score": 0.17,
        "margin_and_roce_score": 0.08,
        "balance_sheet_strength_score": 0.05,
        "valuation_reasonableness_score": 0.05,
    },
    ScoringProfile.SMALL_CAP_SUPPLIERS.value: {
        "direct_ai_dc_revenue_score": 0.22,
        "contract_backlog_visibility_score": 0.18,
        "customer_quality_score": 0.14,
        "supply_chain_criticality_score": 0.20,
        "margin_and_roce_score": 0.10,
        "balance_sheet_strength_score": 0.08,
        "valuation_reasonableness_score": 0.08,
    },
    ScoringProfile.CIRCULAR_ECONOMY_FOCUS.value: {
        "direct_ai_dc_revenue_score": 0.20,
        "contract_backlog_visibility_score": 0.15,
        "customer_quality_score": 0.15,
        "supply_chain_criticality_score": 0.15,
        "margin_and_roce_score": 0.12,
        "balance_sheet_strength_score": 0.13,
        "valuation_reasonableness_score": 0.10,
    },
    ScoringProfile.VALUE_CONTRARIAN.value: {
        "direct_ai_dc_revenue_score": 0.16,
        "contract_backlog_visibility_score": 0.14,
        "customer_quality_score": 0.12,
        "supply_chain_criticality_score": 0.13,
        "margin_and_roce_score": 0.12,
        "balance_sheet_strength_score": 0.11,
        "valuation_reasonableness_score": 0.22,
    },
    ScoringProfile.LOW_VOLATILITY_DEFENSIVE.value: {
        "direct_ai_dc_revenue_score": 0.16,
        "contract_backlog_visibility_score": 0.16,
        "customer_quality_score": 0.16,
        "supply_chain_criticality_score": 0.12,
        "margin_and_roce_score": 0.14,
        "balance_sheet_strength_score": 0.16,
        "valuation_reasonableness_score": 0.10,
    },
    ScoringProfile.IPO_NEW_LISTING.value: {
        "direct_ai_dc_revenue_score": 0.26,
        "contract_backlog_visibility_score": 0.18,
        "customer_quality_score": 0.14,
        "supply_chain_criticality_score": 0.16,
        "margin_and_roce_score": 0.10,
        "balance_sheet_strength_score": 0.08,
        "valuation_reasonableness_score": 0.08,
    },
}


# Supply-chain criticality multipliers by primary category
CRITICALITY_BASE_BY_CATEGORY: dict[str, float] = {
    "A_COMPUTE_HARDWARE": 13.5,
    "B_ELECTRONIC_COMPONENTS": 11.5,
    "C_DATACENTRE_INFRA": 13.0,
    "D_POWER_AND_GRID": 13.5,
    "E_COOLING_THERMAL": 12.5,
    "F_CONNECTIVITY_FIBRE": 11.5,
    "G_ENTERPRISE_AI_IT": 10.0,
    "H_CIRCULAR_ELECTRONICS": 10.5,
}


def score_company_exposure(
    sec: dict[str, Any],
    f: dict[str, Any],
    profile: str = ScoringProfile.DEFAULT_100PT.value,
) -> ExposureScoreBreakdown:
    """Compute the 100-point AI Infrastructure Exposure Score, profile-adjusted score, and mandatory risk flags.

    CRITICAL INVARIANTS ENFORCED:
    1. Companies with `evidence_type` in ('PRESS_RELEASE_ONLY', 'ANNOUNCED_PLAN', 'UNVERIFIED_NARRATIVE')
       cannot receive full Direct AI/DC revenue or Contract Backlog points — capped strictly to prevent
       narrative hype from masquerading as realised revenue.
    2. Severe governance, liquidity, or balance-sheet flags (`CRITICAL` severity) NEVER get hidden by a
       composite score; `has_critical_red_flag=True` and `investability_blocked=True` are set explicitly.
    """
    symbol = sec["symbol"]
    ev_type_str = (f.get("evidence_type") or EvidenceType.INDIRECT_INFRASTRUCTURE.value).upper()
    try:
        evidence_type = EvidenceType(ev_type_str)
    except ValueError:
        evidence_type = EvidenceType.INDIRECT_INFRASTRUCTURE

    is_narrative_only = evidence_type in (
        EvidenceType.PRESS_RELEASE_ONLY,
        EvidenceType.ANNOUNCED_PLAN,
        EvidenceType.UNVERIFIED_NARRATIVE,
    )

    # 1. Direct AI / Data-Centre Revenue Share (Max 25 points)
    direct_rev_pct = f.get("direct_ai_dc_rev_share_pct")
    if direct_rev_pct is None or direct_rev_pct <= 0:
        direct_score = 0.0
    elif direct_rev_pct >= 50.0:
        direct_score = 25.0
    elif direct_rev_pct >= 30.0:
        direct_score = 20.0 + ((direct_rev_pct - 30.0) / 20.0) * 5.0
    elif direct_rev_pct >= 15.0:
        direct_score = 13.0 + ((direct_rev_pct - 15.0) / 15.0) * 7.0
    else:
        direct_score = (direct_rev_pct / 15.0) * 13.0

    # Enforce Fact-vs-Narrative cap: press releases / unverified plans cannot exceed 5.0/25 on direct revenue
    if is_narrative_only:
        direct_score = min(direct_score, 5.0)
    direct_score = round(max(0.0, min(25.0, direct_score)), 2)

    # 2. Confirmed Contract / Order-Book Visibility (Max 15 points)
    ob_to_sales = f.get("order_book_to_LTM_sales")
    ob_cr = f.get("order_book_inr_cr")
    if evidence_type == EvidenceType.UNVERIFIED_NARRATIVE:
        contract_score = 0.0
    elif is_narrative_only:
        contract_score = 3.0
    elif ob_to_sales is not None and ob_to_sales > 0:
        contract_score = min(15.0, 5.0 + ob_to_sales * 4.5)
    elif ob_cr is not None and ob_cr > 0:
        contract_score = 10.5
    elif evidence_type in (EvidenceType.AUDITED_SEGMENT, EvidenceType.CONTRACT_DISCLOSURE):
        contract_score = 11.5
    elif evidence_type == EvidenceType.INDIRECT_INFRASTRUCTURE:
        contract_score = 8.0
    else:
        contract_score = 4.0
    contract_score = round(max(0.0, min(15.0, contract_score)), 2)

    # 3. Customer Quality & Concentration Risk (Max 15 points)
    mcap = f.get("market_cap_inr_cr") or 0.0
    if evidence_type == EvidenceType.UNVERIFIED_NARRATIVE:
        cust_score = 2.0
    elif mcap >= 50000:
        cust_score = 13.5
    elif mcap >= 10000:
        cust_score = 12.0
    elif mcap >= 2000:
        cust_score = 10.5
    else:
        cust_score = 7.5
    if (direct_rev_pct or 0.0) >= 20.0 and not is_narrative_only:
        cust_score = min(15.0, cust_score + 1.5)
    cust_score = round(max(0.0, min(15.0, cust_score)), 2)

    # 4. Supply-Chain Criticality & Switching Costs (Max 15 points)
    primary_cat = sec.get("primary_category", "D_POWER_AND_GRID")
    crit_score = CRITICALITY_BASE_BY_CATEGORY.get(primary_cat, 10.5)
    if evidence_type == EvidenceType.UNVERIFIED_NARRATIVE:
        crit_score = min(crit_score, 3.0)
    elif (direct_rev_pct or 0.0) < 2.0:
        crit_score = min(crit_score, 5.0)
    crit_score = round(max(0.0, min(15.0, crit_score)), 2)

    # 5. Operating Margin & ROCE Quality (Max 10 points)
    roce = f.get("roce_pct")
    ebitda_m = f.get("ebitda_margin_pct")
    m_pts: list[float] = []
    if roce is not None:
        m_pts.append(max(0.0, min(10.0, roce / 2.8)))
    if ebitda_m is not None:
        m_pts.append(max(0.0, min(10.0, ebitda_m / 2.6)))
    margin_roce_score = round(sum(m_pts) / len(m_pts), 2) if m_pts else 4.0

    # 6. Balance-Sheet & Cash-Conversion Strength (Max 10 points)
    d_to_e = f.get("debt_to_equity")
    int_cov = f.get("interest_coverage")
    cfo_ebitda = f.get("cfo_to_ebitda_pct")
    bs_pts: list[float] = []
    if d_to_e is not None:
        if d_to_e <= 0.2:
            bs_pts.append(9.5)
        elif d_to_e <= 0.6:
            bs_pts.append(8.0)
        elif d_to_e <= 1.2:
            bs_pts.append(6.0)
        elif d_to_e <= 2.5:
            bs_pts.append(3.5)
        else:
            bs_pts.append(0.5)
    if int_cov is not None:
        bs_pts.append(9.5 if int_cov >= 8.0 else (7.0 if int_cov >= 3.5 else (4.0 if int_cov >= 1.5 else 0.5)))
    if cfo_ebitda is not None:
        bs_pts.append(max(1.0, min(10.0, cfo_ebitda / 9.5)))
    balance_sheet_score = round(sum(bs_pts) / len(bs_pts), 2) if bs_pts else 4.0

    # 7. Valuation Reasonableness vs Growth (Max 10 points)
    val_100 = _score_valuation_reasonableness_100(
        trailing_pe=f.get("trailing_pe"),
        forward_pe=f.get("forward_pe"),
        ev_ebitda=f.get("ev_ebitda"),
        peg_ratio=f.get("peg_ratio"),
        fcf_yield_pct=f.get("fcf_yield_pct"),
        pb=f.get("price_to_book"),
    )
    valuation_score = round(max(0.0, min(10.0, val_100 / 10.0)), 2)

    total_base_score = round(
        direct_score
        + contract_score
        + cust_score
        + crit_score
        + margin_roce_score
        + balance_sheet_score
        + valuation_score,
        2,
    )

    # Profile-weighted composite score (normalise each component to 0..100 first, then apply profile weights)
    norm_components = {
        "direct_ai_dc_revenue_score": (direct_score / 25.0) * 100.0,
        "contract_backlog_visibility_score": (contract_score / 15.0) * 100.0,
        "customer_quality_score": (cust_score / 15.0) * 100.0,
        "supply_chain_criticality_score": (crit_score / 15.0) * 100.0,
        "margin_and_roce_score": (margin_roce_score / 10.0) * 100.0,
        "balance_sheet_strength_score": (balance_sheet_score / 10.0) * 100.0,
        "valuation_reasonableness_score": (valuation_score / 10.0) * 100.0,
    }
    weights = SCORING_PROFILE_WEIGHTS.get(profile, SCORING_PROFILE_WEIGHTS[ScoringProfile.DEFAULT_100PT.value])
    profile_score = sum(norm_components[k] * w for k, w in weights.items())

    # Apply specialized factor tilts across the 9 ScoringProfile options
    rev_cagr_3y = float(f.get("rev_cagr_3y_pct") or 0.0)
    pat_cagr_3y = float(f.get("pat_cagr_3y_pct") or 0.0)
    t_pe = f.get("trailing_pe")
    peg = f.get("peg_ratio")

    if profile == ScoringProfile.HIGH_GROWTH_INFRA.value:
        growth_signal = (rev_cagr_3y * 0.65) + (pat_cagr_3y * 0.35)
        profile_score = (profile_score * 0.45) + min(55.0, growth_signal * 1.15)
        if sec.get("primary_category") in ("C_DATACENTRE_INFRA", "A_COMPUTE_HARDWARE", "B_ELECTRONIC_COMPONENTS"):
            profile_score += 11.0
        if (ebitda_m or 0.0) >= 18.0 and (roce or 0.0) >= 26.0:
            profile_score += 8.5
        if (ebitda_m or 15.0) < 12.0 or rev_cagr_3y < 17.0:
            profile_score -= 16.0
    elif profile == ScoringProfile.SMALL_CAP_SUPPLIERS.value:
        if 500.0 <= mcap <= 32000.0 and sec.get("primary_category") in (
            "B_ELECTRONIC_COMPONENTS",
            "D_POWER_AND_GRID",
            "E_COOLING_THERMAL",
            "A_COMPUTE_HARDWARE",
        ):
            profile_score += 10.5
        elif mcap > 65000.0:
            profile_score -= 9.5
    elif profile == ScoringProfile.CONSERVATIVE_QUALITY.value:
        if (roce or 0.0) >= 22.0 and (d_to_e is not None and d_to_e <= 0.45):
            profile_score += 7.5
        if t_pe is not None and t_pe > 75.0:
            profile_score -= 7.0
    elif profile == ScoringProfile.BALANCED_GARP.value:
        if peg is not None and 0.4 <= peg <= 2.3 and (roce or 0.0) >= 18.0:
            profile_score += 8.0
        elif t_pe is not None and t_pe > 85.0:
            profile_score -= 6.5
    elif profile == ScoringProfile.VALUE_CONTRARIAN.value:
        if t_pe is not None and t_pe <= 38.0:
            profile_score += 11.0
        elif t_pe is not None and t_pe >= 65.0:
            profile_score -= 10.5
    elif profile == ScoringProfile.LOW_VOLATILITY_DEFENSIVE.value:
        if mcap >= 35000.0 and (d_to_e is None or d_to_e <= 1.3):
            profile_score += 9.5
        elif mcap < 15000.0:
            profile_score -= 8.5
    elif profile == ScoringProfile.CIRCULAR_ECONOMY_FOCUS.value:
        if "H_CIRCULAR_ELECTRONICS" in sec.get("sector_tags", []):
            profile_score += 14.0
        elif sec.get("primary_category") in ("E_COOLING_THERMAL", "D_POWER_AND_GRID") and (cfo_ebitda or 0.0) >= 75.0:
            profile_score += 5.0
    elif profile == ScoringProfile.IPO_NEW_LISTING.value:
        if f.get("rev_cagr_5y_pct") is None and f.get("rev_cagr_3y_pct") is not None:
            profile_score += 9.5
        elif str(sec.get("listing_date") or "") >= "2022-01-01":
            profile_score += 6.0
        else:
            profile_score -= 4.0

    profile_score = round(max(0.0, min(100.0, profile_score)), 2)

    # Mandatory Risk Flags
    risk_flags = evaluate_company_risk_flags(sec=sec, f=f, is_narrative_only=is_narrative_only)
    has_critical = any(rf.severity == RiskFlagSeverity.CRITICAL for rf in risk_flags)
    investability_blocked = has_critical or (not bool(sec.get("is_investable", True)))

    return ExposureScoreBreakdown(
        symbol=symbol,
        direct_ai_dc_revenue_score=direct_score,
        contract_backlog_visibility_score=contract_score,
        customer_quality_score=cust_score,
        supply_chain_criticality_score=crit_score,
        margin_and_roce_score=margin_roce_score,
        balance_sheet_strength_score=balance_sheet_score,
        valuation_reasonableness_score=valuation_score,
        total_score=total_base_score,
        profile_name=profile,
        profile_adjusted_score=profile_score,
        evidence_type=evidence_type,
        evidence_citation=f.get("evidence_citation") or "No filing citation available",
        risk_flags=risk_flags,
        has_critical_red_flag=has_critical,
        investability_blocked=investability_blocked,
    )


def evaluate_company_risk_flags(
    sec: dict[str, Any],
    f: dict[str, Any],
    is_narrative_only: bool = False,
) -> list[RiskFlag]:
    """Generate explicit RiskFlag objects for governance, liquidity, leverage, cash conversion, and narrative hype."""
    flags: list[RiskFlag] = []

    # 1. Auditor qualification / severe governance red flag
    if bool(f.get("auditor_qualification_flag", False)):
        flags.append(
            RiskFlag(
                code="AUDITOR_QUALIFICATION_OR_REGULATORY_ACTION",
                severity=RiskFlagSeverity.CRITICAL,
                category="GOVERNANCE",
                description=f"Auditor qualification or regulatory enforcement noted ({f.get('governance_notes') or 'See exchange filings'}).",
                metric_value=1.0,
            )
        )

    gov_notes = (f.get("governance_notes") or "").lower()
    if "shell" in gov_notes or "holding company" in gov_notes or "not an electronics manufacturer" in gov_notes:
        flags.append(
            RiskFlag(
                code="NON_OPERATING_OR_UNVERIFIED_BUSINESS_RELEVANCE",
                severity=RiskFlagSeverity.CRITICAL,
                category="BUSINESS_RELEVANCE",
                description=f"Business relevance warning: {f.get('governance_notes')}",
                metric_value=f.get("direct_ai_dc_rev_share_pct"),
            )
        )

    # 2. Severe negative net worth / distressed debt service
    d_to_e = f.get("debt_to_equity")
    int_cov = f.get("interest_coverage")
    pat = f.get("pat_inr_cr")
    if (int_cov is not None and int_cov < 1.0) or (pat is not None and pat < -500.0):
        flags.append(
            RiskFlag(
                code="FINANCIAL_DISTRESS_LOW_INTEREST_COVERAGE",
                severity=RiskFlagSeverity.CRITICAL,
                category="BALANCE_SHEET",
                description=f"Severe financial distress: interest coverage {int_cov}x, PAT Rs {pat} Cr.",
                metric_value=int_cov,
            )
        )
    elif d_to_e is not None and d_to_e > 1.5:
        flags.append(
            RiskFlag(
                code="HIGH_LEVERAGE",
                severity=RiskFlagSeverity.WARNING,
                category="BALANCE_SHEET",
                description=f"Elevated debt-to-equity ratio of {d_to_e:.2f}x.",
                metric_value=d_to_e,
            )
        )

    # 3. Liquidity & SME/micro-cap execution risk
    turnover = f.get("avg_daily_turnover_inr_cr")
    if turnover is not None and turnover < 2.0 and sec.get("geography") == "INDIA":
        sev = RiskFlagSeverity.CRITICAL if not sec.get("is_investable", True) else RiskFlagSeverity.HIGH
        flags.append(
            RiskFlag(
                code="ILLIQUID_MICROCAP_OR_SME_EXECUTION_RISK",
                severity=sev,
                category="LIQUIDITY",
                description=f"Low average daily turnover (Rs {turnover:.2f} Cr/day < Rs 2.0 Cr threshold); high impact-cost risk.",
                metric_value=turnover,
            )
        )

    # 4. Narrative-only / press-release hype risk
    if is_narrative_only:
        flags.append(
            RiskFlag(
                code="NARRATIVE_OR_ANNOUNCED_PLAN_NOT_REALISED_REVENUE",
                severity=RiskFlagSeverity.HIGH,
                category="EVIDENCE_QUALITY",
                description="AI/Data-centre exposure is currently based on announcements or narrative rather than audited segment revenue.",
                metric_value=f.get("direct_ai_dc_rev_share_pct"),
            )
        )

    # 5. Working capital / low cash conversion warning
    wc_days = f.get("working_capital_days")
    cfo_ebitda = f.get("cfo_to_ebitda_pct")
    if (wc_days is not None and wc_days > 110) or (cfo_ebitda is not None and cfo_ebitda < 55.0):
        flags.append(
            RiskFlag(
                code="WORKING_CAPITAL_STRETCH_OR_WEAK_CASH_CONVERSION",
                severity=RiskFlagSeverity.WARNING,
                category="CASH_FLOW",
                description=f"Working capital cycle ({wc_days} days) or CFO/EBITDA ({cfo_ebitda}%) requires monitoring.",
                metric_value=wc_days,
            )
        )

    # 6. Extreme valuation multiple warning
    t_pe = f.get("trailing_pe")
    if t_pe is not None and t_pe > 75.0:
        flags.append(
            RiskFlag(
                code="EXTREME_VALUATION_MULTIPLE",
                severity=RiskFlagSeverity.WARNING,
                category="VALUATION",
                description=f"Trailing P/E of {t_pe:.1f}x prices in multi-year flawless execution; check Value Alternative Finder.",
                metric_value=t_pe,
            )
        )

    return flags
