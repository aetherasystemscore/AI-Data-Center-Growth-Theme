"""Tests for ETF & Smallcase overlap, look-through exposure, and all 8 portfolio optimisation methods."""

from __future__ import annotations

import pytest

from analytics.portfolio_optimisation import optimise_portfolio_weights
from analytics.portfolio_risk import run_portfolio_stress_tests
from core.schemas import OptimisationMethod
from database.repository import AI3Repository
from portfolio.overlap import (
    compare_smallcase_fee_vs_diy,
    compute_basket_overlap,
    compute_lookthrough_stock_exposure,
    parse_user_smallcase_csv,
)
from portfolio.rebalancing import compute_rebalance_trades, estimate_trade_cost_inr


def test_basket_overlap_calculation() -> None:
    b_a = {"INFY": 30.0, "TCS": 30.0, "PERSISTENT": 20.0, "NETWEB": 20.0}
    b_b = {"INFY": 25.0, "TCS": 15.0, "HCLTECH": 60.0}
    ov = compute_basket_overlap("Basket A", b_a, "Basket B", b_b)
    # min(30,25) + min(30,15) = 25 + 15 = 40%
    assert pytest.approx(ov.weighted_overlap_pct) == 40.0
    assert ov.shared_symbols_count == 2


def test_lookthrough_exposure_across_stocks_etfs_smallcases() -> None:
    lt = compute_lookthrough_stock_exposure(
        direct_stock_weights={"INFY": 20.0, "NETWEB": 20.0},
        etf_allocations={"ITBEES": 30.0},
        smallcase_allocations={"SC1": 30.0},
        etf_constituents_map={"ITBEES": {"INFY": 50.0, "TCS": 50.0}},
        smallcase_constituents_map={"SC1": {"NETWEB": 50.0, "HITACHIEN": 50.0}},
    )
    by_sym = {r["symbol"]: r for r in lt}
    # INFY = 20% direct + 30% * 50% (15%) = 35%
    assert pytest.approx(by_sym["INFY"]["total_weight_pct"]) == 35.0
    assert by_sym["INFY"]["is_crowded_across_sleeves"] is True
    # NETWEB = 20% direct + 30% * 50% (15%) = 35%
    assert pytest.approx(by_sym["NETWEB"]["total_weight_pct"]) == 35.0


def test_locked_smallcase_has_empty_constituents_and_csv_upload_works(tmp_path) -> None:
    repo = AI3Repository(db_path=tmp_path / "test_sc.db")
    repo.bootstrap_if_needed()
    scs = {s["smallcase_id"]: s for s in repo.get_smallcases()}
    locked = scs["SC_NIVESHAAY_TECHSTACK"]
    assert locked["constituents_locked"] is True
    assert locked["constituents"] == []

    csv_text = "symbol,weight_pct,role\nNETWEB,50,AI Servers\nHITACHIEN,50,HVDC"
    parsed = parse_user_smallcase_csv(csv_text)
    assert len(parsed) == 2
    assert pytest.approx(sum(p["weight_pct"] for p in parsed)) == 100.0


def test_all_eight_portfolio_optimisation_methods_and_constraints() -> None:
    symbols = [
        "POWERGRID",
        "HITACHIEN",
        "CGPOWER",
        "TRIL",
        "TDPOWERSYS",
        "CUMMINSIND",
        "POLYCAB",
        "NETWEB",
        "KAYNES",
        "BLUESTARCO",
        "ANANTRAJ",
        "PERSISTENT",
    ]
    scores = {s: 70.0 + idx for idx, s in enumerate(symbols)}
    mcaps = {s: 15000.0 + idx * 5000.0 for idx, s in enumerate(symbols)}
    cats = {
        "POWERGRID": "D_POWER_AND_GRID",
        "HITACHIEN": "D_POWER_AND_GRID",
        "CGPOWER": "D_POWER_AND_GRID",
        "TRIL": "D_POWER_AND_GRID",
        "TDPOWERSYS": "D_POWER_AND_GRID",
        "CUMMINSIND": "E_COOLING_THERMAL",
        "POLYCAB": "D_POWER_AND_GRID",
        "NETWEB": "A_COMPUTE_HARDWARE",
        "KAYNES": "B_ELECTRONIC_COMPONENTS",
        "BLUESTARCO": "E_COOLING_THERMAL",
        "ANANTRAJ": "C_DATACENTRE_INFRA",
        "PERSISTENT": "G_ENTERPRISE_AI_IT",
    }

    for method in OptimisationMethod:
        w = optimise_portfolio_weights(
            symbols=symbols,
            method=method.value,
            conviction_scores=scores,
            market_caps=mcaps,
            category_map=cats,
            max_single_stock_pct=12.0,
            max_subsector_pct=35.0,
        )
        assert len(w) == len(symbols)
        assert pytest.approx(sum(w.values()), abs=0.5) == 100.0
        for sym, weight_val in w.items():
            assert weight_val <= 12.15, f"{method.value} exceeded single-stock cap on {sym}: {weight_val}"


def test_transaction_cost_and_rebalancing_engine() -> None:
    cost_large = estimate_trade_cost_inr(100_000.0, side="BUY", avg_daily_turnover_inr_cr=100.0)
    cost_illiquid = estimate_trade_cost_inr(100_000.0, side="BUY", avg_daily_turnover_inr_cr=0.8)
    assert cost_large["total_cost_inr"] > 0
    # Illiquid micro-cap must incur higher slippage bps than liquid large-cap
    assert cost_illiquid["effective_cost_bps"] > cost_large["effective_cost_bps"]

    reb = compute_rebalance_trades(
        current_weights={"NETWEB": 50.0, "HITACHIEN": 50.0},
        target_weights={"NETWEB": 40.0, "HITACHIEN": 60.0},
        portfolio_value_inr=1_000_000.0,
        drift_threshold_pct=5.0,
    )
    assert reb["rebalance_triggered"] is True
    assert pytest.approx(reb["one_way_turnover_pct"]) == 10.0


def test_portfolio_stress_testing(tmp_path) -> None:
    repo = AI3Repository(db_path=tmp_path / "test_stress.db")
    repo.bootstrap_if_needed()
    sec_map = {s["symbol"]: s for s in repo.get_securities()}
    f_map = repo.get_latest_fundamentals_map()

    weights = {"NETWEB": 25.0, "HITACHIEN": 25.0, "CUMMINSIND": 25.0, "PERSISTENT": 25.0}
    scen = run_portfolio_stress_tests(weights, sec_map, f_map)
    assert len(scen) == 6
