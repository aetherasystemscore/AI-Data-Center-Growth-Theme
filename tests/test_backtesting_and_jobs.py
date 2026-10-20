"""Tests for point-in-time backtesting, listing-date guard, walk-forward validation, and background jobs."""

from __future__ import annotations

from datetime import date

from backtesting.engine import BacktestConfig, PointInTimeBacktestEngine
from backtesting.walk_forward import run_walk_forward_validation
from data.ingestion import DataIngestionService
from database.repository import AI3Repository
from jobs.discover_ipos import run_discover_ipos
from jobs.discover_new_listings import run_discover_new_listings
from jobs.refresh_financials import run_refresh_financials
from jobs.refresh_prices import run_refresh_prices
from jobs.research_news import run_research_news
from jobs.update_security_master import run_update_security_master


def test_point_in_time_backtest_listing_date_guard_and_tx_costs(tmp_path) -> None:
    repo = AI3Repository(db_path=tmp_path / "test_bt.db")
    ingestion = DataIngestionService(repo=repo)
    ingestion.ensure_bootstrapped()

    engine = PointInTimeBacktestEngine(ingestion=ingestion)

    # NETWEB was listed on 2023-07-27; in a backtest starting 2022-01-03 it must NOT be held in 2022
    sec_netweb = repo.get_security_by_symbol("NETWEB")
    assert engine.is_security_eligible_at_date(sec_netweb, date(2022, 6, 1)) is False
    assert engine.is_security_eligible_at_date(sec_netweb, date(2024, 1, 1)) is True

    cfg = BacktestConfig(
        start_date=date(2022, 1, 3),
        end_date=date(2025, 12, 31),
        initial_capital_inr=1_000_000.0,
        rebalance_frequency="QUARTERLY",
        optimisation_method="EQUAL_WEIGHT",
    )
    res = engine.run_backtest(
        symbols=["POWERGRID", "HITACHIEN", "CUMMINSIND", "NETWEB", "BLUESTARCO"],
        config=cfg,
    )
    # First rebalance in Jan 2022 must only have 4 active symbols (NETWEB excluded prior to July 2023)
    first_reb = res["rebalance_log"][0]
    assert first_reb["active_symbols_count"] == 4
    assert "NETWEB" not in first_reb["top_holdings"]

    # Net return must be strictly less than or equal to Gross return due to Indian transaction costs
    assert res["metrics"]["cagr_pct"] <= res["metrics"]["gross_cagr_pct"]


def test_walk_forward_validation(tmp_path) -> None:
    repo = AI3Repository(db_path=tmp_path / "test_wf.db")
    ingestion = DataIngestionService(repo=repo)
    ingestion.ensure_bootstrapped()
    engine = PointInTimeBacktestEngine(ingestion=ingestion)

    folds = run_walk_forward_validation(
        symbols=["POWERGRID", "HITACHIEN", "CUMMINSIND", "POLYCAB", "BLUESTARCO"],
        start_date=date(2022, 1, 3),
        end_date=date(2025, 6, 30),
        in_sample_months=12,
        out_of_sample_months=6,
        engine=engine,
    )
    assert len(folds) >= 2
    assert "out_of_sample_cagr_pct" in folds[0]


def test_all_six_background_jobs_execute_and_log(tmp_path) -> None:
    repo = AI3Repository(db_path=tmp_path / "test_jobs.db")
    r1 = run_update_security_master(repo)
    assert r1["status"] == "SUCCESS"

    r2 = run_discover_new_listings(repo)
    assert r2["status"] == "SUCCESS"
    assert r2["candidates_queued"] >= 1

    # Verify discovered candidates are placed in CANDIDATE_PENDING_REVIEW, never auto-activated
    q = repo.get_discovery_queue()
    assert len(q) >= 1
    assert all(item["status"] == "CANDIDATE_PENDING_REVIEW" for item in q)

    r3 = run_discover_ipos(repo)
    assert r3["status"] == "SUCCESS"

    r4 = run_refresh_prices(repo, sample_limit=4)
    assert r4["status"] == "SUCCESS"

    r5 = run_refresh_financials(repo)
    assert r5["status"] == "SUCCESS"

    r6 = run_research_news(repo)
    assert r6["status"] == "SUCCESS"

    runs = repo.get_recent_job_runs(limit=10)
    assert len(runs) == 6
