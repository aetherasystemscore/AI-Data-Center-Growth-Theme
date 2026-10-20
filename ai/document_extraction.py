"""Document & DRHP/Filing extraction engine with fact-vs-narrative classification."""

from __future__ import annotations

import re
from typing import Any

from core.schemas import EvidenceType
from pydantic import BaseModel, Field


class DocumentExtractionOutput(BaseModel):
    """Validated structured extraction from an annual report, investor presentation, or DRHP excerpt."""

    symbol_or_entity: str
    evidence_type: EvidenceType
    is_realised_revenue: bool
    extracted_order_book_inr_cr: float | None = None
    extracted_capex_mw_or_mva: str | None = None
    key_facts: list[str] = Field(default_factory=list)
    narrative_warnings: list[str] = Field(default_factory=list)
    supporting_quotes: list[str] = Field(default_factory=list)
    generated_by: str = "DETERMINISTIC_DOCUMENT_EXTRACTOR"


def extract_facts_from_filing_text(
    symbol_or_entity: str,
    text: str,
) -> DocumentExtractionOutput:
    """Deterministically extract verifiable facts, order books, capacity metrics, and narrative warnings from filing text.

    CRITICAL INVARIANT: Never treats an MOU, press release, or 'exploring AI opportunities' statement
    as realised revenue (`is_realised_revenue=False`).
    """
    clean_text = (text or "").strip()
    low = clean_text.lower()

    # Detect whether text reflects audited/contracted execution vs unverified press release / MOU
    has_audited_kw = any(
        w in low
        for w in ("audited segment", "order book of rs", "executed contract", "delivered", "commissioned", "restated")
    )
    has_contract_kw = any(
        w in low
        for w in ("letter of award", "purchase order", "confirmed order", "backlog", "supply contract")
    )
    has_hype_kw = any(
        w in low
        for w in (
            "mou",
            "memorandum of understanding",
            "exploring",
            "plans to enter",
            "intends to",
            "press release",
            "non-binding",
            "proposed",
        )
    )

    if has_hype_kw and not has_audited_kw:
        ev_type = EvidenceType.PRESS_RELEASE_ONLY if "press release" in low or "mou" in low else EvidenceType.ANNOUNCED_PLAN
        is_realised = False
    elif has_audited_kw:
        ev_type = EvidenceType.AUDITED_SEGMENT
        is_realised = True
    elif has_contract_kw:
        ev_type = EvidenceType.CONTRACT_DISCLOSURE
        is_realised = True
    else:
        ev_type = EvidenceType.INDIRECT_INFRASTRUCTURE
        is_realised = False

    # Extract order book in Rs Cr if explicitly stated in text (never invent if absent)
    ob_val: float | None = None
    ob_match = re.search(r"rs\.?\s*([\d,]+(?:\.\d+)?)\s*(?:cr|crore)", low)
    if ob_match and ("order" in low or "backlog" in low):
        try:
            ob_val = float(ob_match.group(1).replace(",", ""))
        except ValueError:
            ob_val = None

    cap_match = re.search(r"(\d[\d,]*(?:\.\d+)?\s*(?:mw|mva|gw|kva|mtpa))", clean_text, flags=re.IGNORECASE)
    cap_str = cap_match.group(1) if cap_match else None

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_text) if s.strip()]
    facts: list[str] = []
    warnings: list[str] = []

    for sent in sentences:
        s_low = sent.lower()
        if any(w in s_low for w in ("mou", "non-binding", "exploring", "planned", "proposed", "intends")):
            warnings.append(f"Unconfirmed/Forward-looking statement: '{sent}'")
        elif any(w in s_low for w in ("order", "revenue", "capacity", "commissioned", "supplied", "ebitda", "mw", "mva")):
            facts.append(sent)

    if not is_realised and not warnings:
        warnings.append("Excerpt does not contain audited AI/data-centre revenue recognition; treat as exploratory or indirect.")

    return DocumentExtractionOutput(
        symbol_or_entity=symbol_or_entity,
        evidence_type=ev_type,
        is_realised_revenue=is_realised,
        extracted_order_book_inr_cr=ob_val,
        extracted_capex_mw_or_mva=cap_str,
        key_facts=facts[:5],
        narrative_warnings=warnings[:5],
        supporting_quotes=sentences[:3],
    )
