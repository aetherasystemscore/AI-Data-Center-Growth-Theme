"""Abstract base interfaces for all pluggable data providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
import pandas as pd


@dataclass
class ProviderPayload:
    """Standardised wrapper returned by all data provider adapters with provenance metadata."""

    data: Any
    source_name: str
    source_url: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    value_type: str = "REPORTED"
    is_live: bool = False
    warnings: List[str] = field(default_factory=list)


class BaseDataProvider(ABC):
    """Base adapter interface with source provenance metadata."""

    provider_name: str = "BASE_PROVIDER"
    priority_rank: int = 99

    def is_available(self) -> bool:
        """Return True if the provider can be queried in the current environment."""
        return True


class BaseExchangeProvider(BaseDataProvider):
    @abstractmethod
    def fetch_symbol_master(self, exchange: str = "NSE") -> ProviderPayload:
        """Return exchange symbol directory."""

    @abstractmethod
    def fetch_recent_listings(self, lookback_days: int = 365) -> ProviderPayload:
        """Return newly listed securities within lookback_days."""


class BasePriceProvider(BaseDataProvider):
    @abstractmethod
    def fetch_price_history(
        self,
        symbol: str,
        exchange: str,
        start_date: date,
        end_date: date,
        listing_date: Optional[date] = None,
    ) -> ProviderPayload:
        """Return OHLCV ProviderPayload."""


class BaseFundamentalsProvider(BaseDataProvider):
    @abstractmethod
    def fetch_fundamentals(self, symbol: str, exchange: str = "NSE") -> ProviderPayload:
        """Return dictionary of fundamental metrics, preserving None for unavailable fields."""

    @abstractmethod
    def fetch_all_fundamentals(self) -> ProviderPayload:
        """Return all fundamental snapshots."""


class BaseIPOProvider(BaseDataProvider):
    @abstractmethod
    def fetch_ipo_pipeline(self) -> ProviderPayload:
        """Return IPO pipeline records."""


class BaseNewsProvider(BaseDataProvider):
    @abstractmethod
    def fetch_company_news(self, symbol: Optional[str] = None, limit: int = 25) -> ProviderPayload:
        """Return company news and filing announcements."""

