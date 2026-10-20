"""Company fundamentals, governance, and sector KPI provider."""

from __future__ import annotations

import csv
from typing import Any

from core.config import get_settings
from core.logging_config import get_logger
from data.providers.base import BaseFundamentalsProvider, ProviderPayload
from data.validation import parse_optional_float

logger = get_logger(__name__)


class HybridFundamentalsProvider(BaseFundamentalsProvider):
    """Provides company fundamental statements, valuation snapshots, and sector KPIs."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._cache: dict[str, dict[str, Any]] | None = None

    def _load_seed_table(self) -> dict[str, dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        path = self.settings.config_dir / "sample_fundamentals_synthetic.csv"
        table: dict[str, dict[str, Any]] = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    sym = row["symbol"].strip()
                    parsed: dict[str, Any] = {"symbol": sym}
                    for k, v in row.items():
                        if k in (
                            "symbol",
                            "fiscal_period",
                            "reporting_date",
                            "order_book_execution_horizon",
                            "governance_notes",
                            "evidence_citation",
                            "evidence_type",
                            "sector_kpi_name",
                            "sector_kpi_unit",
                            "source_name",
                            "value_type",
                            "source_url",
                        ):
                            parsed[k] = v.strip() if v else None
                        elif k == "auditor_qualification_flag":
                            parsed[k] = str(v).strip().lower() == "true"
                        else:
                            parsed[k] = parse_optional_float(v)
                    table[sym] = parsed
        self._cache = table
        return table

    def fetch_fundamentals(self, symbol: str, exchange: str = "NSE") -> ProviderPayload:
        """Fetch fundamentals for a single symbol, preserving None for missing metrics."""
        table = self._load_seed_table()
        record = table.get(symbol)
        if record is None:
            return ProviderPayload(
                data={},
                source_name="MISSING",
                value_type="MISSING",
                is_live=False,
                warnings=[f"No fundamental snapshot available for {symbol}"],
            )
        return ProviderPayload(
            data=dict(record),
            source_name=record.get("source_name") or "SEED_FUNDAMENTALS_FY25",
            source_url=record.get("source_url") or "config/sample_fundamentals_synthetic.csv",
            value_type=record.get("value_type") or "SEED_REFERENCE_SNAPSHOT",
            is_live=False,
        )

    def fetch_all_fundamentals(self) -> ProviderPayload:
        """Fetch all fundamental records in the seed/cached universe."""
        table = self._load_seed_table()
        return ProviderPayload(
            data=list(table.values()),
            source_name="SEED_FUNDAMENTALS_FY25",
            source_url="config/sample_fundamentals_synthetic.csv",
            value_type="SEED_REFERENCE_SNAPSHOT",
            is_live=False,
        )
