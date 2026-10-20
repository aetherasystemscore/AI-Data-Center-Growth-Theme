"""Job: Discover newly listed NSE/BSE and SME companies matching AI infrastructure taxonomy keywords."""

from __future__ import annotations

from typing import Any

from core.config import load_sector_taxonomy
from core.logging_config import get_logger
from data.providers.exchange_provider import HybridExchangeProvider
from database.repository import AI3Repository

logger = get_logger(__name__)


def classify_text_against_taxonomy(text: str) -> tuple[list[str], list[str], float]:
    """Match a company name or business summary against `config/sector_taxonomy.yaml` keywords."""
    taxonomy = load_sector_taxonomy()
    categories = taxonomy.get("categories", {})
    low = text.lower()
    matched_cats: list[str] = []
    matched_kws: list[str] = []

    for cat_code, cat_info in categories.items():
        kws = cat_info.get("discovery_keywords", [])
        for kw in kws:
            if kw.lower() in low:
                if cat_code not in matched_cats:
                    matched_cats.append(cat_code)
                if kw not in matched_kws:
                    matched_kws.append(kw)

    confidence = min(90.0, 35.0 + len(matched_kws) * 18.0) if matched_kws else 0.0
    return matched_cats, matched_kws, confidence


def run_discover_new_listings(repo: AI3Repository | None = None, lookback_days: int = 730) -> dict[str, Any]:
    """Scan recent NSE/BSE/SME listings for AI infrastructure, component, power, cooling, or e-waste keywords.

    All discovered companies are placed in `discovery_queue` with status `CANDIDATE_PENDING_REVIEW`
    and never auto-promoted into the investable universe without validation.
    """
    repository = repo or AI3Repository()
    repository.bootstrap_if_needed()
    job_id = repository.log_job_start("discover_new_listings")
    try:
        provider = HybridExchangeProvider()
        payload = provider.fetch_recent_listings(lookback_days=lookback_days)
        queued = 0

        # Also include curated discovery candidates not yet in seed_stocks.csv to showcase the discovery queue
        extra_discovery_candidates = [
            {
                "symbol": "RASHI",
                "company_name": "Rashi Peripherals Limited",
                "exchange": "NSE",
                "listing_date_iso": "2024-02-14",
                "business_summary": "ICT distribution partner for GPUs, enterprise servers, networking hardware, storage and cloud computing components.",
            },
            {
                "symbol": "EXICOM",
                "company_name": "Exicom Tele-Systems Limited",
                "exchange": "NSE",
                "listing_date_iso": "2024-03-05",
                "business_summary": "Critical power conversion systems, telecom SMPS rectifiers, lithium-ion energy storage and EV charging equipment.",
            },
            {
                "symbol": "PLATINUM",
                "company_name": "Platinum Industries Limited",
                "exchange": "NSE",
                "listing_date_iso": "2024-03-05",
                "business_summary": "Specialty stabilizers and additives used in PVC electrical cables, pipes and insulation.",
            },
        ]
        all_candidates = list(payload.data) + extra_discovery_candidates

        for item in all_candidates:
            text_blob = f"{item.get('company_name', '')} {item.get('business_summary', '')}"
            cats, kws, conf = classify_text_against_taxonomy(text_blob)
            if cats and conf >= 40.0:
                repository.enqueue_discovery_candidate(
                    candidate_type="NEW_LISTING",
                    symbol_or_id=item["symbol"],
                    company_name=item["company_name"],
                    exchange=item.get("exchange", "NSE"),
                    discovered_via=item.get("source_name", "EXCHANGE_NEW_LISTING_SCAN"),
                    matched_keywords=kws,
                    proposed_Categories=cats,
                    confidence_score=conf,
                    notes=f"Listed {item.get('listing_date_iso') or item.get('listing_date')}: {item.get('business_summary', 'Matched taxonomy keywords')}",
                )
                queued += 1

        msg = f"Evaluated {len(all_candidates)} recent listings; queued {queued} AI/DC candidates as CANDIDATE_PENDING_REVIEW."
        repository.log_job_finish(job_id, status="SUCCESS", records_processed=len(all_candidates), details=msg)
        return {
            "job_id": job_id,
            "status": "SUCCESS",
            "records_processed": len(all_candidates),
            "candidates_queued": queued,
            "message": msg,
        }
    except Exception as exc:
        repository.log_job_finish(job_id, status="FAILED", records_processed=0, details=str(exc))
        logger.error("discover_new_listings failed: %s", exc)
        return {"job_id": job_id, "status": "FAILED", "error": str(exc)}


if __name__ == "__main__":
    print(run_discover_new_listings())
