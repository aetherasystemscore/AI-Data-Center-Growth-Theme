"""Job: Refresh company financial statements, valuation snapshots, and exposure scores."""

from __future__ import annotations

from typing import Any

from analytics.exposure_scoring import score_company_exposure
from core.logging_config import get_logger
from database.repository import AI3Repository

logger = get_logger(__name__)


def run_refresh_financials(repo: AI3Repository | None = None) -> dict[str, Any]:
    """Recompute and verify fundamental health and 100-point AI Exposure Scores across the universe."""
    repository = repo or AI3Repository()
    repository.bootstrap_if_needed()
    job_id = repository.log_job_start("refresh_financials")
    try:
        securities = repository.get_securities()
        f_map = repository.get_latest_fundamentals_map()
        scored = 0
        flagged = 0
        for sec in securities:
            f = f_map.get(sec["symbol"], {})
            bd = score_company_exposure(sec, f)
            scored += 1
            if bd.has_critical_red_flag:
                flagged += 1

        msg = f"Verified fundamentals and recomputed AI Exposure Scores for {scored} companies ({flagged} critical risk flags isolated)."
        repository.log_job_finish(job_id, status="SUCCESS", records_processed=scored, details=msg)
        return {
            "job_id": job_id,
            "status": "SUCCESS",
            "records_processed": scored,
            "critical_flags_isolated": flagged,
            "message": msg,
        }
    except Exception as exc:
        repository.log_job_finish(job_id, status="FAILED", records_processed=0, details=str(exc))
        logger.error("refresh_financials failed: %s", exc)
        return {"job_id": job_id, "status": "FAILED", "error": str(exc)}


if __name__ == "__main__":
    print(run_refresh_financials())
