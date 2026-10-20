"""Tests for the 100-point AI Exposure Scoring Model, 8 profiles, risk flags, and Value Alternative Finder."""

from __future__ import annotations

from analytics.exposure_scoring import SCORING_PROFILE_WEIGHTS, score_company_exposure
from analytics.fundamentals import evaluate_fundamental_health
from analytics.valuation import compute_valuation_metrics
from analytics.value_alternatives import find_value_alternatives
from core.schemas import EvidenceType, ScoringProfile
from database.repository import AI3Repository


def test_exposure_scoring_across_all_profiles(tmp_path) -> None:
    repo = AI3Repository(db_path=tmp_path / "test_ai3.db")
    repo.bootstrap_if_needed()

    sec = repo.get_security_by_symbol("NETWEB")
    f_map = repo.get_latest_fundamentals_map()
    f = f_map["NETWEB"]

    for profile in ScoringProfile:
        bd = score_company_exposure(sec, f, profile=profile.value)
        assert 0.0 <= bd.total_score <= 100.0
        assert 0.0 <= bd.profile_adjusted_score <= 100.0
        assert bd.investability_blocked is False


def test_press_release_never_treated_as_realised_revenue() -> None:
    sec = {
        "symbol": "HYPESTOCK",
        "company_name": "Hype Narrative Corp",
        "primary_category": "C_DATACENTRE_INFRA",
        "sector_tags": ["C_DATACENTRE_INFRA"],
        "is_investable": True,
        "geography": "INDIA",
    }
    # Even if someone claims 80% AI revenue in a press release, score_company_exposure caps direct_score <= 5.0
    f_press = {
        "symbol": "HYPESTOCK",
        "direct_ai_dc_rev_share_pct": 80.0,
        "evidence_type": EvidenceType.PRESS_RELEASE_ONLY.value,
        "roce_pct": 18.0,
        "ebitda_margin_pct": 15.0,
        "debt_to_equity": 0.3,
        "trailing_pe": 30.0,
    }
    bd = score_company_exposure(sec, f_press)
    assert bd.direct_ai_dc_revenue_score <= 5.0
    assert bd.contract_backlog_visibility_score <= 3.0
    assert any("NARRATIVE" in rf.code for rf in bd.risk_flags)


def test_severe_governance_warning_blocks_investability(tmp_path) -> None:
    repo = AI3Repository(db_path=tmp_path / "test_gov.db")
    repo.bootstrap_if_needed()
    f_map = repo.get_latest_fundamentals_map()

    cerebra_sec = repo.get_security_by_symbol("CEREBRAINT")
    cerebra_f = f_map["CEREBRAINT"]
    bd = score_company_exposure(cerebra_sec, cerebra_f)
    assert bd.has_critical_red_flag is True
    assert bd.investability_blocked is True
    assert any(rf.code == "AUDITOR_QUALIFICATION_OR_REGULATORY_ACTION" for rf in bd.risk_flags)


def test_newly_listed_company_retained_with_null_5y_cagr(tmp_path) -> None:
    repo = AI3Repository(db_path=tmp_path / "test_new_list.db")
    repo.bootstrap_if_needed()
    f_map = repo.get_latest_fundamentals_map()

    for sym in ("NETWEB", "CYIENTDLM", "AVALON", "RRKABEL"):
        f = f_map[sym]
        assert f["rev_cagr_5y_pct"] is None, f"{sym} has <5Y listed history; 5Y CAGR must be None, not 0"
        fh = evaluate_fundamental_health(f)
        assert fh["is_newly_listed"] is True
        assert fh["growth_score"] is not None and fh["growth_score"] > 50.0


def test_value_alternative_finder_returns_cheaper_peers(tmp_path) -> None:
    repo = AI3Repository(db_path=tmp_path / "test_val_alt.db")
    repo.bootstrap_if_needed()
    all_secs = repo.get_securities()
    f_map = repo.get_latest_fundamentals_map()

    for target in ("DIXON", "ABB", "CUMMINSIND", "HITACHIEN"):
        report = find_value_alternatives(
            target_symbol=target,
            securities=all_secs,
            fundamentals_map=f_map,
            top_n=4,
        )
        assert len(report.alternatives) >= 3
        for alt in report.alternatives:
            assert alt.symbol != target
            assert alt.similarity_score >= 22.0
            # Ensure non-investable stocks are never recommended as value alternatives
            alt_sec = repo.get_security_by_symbol(alt.symbol)
            assert alt_sec["is_investable"] is True
            assert len(alt.why_cheaper) > 10
            assert len(alt.what_breaks_thesis) > 10
