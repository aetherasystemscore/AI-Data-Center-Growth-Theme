"""Job: Refresh market price and turnover series for the active stock & ETF universe."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from core.logging_config import get_logger
from data.ingestion import DataIngestionService
from database.repository import AI3Repository

logger = get_logger(__name__)


def run_refresh_prices(
    repo: AI3Repository | None = None,
    sample_limit: int = 15,
    sync_live_snapshot: bool | None = None,
) -> dict[str, Any]:
    """Validate and refresh OHLCV series and live market snapshot for active securities."""
    repository = repo or AI3Repository()
    ingestion = DataIngestionService(repo=repository)
    ingestion.ensure_bootstrapped()
    job_id = repository.log_job_start("refresh_prices")
    try:
        do_live_sync = sync_live_snapshot if sync_live_snapshot is not None else (sample_limit >= 10)
        live_equities_count = 0
        if do_live_sync:
            from analytics.equity_enrichment import refresh_live_market_snapshot

            snap = refresh_live_market_snapshot(update_csv=False)
            live_equities_count = len(snap.get("equities", {}))

        securities = repository.get_securities(geography="INDIA")[:sample_limit]
        end_dt = date.today()
        start_dt = end_dt - timedelta(days=365)
        processed = 0
        for sec in securities:
            res = ingestion.get_or_generate_price_history(
                symbol=sec["symbol"],
                start_date=start_dt,
                end_date=end_dt,
            )
            if res.get("df") is not None and not res["df"].empty:
                processed += 1

        msg = (
            f"Refreshed and validated 1Y price/turnover history for {processed}/{len(securities)} Indian securities"
            + (f" and synced {live_equities_count} live Yahoo Finance quotes." if live_equities_count else ".")
        )
        repository.log_job_finish(job_id, status="SUCCESS", records_processed=max(processed, live_equities_count), details=msg)
        return {
            "job_id": job_id,
            "status": "SUCCESS",
            "records_processed": max(processed, live_equities_count),
            "live_equities_synced": live_equities_count,
            "message": msg,
        }
    except Exception as exc:
        repository.log_job_finish(job_id, status="FAILED", records_processed=0, details=str(exc))
        logger.error("refresh_prices failed: %s", exc)
        return {"job_id": job_id, "status": "FAILED", "error": str(exc)}


if __name__ == "__main__":
    print(run_refresh_prices())
