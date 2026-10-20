"""Tests for the AI document extraction, structured memo generation, and Fact-vs-Narrative invariants."""

from __future__ import annotations

from ai.document_extraction import extract_facts_from_filing_text
from ai.research_summariser import generate_company_research_memo
from core.schemas import EvidenceType
from database.repository import AI3Repository


def test_document_extractor_distinguishes_mou_press_release_from_audited_contract() -> None:
    mou_text = (
        "Company announced a non-binding Memorandum of Understanding (MoU) press release exploring "
        "potential AI data centre opportunities. No orders have been executed."
    )
    out_mou = extract_facts_from_filing_text("TESTMOU", mou_text)
    assert out_mou.is_realised_revenue is False
    assert out_mou.evidence_type in (EvidenceType.PRESS_RELEASE_ONLY, EvidenceType.ANNOUNCED_PLAN)
    assert len(out_mou.narrative_warnings) >= 1

    audited_text = (
        "Audited segment disclosures confirm executed contract and confirmed order book of Rs 4,250 Cr "
        "for 220kV data-centre GIS substations and 400 MVA power transformers."
    )
    out_aud = extract_facts_from_filing_text("HITACHIEN", audited_text)
    assert out_aud.is_realised_revenue is True
    assert out_aud.evidence_type == EvidenceType.AUDITED_SEGMENT
    assert out_aud.extracted_order_book_inr_cr == 4250.0
    assert out_aud.extracted_capex_mw_or_mva is not None


def test_research_memo_schema_validation_offline(tmp_path) -> None:
    repo = AI3Repository(db_path=tmp_path / "test_ai_memo.db")
    repo.bootstrap_if_needed()
    sec = repo.get_security_by_symbol("HITACHIEN")
    f = repo.get_latest_fundamentals_map()["HITACHIEN"]
    memo = generate_company_research_memo(sec, f)

    assert memo.symbol == "HITACHIEN"
    assert len(memo.bull_case) >= 2
    assert len(memo.bear_case_and_risks) >= 1
    assert len(memo.evidence_citations) >= 1
