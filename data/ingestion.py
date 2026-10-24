"""High-level data ingestion orchestrator connecting providers, validators, and the SQLite repository."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.logging_config import get_logger
from data.providers.exchange_provider import HybridExchangeProvider
from data.providers.fundamentals_provider import HybridFundamentalsProvider
from data.providers.ipo_provider import HybridIPOProvider
from data.providers.news_provider import HybridNewsProvider
from data.providers.price_provider import HybridPriceProvider
from data.validation import validate_ohlcv_dataframe
from database.models import NewsEventModel
from database.repository import AI3Repository

logger = get_logger(__name__)


class DataIngestionService:
    """Orchestrates point-in-time data ingestion, validation, and persistence."""

    def __init__(self, repo: AI3Repository | None = None) -> None:
        self.repo = repo or AI3Repository()
        self.exchange_provider = HybridExchangeProvider()
        self.price_provider = HybridPriceProvider()
        self.fundamentals_provider = HybridFundamentalsProvider()
        self.ipo_provider = HybridIPOProvider()
        self.news_provider = HybridNewsProvider()

    def ensure_bootstrapped(self) -> dict[str, int]:
        """Bootstrap seed database and ensure news/filings are populated."""
        counts = self.repo.bootstrap_if_needed()
        self._seed_curated_news_if_empty()
        return counts

    def _seed_curated_news_if_empty(self) -> int:
        existing = self.repo.get_news_items()
        if existing:
            return 0
        payload = self.news_provider.fetch_company_news(limit=100)
        sec_map = {s["symbol"]: s["company_name"] for s in self.repo.get_securities()}
        inserted = 0
        with self.repo.session() as session:
            for item in payload.data:
                pub_dt = datetime.strptime(item["published_date"], "%Y-%m-%d").date()
                session.add(
                    NewsEventModel(
                        symbol=item["symbol"],
                        company_name=sec_map.get(item["symbol"], item["symbol"]),
                        event_category=item.get("evidence_type", "CORPORATE_FILING"),
                        event_stage="SIGNED_CONTRACT" if item.get("is_verified_contract") else "ANNOUNCED_PLAN",
                        event_date=pub_dt,
                        disclosed_amount_cr_inr=None,
                        headline=item["headline"],
                        summary=item["summary"],
                        reflected_in_financials=bool(item.get("is_verified_contract", False)),
                        source_name=item["source_name"],
                        source_url=item["source_url"],
                    )
                )
                inserted += 1
        return inserted

    def get_or_generate_price_history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        force_live: bool = False,
    ) -> dict[str, Any]:
        """Fetch validated OHLCV price history for `symbol` with point-in-time listing date enforcement."""
        from analytics.equity_enrichment import get_live_equity_quote

        sec = self.repo.get_security_by_symbol(symbol)
        if not sec:
            return {"df": None, "warnings": [f"Unknown symbol {symbol}"], "source_name": "UNKNOWN"}

        fundamentals_map = self.repo.get_latest_fundamentals_map()
        f = fundamentals_map.get(symbol, {})
        live_q = get_live_equity_quote(symbol)

        listing_dt: date | None = None
        if sec.get("listing_date"):
            try:
                listing_dt = datetime.strptime(sec["listing_date"], "%Y-%m-%d").date()
            except ValueError:
                listing_dt = None

        # Derive reference price from live market snapshot or fundamentals snapshot
        mcap_cr = f.get("market_cap_inr_cr") or 5000.0
        if live_q and live_q.get("cmp") and float(live_q["cmp"]) > 0:
            ref_price = float(live_q["cmp"])
            yft_override = str(live_q.get("yf_ticker") or "")
        else:
            ref_price = max(25.0, min(45000.0, round((mcap_cr ** 0.52) * 8.5, 2)))
            yft_override = str(sec.get("yf_ticker") or "")

        rev_cagr_3y = f.get("rev_cagr_3y_pct")
        annual_drift = 16.0 if rev_cagr_3y is None else max(-20.0, min(42.0, rev_cagr_3y * 0.75))
        if not sec.get("is_investable", True):
            annual_drift = min(annual_drift, 4.0)

        payload = self.price_provider.fetch_price_history(
            symbol=sec["symbol"],
            exchange=sec["exchange"],
            start_date=start_date,
            end_date=end_date,
            listing_date=listing_dt,
            reference_price=ref_price,
            annual_return_hint_pct=annual_drift,
            volatility_hint_pct=26.0 if sec.get("universe_tier") != "HIGH_RISK_RESEARCH" else 42.0,
            avg_daily_turnover_cr=f.get("avg_daily_turnover_inr_cr") or 10.0,
            force_live=force_live,
            yf_ticker_override=yft_override or None,
        )
        df = payload.data
        validation = validate_ohlcv_dataframe(df, symbol=sec["symbol"])
        return {
            "df": df,
            "source_name": payload.source_name,
            "source_url": payload.source_url,
            "value_type": payload.value_type,
            "is_live": payload.is_live,
            "warnings": payload.warnings + validation.warnings + validation.errors,
        }
