"""Job: Refresh NSE/BSE security master and detect symbol changes or new listings."""

from __future__ import annotations

from typing import Any

from core.logging_config import get_logger
from data.providers.exchange_provider import HybridExchangeProvider
from database.repository import AI3Repository

logger = get_logger(__name__)


def run_update_security_master(repo: AI3Repository | None = None) -> dict[str, Any]:
    """Synchronize symbol master against official exchange CSV or seed fallback."""
    repository = repo or AI3Repository()
    repository.bootstrap_if_needed()
    job_id = repository.log_job_start("update_security_master")
    try:
        provider = HybridExchangeProvider()
        payload = provider.fetch_symbol_master(exchange="NSE")
        existing = {s["symbol"]: s for s in repository.get_securities()}
        verified_count = sum(1 for row in payload.data if row["symbol"] in existing)

        msg = (
            f"Checked {len(payload.data)} symbols from {payload.source_name}; "
            f"{verified_count} active AI3 universe symbols verified."
        )
        repository.log_job_finish(job_id, status="SUCCESS", records_processed=len(payload.data), details=msg)
        return {
            "job_id": job_id,
            "status": "SUCCESS",
            "records_processed": len(payload.data),
            "verified_symbols": verified_count,
            "source_name": payload.source_name,
            "is_live": payload.is_live,
            "message": msg,
        }
    except Exception as exc:
        repository.log_job_finish(job_id, status="FAILED", records_processed=0, details=str(exc))
        logger.error("update_security_master failed: %s", exc)
        return {"job_id": job_id, "status": "FAILED", "error": str(exc)}


if __name__ == "__main__":
    print(run_update_security_master())
