"""Job: Refresh market price and turnover series for the active stock & ETF universe."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from core.logging_config import get_logger
from data.ingestion import DataIngestionService
from database.repository import AI3Repository

logger = get_logger(__name__)


def run_refresh_prices(repo: AI3Repository | None = None, sample_limit: int = 15) -> dict[str, Any]:
    """Validate and refresh OHLCV series for active securities."""
    repository = repo or AI3Repository()
    ingestion = DataIngestionService(repo=repository)
    ingestion.ensure_bootstrapped()
    job_id = repository.log_job_start("refresh_prices")
    try:
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

        msg = f"Refreshed and validated 1Y price/turnover history for {processed}/{len(securities)} Indian securities."
        repository.log_job_finish(job_id, status="SUCCESS", records_processed=processed, details=msg)
        return {"job_id": job_id, "status": "SUCCESS", "records_processed": processed, "message": msg}
    except Exception as exc:
        repository.log_job_finish(job_id, status="FAILED", records_processed=0, details=str(exc))
        logger.error("refresh_prices failed: %s", exc)
        return {"job_id": job_id, "status": "FAILED", "error": str(exc)}


if __name__ == "__main__":
    print(run_refresh_prices())
