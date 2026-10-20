"""Automated Daily 3:00 PM IST Working-Day Paper-Trading Job."""

from __future__ import annotations

from typing import Any

from data.ingestion import DataIngestionService
from database.repository import AI3Repository
from portfolio.paper_trading import ensure_paper_trading_ledger, get_ist_now, is_working_day


def run_paper_trade_3pm_job(repo: AI3Repository | None = None, force: bool = False) -> dict[str, Any]:
    """Execute the daily 3:00 PM IST working-day paper-trading mark-to-market and rebalance check."""
    repository = repo or AI3Repository()
    ingestion = DataIngestionService(repo=repository)
    ingestion.ensure_bootstrapped()

    job_id = repository.log_job_start("run_paper_trade_3pm_ist")
    now_ist = get_ist_now()

    if not is_working_day(now_ist.date()) and not force:
        msg = f"Skipped 3:00 PM IST paper trade: {now_ist.date().isoformat()} is a weekend/non-working day."
        repository.log_job_finish(job_id, status="SKIPPED_WEEKEND", records_processed=0, details=msg)
        return {"job_id": job_id, "status": "SKIPPED_WEEKEND", "message": msg}

    ledger = ensure_paper_trading_ledger(repo=repository, ingestion=ingestion, force_run_today=force)
    positions_count = len(ledger.get("positions", []))
    net_nav = ledger.get("current_net_nav_inr", 1_000_000.0)
    msg = (
        f"Executed 3:00 PM IST paper-trading cycle ({ledger.get('last_executed_timestamp_ist')}): "
        f"{positions_count} open positions | Net NAV Rs {net_nav:,.2f}."
    )
    repository.log_job_finish(job_id, status="SUCCESS", records_processed=positions_count, details=msg)
    return {
        "job_id": job_id,
        "status": "SUCCESS",
        "positions_count": positions_count,
        "current_net_nav_inr": net_nav,
        "message": msg,
    }


if __name__ == "__main__":
    result = run_paper_trade_3pm_job(force=True)
    print(result["message"])
