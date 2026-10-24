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
from jobs.run_paper_trade_3pm import run_paper_trade_3pm_job
from jobs.update_security_master import run_update_security_master
from analytics.equity_enrichment import (
    compute_enriched_equity_metrics,
    get_2y_quarterly_shareholding_and_price,
    get_live_equity_quote,
    get_live_etf_quote,
    load_live_market_snapshot,
)
from portfolio.paper_trading import (
    build_forward_horizon_kpi_table,
    deploy_custom_basket_to_paper_trading,
    ensure_paper_trading_ledger,
    execute_manual_paper_trade,
    get_best_5y_scoring_profile,
    rank_scoring_profiles_5y,
    refresh_paper_ledger_mtm,
    run_5y_historical_verifiable_backtest,
)


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


def test_equity_enrichment_and_3pm_paper_trading_and_5y_backtest(tmp_path) -> None:
    repo = AI3Repository(db_path=tmp_path / "test_pt.db")
    ingestion = DataIngestionService(repo=repo)
    ingestion.ensure_bootstrapped()

    dixon = repo.get_security_by_symbol("DIXON")
    f_map = repo.get_latest_fundamentals_map()
    enr = compute_enriched_equity_metrics(dixon, f_map.get("DIXON", {}))
    assert enr["cmp"] > 0
    assert 0 <= enr["fundamental_score"] <= 100
    assert 0 <= enr["technical_score"] <= 100
    assert 0 <= enr["analyst_score"] <= 100
    assert "2Y" in enr["price_trend_summary"]
    assert "2Y" in enr["promoter_trend"]

    q_rows = get_2y_quarterly_shareholding_and_price(dixon, f_map.get("DIXON", {}))
    assert len(q_rows) == 8

    pt_res = run_paper_trade_3pm_job(repo=repo, force=True)
    assert pt_res["status"] == "SUCCESS"
    assert pt_res["positions_count"] >= 5

    ledger = ensure_paper_trading_ledger(repo=repo, ingestion=ingestion)
    bt_5y = run_5y_historical_verifiable_backtest(repo=repo, ingestion=ingestion)
    assert len(bt_5y["interval_table"]) == 8  # 1W, 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y
    fwd_rows = build_forward_horizon_kpi_table(ledger, bt_5y["interval_table"])
    assert len(fwd_rows) == 8

    ranked_profiles = rank_scoring_profiles_5y(repo=repo, ingestion=ingestion)
    assert len(ranked_profiles["leaderboard"]) == 9
    best_prof, best_metrics, lb = get_best_5y_scoring_profile(repo=repo, ingestion=ingestion)
    assert best_prof == "HIGH_GROWTH_INFRA"
    assert best_metrics["cagr_pct"] > 20.0
    assert len(lb) == 9
    assert bt_5y["best_5y_profile"] == "HIGH_GROWTH_INFRA"
    assert ledger["scoring_profile"] == "HIGH_GROWTH_INFRA"


def test_live_snapshot_manual_paper_trades_and_all_views(tmp_path) -> None:
    snap = load_live_market_snapshot()
    assert len(snap.get("equities", {})) >= 90
    assert len(snap.get("etfs", {})) >= 8
    assert get_live_equity_quote("NETWEB") is not None
    assert get_live_etf_quote("INFRABEES") is not None

    repo = AI3Repository(db_path=tmp_path / "test_manual_pt.db")
    ingestion = DataIngestionService(repo=repo)
    ingestion.ensure_bootstrapped()

    # Save custom basket and deploy to paper trading
    saved_id = repo.save_custom_portfolio_basket(
        basket_name="AI Infra Test Basket",
        weights_map={"NETWEB": 50.0, "CUMMINSIND": 50.0},
        capital_inr=1_000_000.0,
        scoring_profile="HIGH_GROWTH_INFRA",
        optimisation_method="EQUAL_WEIGHT",
    )
    assert saved_id >= 1
    baskets = repo.get_saved_portfolio_baskets()
    assert any(b["basket_name"] == "AI Infra Test Basket" for b in baskets)

    dep_ledger = deploy_custom_basket_to_paper_trading(
        repo=repo,
        ingestion=ingestion,
        weights_map={"NETWEB": 40.0, "CUMMINSIND": 40.0},
        initial_capital_inr=1_000_000.0,
        scoring_profile="HIGH_GROWTH_INFRA",
    )
    assert len(dep_ledger["positions"]) == 2

    # Execute manual BUY and SELL paper trades
    buy_ledger = execute_manual_paper_trade(
        repo=repo,
        ingestion=ingestion,
        symbol="POLYCAB",
        side="BUY",
        quantity=2,
        rationale="Test manual buy",
    )
    assert any(p["Symbol"] == "POLYCAB" for p in buy_ledger["positions"])

    sell_ledger = execute_manual_paper_trade(
        repo=repo,
        ingestion=ingestion,
        symbol="POLYCAB",
        side="SELL",
        quantity=1,
        rationale="Test manual partial sell",
    )
    poly_pos = next(p for p in sell_ledger["positions"] if p["Symbol"] == "POLYCAB")
    assert poly_pos["Qty (Shares)"] == 1

    mtm_ledger = refresh_paper_ledger_mtm(repo=repo, ingestion=ingestion, fetch_live_yf=False)
    assert mtm_ledger["current_net_nav_inr"] > 0

    # Restore clean default HIGH_GROWTH_INFRA 3:00 PM IST paper ledger
    restored = ensure_paper_trading_ledger(repo=repo, ingestion=ingestion, force_run_today=True)
    assert restored["scoring_profile"] == "HIGH_GROWTH_INFRA"

    # Ensure all 12 views import cleanly and expose render()
    import importlib

    view_modules = [
        "views.dashboard",
        "views.stock_screener",
        "views.company_research",
        "views.value_alternatives",
        "views.etf_analysis",
        "views.smallcase_analysis",
        "views.ipo_tracker",
        "views.circular_electronics",
        "views.portfolio_builder",
        "views.backtesting",
        "views.settings",
        "views.paper_trading",
    ]
    for mod_name in view_modules:
        mod = importlib.import_module(mod_name)
        assert hasattr(mod, "render")

