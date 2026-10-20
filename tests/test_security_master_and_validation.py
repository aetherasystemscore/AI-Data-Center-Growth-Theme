"""Tests for ticker verification, security master, corporate actions, IPO validation, and missing-data invariants."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from core.security_master import SecurityMasterService
from data.corporate_actions import (
    CorporateActionEvent,
    apply_point_in_time_adjustments,
    compute_bonus_adjustment_factor,
    compute_split_adjustment_factor,
)
from data.validation import (
    ensure_missing_not_zero,
    parse_optional_float,
    validate_ipo_record,
    validate_ohlcv_dataframe,
)


def test_security_master_deduplication_and_alias_resolution() -> None:
    sm = SecurityMasterService()
    all_secs = sm.get_all_securities()
    symbols = [s["symbol"] for s in all_secs]
    # Ensure strict deduplication of repeated seed tickers
    assert len(symbols) == len(set(symbols))
    assert len(all_secs) >= 70

    # Verify alias mapping
    assert sm.resolve_symbol("POWERINDIA") == "HITACHIEN"
    assert sm.resolve_symbol("TARIL") == "TRIL"
    assert sm.resolve_symbol("KPIL") == "KALPATARU"
    assert sm.resolve_symbol("BBOX") == "BLACKBOX"


def test_company_name_never_accepted_as_verified_ticker() -> None:
    sm = SecurityMasterService()
    is_valid, reason = sm.validate_ticker_is_not_company_name("Power Grid Corporation of India")
    assert is_valid is False
    assert "Company name" in reason or "whitespace" in reason

    is_valid_sym, _ = sm.validate_ticker_is_not_company_name("POWERGRID")
    assert is_valid_sym is True


def test_high_risk_and_unverified_candidates_not_investable() -> None:
    sm = SecurityMasterService()
    for sym in ("ELCIDIN", "BDL", "TTML", "ECORECO", "CEREBRAINT", "NAMOEWASTE", "ERI"):
        sec = sm.get_security(sym)
        assert sec is not None, f"Expected {sym} in security master"
        assert sec["is_investable"] is False, f"{sym} must not be automatically investable"
        assert sec["universe_tier"] == "HIGH_RISK_RESEARCH"


def test_corporate_action_split_and_bonus_adjustments() -> None:
    # 1:5 split (1 old share becomes 5 new shares -> historical prices multiplied by 0.20)
    assert pytest.approx(compute_split_adjustment_factor(5.0, 1.0)) == 0.20
    # 1:1 bonus issue -> historical prices multiplied by 0.50
    assert pytest.approx(compute_bonus_adjustment_factor(1.0, 1.0)) == 0.50

    df = pd.DataFrame(
        {
            "trade_date": [date(2024, 6, 10), date(2024, 6, 11), date(2024, 6, 12)],
            "open": [1000.0, 200.0, 205.0],
            "high": [1020.0, 210.0, 215.0],
            "low": [990.0, 195.0, 200.0],
            "close": [1000.0, 200.0, 210.0],
            "volume": [1000.0, 5000.0, 5200.0],
        }
    )
    events = [
        CorporateActionEvent(
            symbol="TEST",
            ex_date=date(2024, 6, 11),
            action_type="SPLIT",
            ratio_numerator=5.0,
            ratio_denominator=1.0,
        )
    ]
    adj = apply_point_in_time_adjustments(df, events)
    assert pytest.approx(float(adj.loc[0, "adj_close"])) == 200.0
    assert pytest.approx(float(adj.loc[1, "adj_close"])) == 200.0
    assert pytest.approx(float(adj.loc[0, "adj_volume"])) == 5000.0


def test_missing_data_never_converted_to_zero() -> None:
    assert parse_optional_float(None) is None
    assert parse_optional_float("") is None
    assert parse_optional_float("NA") is None
    assert parse_optional_float("null") is None
    assert parse_optional_float(float("nan")) is None
    assert parse_optional_float("0.0") == 0.0

    rec = {"symbol": "NETWEB", "rev_cagr_3y_pct": 54.0, "rev_cagr_5y_pct": ""}
    cleaned = ensure_missing_not_zero(rec, ["rev_cagr_3y_pct", "rev_cagr_5y_pct", "trailing_pe"])
    assert cleaned["rev_cagr_5y_pct"] is None
    assert cleaned["trailing_pe"] is None
    assert cleaned["rev_cagr_3y_pct"] == 54.0


def test_ipo_unconfirmed_dates_validation() -> None:
    invalid_ipo = {
        "ipo_id": "IPO_TEST",
        "company_name": "Test Infra Ltd",
        "dates_confirmed": False,
        "issue_open_date": "2026-05-01",
    }
    res = validate_ipo_record(invalid_ipo)
    assert res.is_valid is False
    assert any("dates_confirmed=False" in e for e in res.errors)

    valid_ipo = {
        "ipo_id": "IPO_TEST_OK",
        "company_name": "Test Infra Ltd",
        "dates_confirmed": False,
        "issue_open_date": None,
        "issue_close_date": None,
        "listing_date": None,
        "productive_capex_and_debt_repayment_pct": 80.0,
        "ofs_share_of_total_issue_pct": 20.0,
    }
    res_ok = validate_ipo_record(valid_ipo)
    assert res_ok.is_valid is True


def test_ohlcv_validation_catches_corrupt_bars() -> None:
    bad_df = pd.DataFrame(
        {
            "trade_date": [date(2025, 1, 1)],
            "open": [100.0],
            "high": [90.0],  # high < low!
            "low": [95.0],
            "close": [98.0],
            "volume": [1000.0],
        }
    )
    res = validate_ohlcv_dataframe(bad_df, "BADTICKER")
    assert res.is_valid is False
