"""Exchange symbol list, newly listed equities, and security master provider."""

from __future__ import annotations

import csv
import io
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Any

import requests

from core.config import get_settings
from core.logging_config import get_logger
from data.providers.base import BaseExchangeProvider, ProviderPayload

logger = get_logger(__name__)


def fetch_google_news_rss(query: str, max_items: int = 3) -> list[dict[str, str]]:
    """Fetch live RSS news headlines from Google News India for a company or corporate filing query."""
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
    items: list[dict[str, str]] = []
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=5,
        )
        if resp.status_code == 200 and "<rss" in resp.text[:400].lower():
            root = ET.fromstring(resp.text)
            for node in root.findall(".//item")[:max_items]:
                title = (node.findtext("title") or "").strip()
                link = (node.findtext("link") or "").strip()
                pub = (node.findtext("pubDate") or "").strip()
                if title:
                    items.append({"title": title, "link": link, "published": pub})
    except Exception as exc:
        logger.debug("Google News RSS fetch skipped for %s: %s", query, exc)
    return items


class HybridExchangeProvider(BaseExchangeProvider):
    """Provides exchange symbol lists and newly listed equities using NSE official CSV or seed fallback."""

    NSE_EQUITY_CSV_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    NSE_SME_CSV_URL = "https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/csv,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    def fetch_symbol_master(self, exchange: str = "NSE") -> ProviderPayload:
        """Fetch official NSE/BSE equity symbol directory or fallback to seed stocks."""
        if self.settings.data_mode in ("HYBRID", "LIVE") and exchange.upper() in ("NSE", "NSE_SME"):
            url = self.NSE_SME_CSV_URL if exchange.upper() == "NSE_SME" else self.NSE_EQUITY_CSV_URL
            try:
                resp = requests.get(url, headers=self._headers, timeout=8)
                if resp.status_code == 200 and "SYMBOL" in resp.text[:200].upper():
                    reader = csv.DictReader(io.StringIO(resp.text))
                    rows: list[dict[str, Any]] = []
                    for r in reader:
                        clean = {k.strip(): (v.strip() if v else "") for k, v in r.items() if k}
                        symbol = clean.get("SYMBOL", "")
                        if symbol:
                            rows.append(
                                {
                                    "symbol": symbol,
                                    "company_name": clean.get("NAME OF COMPANY", symbol),
                                    "series": clean.get("SERIES", "EQ"),
                                    "listing_date": clean.get("DATE OF LISTING", None),
                                    "isin": clean.get("ISIN NUMBER", None),
                                    "exchange": exchange.upper(),
                                    "source_name": "NSE_ARCHIVES_EQUITY_L",
                                    "value_type": "ACTUAL_OFFICIAL_EXCHANGE",
                                }
                            )
                    if rows:
                        return ProviderPayload(
                            data=rows,
                            source_name="NSE_ARCHIVES_EQUITY_L",
                            source_url=url,
                            value_type="ACTUAL_OFFICIAL_EXCHANGE",
                            is_live=True,
                        )
            except Exception as exc:
                logger.warning("Live NSE symbol master fetch failed (%s); falling back to local seed.", exc)

        # Fallback to seed_stocks.csv
        seed_path = self.settings.config_dir / "seed_stocks.csv"
        rows = []
        if seed_path.exists():
            with open(seed_path, "r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for r in reader:
                    if exchange == "ALL" or r.get("exchange", "").upper() == exchange.upper():
                        rows.append(
                            {
                                "symbol": r["symbol"].strip(),
                                "company_name": r["company_name"].strip(),
                                "series": "EQ",
                                "listing_date": r.get("listing_date") or None,
                                "isin": r.get("isin") or None,
                                "exchange": r["exchange"].strip(),
                                "source_name": "SEED_STOCKS_CSV",
                                "value_type": "SEED_REFERENCE_SNAPSHOT",
                            }
                        )
        return ProviderPayload(
            data=rows,
            source_name="SEED_STOCKS_CSV",
            source_url="config/seed_stocks.csv",
            value_type="SEED_REFERENCE_SNAPSHOT",
            is_live=False,
        )

    def fetch_recent_listings(self, lookback_days: int = 365) -> ProviderPayload:
        """Return companies listed within `lookback_days` plus candidate newly listed AI/DC names."""
        cutoff = date.today().toordinal() - lookback_days
        payload = self.fetch_symbol_master(exchange="ALL")
        recent: list[dict[str, Any]] = []
        for item in payload.data:
            ld_str = item.get("listing_date")
            if ld_str:
                parsed_dt: date | None = None
                for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
                    try:
                        parsed_dt = datetime.strptime(ld_str, fmt).date()
                        break
                    except ValueError:
                        continue
                if parsed_dt and parsed_dt.toordinal() >= cutoff:
                    item_copy = dict(item)
                    item_copy["listing_date_iso"] = parsed_dt.isoformat()
                    recent.append(item_copy)

        # Also add curated newly-listed discovery candidates if not already in list
        curated_recent = [
            {
                "symbol": "NAMOEWASTE",
                "company_name": "Namo eWaste Management Limited",
                "exchange": "NSE_SME",
                "listing_date_iso": "2024-09-11",
                "isin": "INE0U9J01013",
                "business_summary": "E-waste collection, dismantling, PCB and lithium battery recycling facility.",
                "source_name": "SEED_RECENT_LISTING_CURATED",
                "value_type": "SEED_REFERENCE_SNAPSHOT",
            },
            {
                "symbol": "NETWEB",
                "company_name": "Netweb Technologies India Limited",
                "exchange": "NSE",
                "listing_date_iso": "2023-07-27",
                "isin": "INE0NT901020",
                "business_summary": "High-performance computing (Tyrone), GPU servers, AI systems and private cloud.",
                "source_name": "SEED_RECENT_LISTING_CURATED",
                "value_type": "SEED_REFERENCE_SNAPSHOT",
            },
            {
                "symbol": "CYIENTDLM",
                "company_name": "Cyient DLM Limited",
                "exchange": "NSE",
                "listing_date_iso": "2023-07-10",
                "isin": "INE055S01018",
                "business_summary": "High-reliability PCBA, cable harnesses, and precision machining.",
                "source_name": "SEED_RECENT_LISTING_CURATED",
                "value_type": "SEED_REFERENCE_SNAPSHOT",
            },
            {
                "symbol": "AVALON",
                "company_name": "Avalon Technologies Limited",
                "exchange": "NSE",
                "listing_date_iso": "2023-04-18",
                "isin": "INE0LCL01028",
                "business_summary": "Box-build EMS, PCB assembly, sheet metal enclosures, clean energy & power.",
                "source_name": "SEED_RECENT_LISTING_CURATED",
                "value_type": "SEED_REFERENCE_SNAPSHOT",
            },
            {
                "symbol": "RRKABEL",
                "company_name": "RR Kabel Limited",
                "exchange": "NSE",
                "listing_date_iso": "2023-09-20",
                "isin": "INE777K01022",
                "business_summary": "Wires, power cables, fire-survival industrial and data cables.",
                "source_name": "SEED_RECENT_LISTING_CURATED",
                "value_type": "SEED_REFERENCE_SNAPSHOT",
            },
        ]
        existing_syms = {r["symbol"] for r in recent}
        for c in curated_recent:
            if c["symbol"] not in existing_syms:
                recent.append(c)

        return ProviderPayload(
            data=recent,
            source_name=payload.source_name,
            source_url=payload.source_url,
            value_type=payload.value_type,
            is_live=payload.is_live,
        )
