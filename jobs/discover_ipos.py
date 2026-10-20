"""Job: Scan SEBI DRHP/RHP filings and IPO feeds for AI infrastructure & component candidates."""

from __future__ import annotations

from typing import Any

from core.logging_config import get_logger
from data.providers.ipo_provider import HybridIPOProvider
from database.repository import AI3Repository

logger = get_logger(__name__)


def run_discover_ipos(repo: AI3Repository | None = None) -> dict[str, Any]:
    """Scan SEBI filings and queue any newly discovered DRHP/RHP candidates for review."""
    repository = repo or AI3Repository()
    repository.bootstrap_if_needed()
    job_id = repository.log_job_start("discover_ipos")
    try:
        provider = HybridIPOProvider()
        payload = provider.fetch_ipo_pipeline()
        existing_ids = {i["ipo_id"] for i in repository.get_ipos()}
        queued = 0
        for item in payload.data:
            if item["ipo_id"] not in existing_ids:
                repository.enqueue_discovery_candidate(
                    candidate_type="IPO_FILING",
                    symbol_or_id=item["ipo_id"],
                    company_name=item["company_name"],
                    exchange=item.get("exchange", "NSE/BSE"),
                    discovered_via=item.get("source_name", "SEBI_RSS_FEED"),
                    matched_keywords=["drhp", "ai_infra_keyword_scan"],
                    proposed_Categories=item.get("sector_tags", ["B_ELECTRONIC_COMPONENTS"]),
                    confidence_score=float(item.get("ai_infrastructure_relevance_score", 50.0)),
                    notes=item.get("value_chain_role", "Discovered via IPO pipeline scan"),
                )
                queued += 1

        msg = f"Scanned {len(payload.data)} IPO filings; queued {queued} new candidates as CANDIDATE_PENDING_REVIEW."
        repository.log_job_finish(job_id, status="SUCCESS", records_processed=len(payload.data), details=msg)
        return {
            "job_id": job_id,
            "status": "SUCCESS",
            "records_processed": len(payload.data),
            "new_candidates_queued": queued,
            "message": msg,
        }
    except Exception as exc:
        repository.log_job_finish(job_id, status="FAILED", records_processed=0, details=str(exc))
        logger.error("discover_ipos failed: %s", exc)
        return {"job_id": job_id, "status": "FAILED", "error": str(exc)}


if __name__ == "__main__":
    print(run_discover_ipos())
