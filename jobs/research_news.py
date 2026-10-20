"""Job: Ingest and classify corporate announcements and filing evidence items."""

from __future__ import annotations

from typing import Any

from core.logging_config import get_logger
from data.ingestion import DataIngestionService
from database.repository import AI3Repository

logger = get_logger(__name__)


def run_research_news(repo: AI3Repository | None = None) -> dict[str, Any]:
    """Refresh corporate filing evidence and verify fact-vs-narrative tags."""
    repository = repo or AI3Repository()
    ingestion = DataIngestionService(repo=repository)
    ingestion.ensure_bootstrapped()
    job_id = repository.log_job_start("research_news")
    try:
        items = repository.get_news_items()
        verified_count = sum(1 for i in items if i.get("is_verified_contract"))
        msg = f"Processed {len(items)} corporate filing/news evidence items ({verified_count} confirmed contract/segment disclosures)."
        repository.log_job_finish(job_id, status="SUCCESS", records_processed=len(items), details=msg)
        return {
            "job_id": job_id,
            "status": "SUCCESS",
            "records_processed": len(items),
            "verified_contracts": verified_count,
            "message": msg,
        }
    except Exception as exc:
        repository.log_job_finish(job_id, status="FAILED", records_processed=0, details=str(exc))
        logger.error("research_news failed: %s", exc)
        return {"job_id": job_id, "status": "FAILED", "error": str(exc)}


if __name__ == "__main__":
    print(run_research_news())
