"""Job: Ingest and classify corporate announcements and filing evidence items."""

from __future__ import annotations

from datetime import date
from typing import Any

from core.logging_config import get_logger
from data.ingestion import DataIngestionService
from data.providers.exchange_provider import fetch_google_news_rss
from database.repository import AI3Repository

logger = get_logger(__name__)

_LIVE_NEWS_QUERIES: list[tuple[str, str, str]] = [
    ("NETWEB", "Netweb Technologies", "Netweb Technologies AI server order NSE"),
    ("CUMMINSIND", "Cummins India", "Cummins India data center power genset"),
    ("HITACHIEN", "Hitachi Energy India", "Hitachi Energy India HVDC substation order"),
    ("CGPOWER", "CG Power and Industrial Solutions", "CG Power transformer semiconductor OSAT"),
    ("ANANTRAJ", "Anant Raj Limited", "Anant Raj data center cloud MW"),
]


def run_research_news(repo: AI3Repository | None = None, fetch_live_rss: bool = True) -> dict[str, Any]:
    """Refresh corporate filing evidence, optionally pull live Google News RSS items, and verify fact-vs-narrative tags."""
    repository = repo or AI3Repository()
    ingestion = DataIngestionService(repo=repository)
    ingestion.ensure_bootstrapped()
    job_id = repository.log_job_start("research_news")
    try:
        live_added = 0
        if fetch_live_rss:
            for sym, cname, q in _LIVE_NEWS_QUERIES:
                try:
                    rss_items = fetch_google_news_rss(q, max_items=2)
                    for item in rss_items:
                        title = (item.get("title") or "").strip()
                        link = (item.get("link") or "").strip()
                        if title and repository.upsert_news_event(
                            symbol=sym,
                            company_name=cname,
                            headline=title[:240],
                            summary=f"Live RSS corporate news feed item ({item.get('published', 'Recent')}). Verify against formal NSE/BSE exchange filing before sizing.",
                            event_date=date.today(),
                            event_category="LIVE_NEWS_RSS",
                            event_stage="PRESS_RELEASE_OR_MEDIA",
                            reflected_in_financials=False,
                            source_name="GOOGLE_NEWS_RSS_LIVE",
                            source_url=link,
                        ):
                            live_added += 1
                except Exception:
                    continue

        items = repository.get_news_items()
        verified_count = sum(1 for i in items if i.get("is_verified_contract"))
        msg = (
            f"Processed {len(items)} corporate filing/news evidence items "
            f"({verified_count} confirmed contract/segment disclosures, {live_added} new live RSS items)."
        )
        repository.log_job_finish(job_id, status="SUCCESS", records_processed=len(items), details=msg)
        return {
            "job_id": job_id,
            "status": "SUCCESS",
            "records_processed": len(items),
            "verified_contracts": verified_count,
            "live_rss_added": live_added,
            "message": msg,
        }
    except Exception as exc:
        repository.log_job_finish(job_id, status="FAILED", records_processed=0, details=str(exc))
        logger.error("research_news failed: %s", exc)
        return {"job_id": job_id, "status": "FAILED", "error": str(exc)}


if __name__ == "__main__":
    print(run_research_news())
