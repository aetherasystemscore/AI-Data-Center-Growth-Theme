"""Security master management, ticker alias resolution, deduplication, and lifecycle tracking."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.config import get_config
from core.logging_config import get_logger
from core.schemas import SecurityRecordSchema

logger = get_logger("ai3.security_master")


class SecurityMaster:
    """In-memory and database-backed Security Master with ISIN deduplication and alias mapping."""

    def __init__(self, seed_path: Optional[Path] = None) -> None:
        self.config = get_config()
        self.seed_path = seed_path or self.config.seed_stocks_path
        self._by_symbol: Dict[str, SecurityRecordSchema] = {}
        self._by_isin: Dict[str, SecurityRecordSchema] = {}
        self._alias_to_symbol: Dict[str, str] = {}
        self._history_events: List[Dict[str, str]] = []

    def load_seed_universe(self) -> List[SecurityRecordSchema]:
        """Load and deduplicate the seed stock universe from CSV."""
        if not self.seed_path.exists():
            logger.warning("Seed stocks file not found at %s", self.seed_path)
            return []

        records: List[SecurityRecordSchema] = []
        with self.seed_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rec = self._parse_row(row)
                accepted, reason = self.register_security(rec)
                if accepted:
                    records.append(rec)
                else:
                    logger.info("Skipped duplicate security %s: %s", rec.symbol, reason)
        return records

    @staticmethod
    def _parse_row(row: Dict[str, str]) -> SecurityRecordSchema:
        raw_date = (row.get("listing_date") or "").strip()
        listing_dt = date.fromisoformat(raw_date) if raw_date else None
        subcats = [
            s.strip()
            for s in (row.get("subcategory_tags") or "").split("|")
            if s.strip()
        ]
        aliases = [
            a.strip().upper()
            for a in (row.get("aliases") or "").split("|")
            if a.strip()
        ]
        return SecurityRecordSchema(
            symbol=row["symbol"].strip().upper(),
            yf_ticker=(row.get("yf_ticker") or row["symbol"]).strip(),
            company_name=row["company_name"].strip(),
            isin=row["isin"].strip().upper(),
            exchange=row["exchange"].strip().upper(),
            country=(row.get("country") or "India").strip(),
            currency=(row.get("currency") or "INR").strip().upper(),
            security_type=(row.get("security_type") or "EQUITY").strip().upper(),
            listing_date=listing_dt,
            listing_status=(row.get("listing_status") or "ACTIVE").strip().upper(),
            universe_tier=(row.get("universe_tier") or "INVESTABLE_INDIA").strip().upper(),
            is_investable=str(row.get("is_investable", "true")).lower() == "true",
            high_risk_flag=str(row.get("high_risk_flag", "false")).lower() == "true",
            primary_category=row["primary_category"].strip(),
            subcategory_tags=subcats,
            aliases=aliases,
            verification_notes=(row.get("verification_notes") or "").strip(),
        )

    def register_security(
        self, record: SecurityRecordSchema, merge_tags_if_duplicate: bool = True
    ) -> Tuple[bool, str]:
        """Register a security, preventing duplicate tickers or ISINs while merging multi-sector tags."""
        sym = record.symbol.upper()
        isin = record.isin.upper()

        existing = self._by_symbol.get(sym) or (
            self._by_isin.get(isin) if not isin.startswith("UNVERIFIED") else None
        )
        if existing is not None:
            if merge_tags_if_duplicate:
                merged_subcats = list(
                    dict.fromkeys(existing.subcategory_tags + record.subcategory_tags)
                )
                existing.subcategory_tags = merged_subcats
                merged_aliases = list(dict.fromkeys(existing.aliases + record.aliases))
                existing.aliases = merged_aliases
            return False, f"Merged tags into existing security {existing.symbol} ({existing.isin})"

        self._by_symbol[sym] = record
        if isin and not isin.startswith("UNVERIFIED"):
            self._by_isin[isin] = record
        self._alias_to_symbol[sym] = sym
        for alias in record.aliases:
            self._alias_to_symbol[alias.upper()] = sym
        return True, "Registered"

    def resolve_symbol(self, ticker_or_alias: str) -> Optional[str]:
        """Resolve an exchange ticker, historical ticker alias, or ISIN to canonical symbol."""
        key = ticker_or_alias.strip().upper()
        if key in self._alias_to_symbol:
            return self._alias_to_symbol[key]
        if key in self._by_isin:
            return self._by_isin[key].symbol
        # Strip .NS or .BO suffix if passed
        if key.endswith(".NS") or key.endswith(".BO"):
            base = key[:-3]
            if base in self._alias_to_symbol:
                return self._alias_to_symbol[base]
        return None

    def get_security(self, ticker_or_alias: str) -> Optional[SecurityRecordSchema]:
        sym = self.resolve_symbol(ticker_or_alias)
        return self._by_symbol.get(sym) if sym else None

    def record_symbol_change(
        self,
        old_symbol: str,
        new_symbol: str,
        effective_date: date,
        reason: str = "EXCHANGE_SYMBOL_CHANGE",
    ) -> bool:
        """Update canonical symbol while preserving historical alias lookup and effective date."""
        old_sym = old_symbol.strip().upper()
        new_sym = new_symbol.strip().upper()
        if " " in new_sym or not new_sym:
            raise ValueError("New symbol must be a valid ticker, not a company name.")

        sec = self.get_security(old_sym)
        if sec is None:
            return False

        canonical_old = sec.symbol
        del self._by_symbol[canonical_old]
        if canonical_old not in sec.aliases:
            sec.aliases.append(canonical_old)
        if new_sym not in sec.aliases:
            sec.aliases.append(new_sym)
        sec.symbol = new_sym
        self._by_symbol[new_sym] = sec
        self._alias_to_symbol[canonical_old] = new_sym
        self._alias_to_symbol[old_sym] = new_sym
        self._alias_to_symbol[new_sym] = new_sym
        self._history_events.append(
            {
                "isin": sec.isin,
                "old_symbol": canonical_old,
                "new_symbol": new_sym,
                "effective_date": effective_date.isoformat(),
                "event_type": reason,
            }
        )
        return True

    def update_listing_status(
        self,
        symbol: str,
        new_status: str,
        effective_date: date,
        reason: str = "",
    ) -> bool:
        """Handle delistings, suspensions, surveillance, or demergers without deleting history."""
        sec = self.get_security(symbol)
        if sec is None:
            return False
        old_status = sec.listing_status
        sec.listing_status = new_status.strip().upper()
        if sec.listing_status != "ACTIVE":
            sec.is_investable = False
            sec.high_risk_flag = True
            if sec.universe_tier == "INVESTABLE_INDIA":
                sec.universe_tier = "HIGH_RISK_RESEARCH"
        self._history_events.append(
            {
                "isin": sec.isin,
                "old_symbol": sec.symbol,
                "new_symbol": sec.symbol,
                "effective_date": effective_date.isoformat(),
                "event_type": f"STATUS_CHANGE:{old_status}->{sec.listing_status}",
                "reason": reason,
            }
        )
        return True

    def list_investable_india(self) -> List[SecurityRecordSchema]:
        return [
            s
            for s in self._by_symbol.values()
            if s.country == "India"
            and s.is_investable
            and not s.high_risk_flag
            and s.listing_status == "ACTIVE"
        ]

    def list_high_risk_universe(self) -> List[SecurityRecordSchema]:
        return [
            s
            for s in self._by_symbol.values()
            if s.high_risk_flag or not s.is_investable or s.universe_tier == "HIGH_RISK_RESEARCH"
        ]

    def list_global_benchmarks(self) -> List[SecurityRecordSchema]:
        return [
            s
            for s in self._by_symbol.values()
            if s.universe_tier == "GLOBAL_BENCHMARK"
        ]

    def list_all(self) -> List[SecurityRecordSchema]:
        return list(self._by_symbol.values())

    @property
    def history_events(self) -> List[Dict[str, str]]:
        return list(self._history_events)


class SecurityMasterService:
    """Dictionary-oriented facade over `SecurityMaster` for analytics, jobs, pages, and tests."""

    KNOWN_ALIASES: Dict[str, str] = {
        "POWERINDIA": "HITACHIEN",
        "TARIL": "TRIL",
        "KPIL": "KALPATARU",
        "KALPATPOWR": "KALPATARU",
        "BBOX": "BLACKBOX",
        "DYNPRO": "DYNACONS",
        "SBGSY": "SU.PA",
        "SCHNEIDER": "SU.PA",
        "503681": "ELCIDIN",
        "530643": "ECORECO",
    }

    def __init__(self, seed_path: Optional[Path] = None) -> None:
        self._sm = SecurityMaster(seed_path=seed_path)
        self._sm.load_seed_universe()

    @staticmethod
    def _to_dict(rec: SecurityRecordSchema) -> Dict[str, object]:
        return {
            "symbol": rec.symbol,
            "yf_ticker": rec.yf_ticker,
            "company_name": rec.company_name,
            "isin": rec.isin,
            "exchange": rec.exchange,
            "country": rec.country,
            "currency": rec.currency,
            "security_type": rec.security_type,
            "listing_date": rec.listing_date.isoformat() if rec.listing_date else None,
            "listing_status": rec.listing_status,
            "universe_tier": rec.universe_tier,
            "is_investable": rec.is_investable,
            "high_risk_flag": rec.high_risk_flag,
            "primary_category": rec.primary_category,
            "subcategories": list(rec.subcategory_tags),
            "subcategory_tags": list(rec.subcategory_tags),
            "aliases": list(rec.aliases),
            "notes": rec.verification_notes,
            "verification_notes": rec.verification_notes,
        }

    def resolve_symbol(self, raw_ticker: str) -> str:
        clean = (raw_ticker or "").strip().upper()
        for suffix in (".NS", ".BO"):
            if clean.endswith(suffix):
                clean = clean[: -len(suffix)]
        if clean in self.KNOWN_ALIASES:
            return self.KNOWN_ALIASES[clean]
        resolved = self._sm.resolve_symbol(clean)
        return resolved or clean

    def get_security(self, symbol_or_alias: str) -> Optional[Dict[str, object]]:
        rec = self._sm.get_security(symbol_or_alias)
        return self._to_dict(rec) if rec else None

    def get_all_securities(
        self,
        investable_only: bool = False,
        country: Optional[str] = None,
        universe_tier: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        out = [self._to_dict(r) for r in self._sm.list_all()]
        if investable_only:
            out = [r for r in out if r["is_investable"]]
        if country:
            out = [r for r in out if str(r["country"]).lower() == country.lower()]
        if universe_tier:
            out = [r for r in out if r["universe_tier"] == universe_tier]
        return out

    def is_investable(self, symbol: str) -> bool:
        sec = self.get_security(symbol)
        return bool(sec and sec.get("is_investable", False))

    def validate_ticker_is_not_company_name(self, candidate: str) -> Tuple[bool, str]:
        if not candidate or not candidate.strip():
            return False, "Empty ticker symbol"
        clean = candidate.strip()
        if " " in clean and len(clean.split()) >= 2:
            return False, f"Rejected '{clean}': Company name or multi-word string passed instead of verified ticker"
        if len(clean) > 20:
            return False, f"Rejected '{clean}': Exceeds maximum exchange symbol length"
        resolved = self.resolve_symbol(clean)
        sec = self._sm.get_security(resolved)
        if sec is None:
            return False, f"Ticker '{clean}' (resolved '{resolved}') is not verified in Security Master"
        return True, f"Verified symbol {resolved}"

    def get_high_risk_universe(self) -> List[Dict[str, object]]:
        return [self._to_dict(r) for r in self._sm.list_high_risk_universe()]

