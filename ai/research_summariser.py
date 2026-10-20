"""Structured AI research memo generator combining deterministic financial facts with optional LLM synthesis."""

from __future__ import annotations

from typing import Any

from ai.base_provider import BaseAIProvider
from ai.deepseek_provider import DeepSeekAIProvider
from ai.gemini_provider import GeminiAIProvider
from ai.local_provider import LocalRuleAndOllamaProvider
from analytics.exposure_scoring import score_company_exposure
from core.schemas import AIResearchMemo


def get_active_ai_provider(preferred: str | None = None) -> BaseAIProvider:
    """Return the requested or first-available AI provider, defaulting safely to deterministic rules."""
    pref = (preferred or "").upper()
    ds = DeepSeekAIProvider()
    gm = GeminiAIProvider()
    loc = LocalRuleAndOllamaProvider()

    if pref == "DEEPSEEK" and ds.is_available():
        return ds
    if pref == "GEMINI" and gm.is_available():
        return gm
    if ds.is_available():
        return ds
    if gm.is_available():
        return gm
    return loc


def generate_company_research_memo(
    sec: dict[str, Any],
    f: dict[str, Any],
    news_items: list[dict[str, Any]] | None = None,
    provider_preference: str | None = None,
) -> AIResearchMemo:
    """Produce a schema-validated `AIResearchMemo` grounded strictly in verified repository facts."""
    sym = sec["symbol"]
    score_bd = score_company_exposure(sec, f)

    citations: list[str] = []
    if f.get("evidence_citation"):
        citations.append(f"[{f.get('source_name', 'FILING')}] {f['evidence_citation']}")
    for n in (news_items or [])[:3]:
        citations.append(f"[{n.get('published_date')} | {n.get('source_name')}] {n.get('headline')}")
    if not citations:
        citations.append(f"[SECURITY_MASTER] {sec.get('notes') or 'Categorised under ' + sec.get('primary_category', '')}")

    direct_rev = f.get("direct_ai_dc_rev_share_pct")
    ob_cr = f.get("order_book_inr_cr")
    roce = f.get("roce_pct")
    t_pe = f.get("trailing_pe")

    bull_points = [
        f"Positioned in `{sec.get('primary_category')}` ({', '.join(sec.get('subcategories', []))}): {sec.get('notes') or ''}",
        (
            f"Estimated direct AI / data-centre / critical power revenue attribution of {direct_rev:.1f}% "
            f"(Evidence classification: {score_bd.evidence_type.value})."
            if direct_rev is not None
            else "Broad industrial/infrastructure exposure with optionality on data-centre capex."
        ),
    ]
    if ob_cr is not None and ob_cr > 0:
        bull_points.append(
            f"Reported order book of Rs {ob_cr:,.0f} Cr ({f.get('order_book_to_LTM_sales') or 'N/A'}x LTM sales; horizon: {f.get('order_book_execution_horizon') or 'Multi-quarter'})."
        )
    if roce is not None and roce >= 18.0:
        bull_points.append(f"Strong capital efficiency with ROCE of {roce:.1f}% and EBITDA margin of {f.get('ebitda_margin_pct')}%.")

    bear_points = [rf.description for rf in score_bd.risk_flags]
    if not bear_points:
        bear_points.append(
            f"Valuation sensitivity (Trailing P/E: {t_pe if t_pe is not None else 'N/A'}x) and execution timing of hyperscale/utility capex."
        )

    uncertainties = [
        "Quarterly order conversion cadence and customer concentration across top colocation/cloud buyers.",
    ]
    if f.get("rev_cagr_5y_pct") is None:
        uncertainties.append("5-year historical revenue CAGR is unavailable (newly listed / shorter listed track record).")

    deterministic_dict: dict[str, Any] = {
        "symbol": sym,
        "company_name": sec["company_name"],
        "fact_vs_narrative_verdict": (
            f"{score_bd.evidence_type.value}: AI Exposure Score {score_bd.total_score:.1f}/100 "
            f"({'INVESTABLE' if not score_bd.investability_blocked else 'HIGH-RISK / NON-INVESTABLE'})."
        ),
        "verified_business_exposure": (
            f"{sec['company_name']} ({sym}) operates in {sec.get('primary_category')} with "
            f"estimated AI/DC revenue share of {direct_rev if direct_rev is not None else 'N/A'}%. "
            f"Primary KPI: {f.get('sector_kpi_name') or 'N/A'} = {f.get('sector_kpi_value') if f.get('sector_kpi_value') is not None else 'N/A'} {f.get('sector_kpi_unit') or ''}."
        ),
        "bull_case": bull_points,
        "bear_case_and_risks": bear_points,
        "key_uncertainties": uncertainties,
        "evidence_citations": citations,
        "generated_by": "DETERMINISTIC_RULE_ENGINE",
    }

    provider = get_active_ai_provider(preferred=provider_preference)
    if provider.provider_name != "DETERMINISTIC_RULE_ENGINE" and provider.is_available():
        sys_prompt = (
            "You are a senior Indian institutional equity analyst. Summarize ONLY the provided verified JSON facts. "
            "Never invent numbers, contracts, customers, or ratios. Return JSON matching keys: "
            "symbol, company_name, fact_vs_narrative_verdict, verified_business_exposure, bull_case, "
            "bear_case_and_risks, key_uncertainties, evidence_citations."
        )
        usr_prompt = f"Verified Company Data: {deterministic_dict}"
        llm_out = provider.generate_structured_json(sys_prompt, usr_prompt, deterministic_dict)
        try:
            return AIResearchMemo(**llm_out)
        except Exception:
            return AIResearchMemo(**deterministic_dict)

    return AIResearchMemo(**deterministic_dict)
