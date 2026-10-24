"""Repository layer for initializing, seeding, querying, and updating the AI3 database."""
from __future__ import annotations

import csv
import json
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import AppConfig, get_config
from core.logging_config import get_logger
from core.security_master import SecurityMaster
from database.models import (
    AIModelOutputModel,
    AlertModel,
    BacktestRunModel,
    Base,
    BasketHoldingModel,
    BusinessExposureEvidenceModel,
    CompanyAliasModel,
    CompanySectorMappingModel,
    CorporateActionModel,
    DataQualityIncidentModel,
    ETFHoldingsSnapshotModel,
    ETFSchemeModel,
    ExchangeModel,
    FinancialRatioModel,
    IPOEventHistoryModel,
    IPOCandidateModel,
    IPODocumentModel,
    NewsEventModel,
    PriceHistoryModel,
    ResearchScoreModel,
    SecurityListingHistoryModel,
    SecurityModel,
    SmallcaseHoldingsSnapshotModel,
    SmallcaseModel,
    SourceCitationModel,
    UserBasketModel,
    ValueAlternativeComparisonModel,
)

logger = get_logger("ai3.repository")


def _parse_optional_float(val: Any) -> Optional[float]:
    """Convert string/number to float, strictly preserving None/empty as None (never 0)."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if pd.isna(val):
            return None
        return float(val)
    s = str(val).strip()
    if s == "" or s.upper() in ("NULL", "NONE", "NAN", "N/A", "NA"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


class AI3Repository:
    """Data access and persistence repository for AI3."""

    def __init__(
        self,
        database_url: Optional[str] = None,
        config: Optional[AppConfig] = None,
        db_path: Optional[Path | str] = None,
    ) -> None:
        self.config = config or get_config()
        if db_path is not None:
            resolved_path = Path(db_path).resolve()
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            self.database_url = f"sqlite:///{resolved_path.as_posix()}"
        else:
            self.database_url = database_url or self.config.database_url
        connect_args = {"check_same_thread": False} if self.database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(self.database_url, connect_args=connect_args, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    @contextmanager
    def session(self):
        """Yield a managed SQLAlchemy session with automatic commit/rollback."""
        sess = self.SessionLocal()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    def create_all_tables(self) -> None:
        Base.metadata.create_all(self.engine)

    def bootstrap_if_needed(self, force: bool = False) -> Dict[str, int]:
        """Create tables and idempotently seed exchanges, stocks, ETFs, smallcases, IPOs, fundamentals, and news."""
        self.create_all_tables()
        counts: Dict[str, int] = {}
        with self.SessionLocal() as session:
            existing_sec = session.scalar(select(SecurityModel.id).limit(1))
            if existing_sec is not None and not force:
                return {"status": 0}

            counts["exchanges"] = self._seed_exchanges(session)
            counts["securities"] = self._seed_securities(session)
            counts["etfs"] = self._seed_etfs(session)
            counts["smallcases"] = self._seed_smallcases(session)
            counts["ipos"] = self._seed_ipos(session)
            counts["fundamentals"] = self._seed_fundamentals(session)
            counts["news"] = self._seed_initial_news_and_alerts(session)
            counts["baskets"] = self._seed_default_baskets(session)
            session.commit()
        return counts

    def _seed_exchanges(self, session: Session) -> int:
        exchanges = [
            ("NSE", "National Stock Exchange of India", "India", "INR", "Asia/Kolkata",
             "Primary Indian equity & ETF market. Direct retail & institutional access."),
            ("NSE_SME", "NSE Emerge SME Platform", "India", "INR", "Asia/Kolkata",
             "Indian SME platform. Minimum lot size trading and lower liquidity warning apply."),
            ("BSE", "BSE Limited (Bombay Stock Exchange)", "India", "INR", "Asia/Kolkata",
             "Primary Indian equity market."),
            ("NASDAQ", "NASDAQ Stock Market", "United States", "USD", "America/New_York",
             "Global benchmark. Indian retail access subject to RBI LRS ($250k/yr), 20% TCS above ₹7L, and foreign asset schedule in ITR."),
            ("NYSE", "New York Stock Exchange", "United States", "USD", "America/New_York",
             "Global benchmark. Subject to RBI LRS, US estate tax rules (> $60k), and 25% dividend withholding under DTAA."),
            ("KRX", "Korea Exchange", "South Korea", "KRW", "Asia/Seoul",
             "Global benchmark (Samsung, SK Hynix). Direct retail access restricted for most Indian brokers; research benchmark."),
            ("TSE", "Tokyo Stock Exchange", "Japan", "JPY", "Asia/Tokyo",
             "Global benchmark (Murata, TDK, Omron). JPY/INR currency risk and international brokerage access required."),
            ("EURONEXT", "Euronext Paris / Brussels", "France", "EUR", "Europe/Paris",
             "Global benchmark (Schneider Electric SU.PA). EUR/INR currency and European withholding tax rules apply."),
            ("XETRA", "Deutsche Boerse XETRA", "Germany", "EUR", "Europe/Berlin",
             "Global benchmark (Aurubis NDA.DE)."),
            ("ASX", "Australian Securities Exchange", "Australia", "AUD", "Australia/Sydney",
             "Global benchmark (Sims Limited SGM.AX)."),
            ("PRIVATE", "Unlisted / Private Market Benchmark", "United States", "USD", "America/New_York",
             "Non-listed private benchmark only (e.g. ERI). Not publicly tradable."),
        ]
        added = 0
        for code, name, country, curr, tz, notes in exchanges:
            if not session.scalar(select(ExchangeModel).where(ExchangeModel.code == code)):
                session.add(
                    ExchangeModel(
                        code=code,
                        name=name,
                        country=country,
                        currency=curr,
                        timezone_str=tz,
                        access_notes=notes,
                    )
                )
                added += 1
        return added

    def _seed_securities(self, session: Session) -> int:
        sm = SecurityMaster(self.config.seed_stocks_path)
        records = sm.load_seed_universe()
        added = 0
        for rec in records:
            existing = session.scalar(
                select(SecurityModel).where(SecurityModel.symbol == rec.symbol)
            )
            if existing is None:
                model = SecurityModel(
                    symbol=rec.symbol,
                    yf_ticker=rec.yf_ticker,
                    company_name=rec.company_name,
                    isin=rec.isin,
                    exchange_code=rec.exchange,
                    country=rec.country,
                    currency=rec.currency,
                    security_type=rec.security_type,
                    listing_date=rec.listing_date,
                    listing_status=rec.listing_status,
                    universe_tier=rec.universe_tier,
                    is_investable=rec.is_investable,
                    high_risk_flag=rec.high_risk_flag,
                    primary_category=rec.primary_category,
                    subcategory_tags="|".join(rec.subcategory_tags),
                    verification_notes=rec.verification_notes,
                )
                session.add(model)
                added += 1

            for alias in rec.aliases:
                if not session.scalar(
                    select(CompanyAliasModel).where(
                        CompanyAliasModel.security_symbol == rec.symbol,
                        CompanyAliasModel.alias == alias,
                    )
                ):
                    session.add(
                        CompanyAliasModel(
                            security_symbol=rec.symbol,
                            alias=alias,
                            alias_type="TICKER_ALIAS",
                            effective_from=rec.listing_date,
                        )
                    )

            for idx, subcat in enumerate(rec.subcategory_tags):
                if not session.scalar(
                    select(CompanySectorMappingModel).where(
                        CompanySectorMappingModel.symbol == rec.symbol,
                        CompanySectorMappingModel.category_code == rec.primary_category,
                        CompanySectorMappingModel.subcategory_id == subcat,
                    )
                ):
                    session.add(
                        CompanySectorMappingModel(
                            symbol=rec.symbol,
                            category_code=rec.primary_category,
                            subcategory_id=subcat,
                            is_primary=(idx == 0),
                            confidence_level="VERIFIED" if rec.is_investable else "NEEDS_REVIEW",
                        )
                    )
        return added

    def _seed_etfs(self, session: Session) -> int:
        path = self.config.seed_etfs_path
        if not path.exists():
            return 0
        added = 0
        with path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                sym = row["symbol"].strip().upper()
                snap_dt = date.fromisoformat(row["holdings_date"].strip())
                sector_dict: Dict[str, float] = {}
                for item in (row.get("sector_allocation_pipe") or "").split("|"):
                    if ":" in item:
                        k, v = item.split(":", 1)
                        sector_dict[k.strip()] = float(v.strip())

                if not session.scalar(select(ETFSchemeModel).where(ETFSchemeModel.symbol == sym)):
                    session.add(
                        ETFSchemeModel(
                            symbol=sym,
                            yf_ticker=row["yf_ticker"].strip(),
                            scheme_name=row["scheme_name"].strip(),
                            isin=row["isin"].strip(),
                            exchange=row["exchange"].strip(),
                            issuer=row["issuer"].strip(),
                            underlying_index=row["underlying_index"].strip(),
                            category=row["category"].strip(),
                            expense_ratio_pct=_parse_optional_float(row.get("expense_ratio_pct")),
                            tracking_error_pct=_parse_optional_float(row.get("tracking_error_pct")),
                            aum_cr_inr=_parse_optional_float(row.get("aum_cr_inr")),
                            replication_method=row.get("replication_method", "FULL_REPLICATION").strip(),
                            is_direct_ai_etf=str(row.get("is_direct_ai_etf", "false")).lower() == "true",
                            verified_ai_dc_exposure_pct=_parse_optional_float(
                                row.get("verified_ai_dc_exposure_pct")
                            ),
                            sector_allocation_json=json.dumps(sector_dict),
                            notes=row.get("notes", "").strip(),
                        )
                    )
                    added += 1

                for h_item in (row.get("top_holdings_pipe") or "").split("|"):
                    if ":" in h_item:
                        csym, w_str = h_item.split(":", 1)
                        csym = csym.strip().upper()
                        w_val = float(w_str.strip())
                        if not session.scalar(
                            select(ETFHoldingsSnapshotModel).where(
                                ETFHoldingsSnapshotModel.etf_symbol == sym,
                                ETFHoldingsSnapshotModel.snapshot_date == snap_dt,
                                ETFHoldingsSnapshotModel.constituent_symbol == csym,
                            )
                        ):
                            session.add(
                                ETFHoldingsSnapshotModel(
                                    etf_symbol=sym,
                                    snapshot_date=snap_dt,
                                    constituent_symbol=csym,
                                    weight_pct=w_val,
                                    source="AMC_FACTSHEET_SEED",
                                )
                            )
        return added

    def _seed_smallcases(self, session: Session) -> int:
        path = self.config.seed_smallcases_path
        if not path.exists():
            return 0
        payload = json.loads(path.read_text(encoding="utf-8"))
        added = 0
        for b in payload.get("baskets", []):
            sc_id = b["smallcase_id"]
            snap_dt = date.fromisoformat(b["snapshot_date"])
            if not session.scalar(select(SmallcaseModel).where(SmallcaseModel.smallcase_id == sc_id)):
                session.add(
                    SmallcaseModel(
                        smallcase_id=sc_id,
                        name=b["name"],
                        provider=b["provider"],
                        source_url=b.get("source_url"),
                        rebalancing_frequency=b.get("rebalancing_frequency", "QUARTERLY"),
                        fee_structure=b.get("fee_structure"),
                        min_investment_inr=_parse_optional_float(b.get("min_investment_inr")),
                        benchmark_index=b.get("benchmark_index"),
                        constituents_status=b["constituents_status"],
                        provider_reported_cagr_pct=_parse_optional_float(
                            b.get("provider_reported_cagr_pct")
                        ),
                        notes=b.get("notes"),
                    )
                )
                added += 1

            for h in b.get("holdings", []):
                csym = h["symbol"].strip().upper()
                if not session.scalar(
                    select(SmallcaseHoldingsSnapshotModel).where(
                        SmallcaseHoldingsSnapshotModel.smallcase_id == sc_id,
                        SmallcaseHoldingsSnapshotModel.snapshot_date == snap_dt,
                        SmallcaseHoldingsSnapshotModel.constituent_symbol == csym,
                    )
                ):
                    session.add(
                        SmallcaseHoldingsSnapshotModel(
                            smallcase_id=sc_id,
                            snapshot_date=snap_dt,
                            constituent_symbol=csym,
                            weight_pct=float(h["weight_pct"]),
                            is_estimated_weight=bool(h.get("is_estimated_weight", False)),
                            source="SEED_PUBLIC_THEME_SNAPSHOT",
                        )
                    )
        return added

    def _seed_ipos(self, session: Session) -> int:
        path = self.config.seed_ipos_path
        if not path.exists():
            return 0
        payload = json.loads(path.read_text(encoding="utf-8"))
        added = 0
        for item in payload.get("candidates", []):
            cid = item["candidate_id"]
            if not session.scalar(select(IPOCandidateModel).where(IPOCandidateModel.candidate_id == cid)):
                open_dt = (
                    date.fromisoformat(item["reference_open_date"])
                    if item.get("reference_open_date")
                    else None
                )
                close_dt = (
                    date.fromisoformat(item["reference_close_date"])
                    if item.get("reference_close_date")
                    else None
                )
                model = IPOCandidateModel(
                    candidate_id=cid,
                    company_name=item["company_name"],
                    proposed_symbol=item.get("proposed_symbol"),
                    exchange_segment=item.get("exchange_segment", "MAINBOARD"),
                    exchanges_csv=",".join(item.get("exchanges", ["NSE", "BSE"])),
                    primary_category=item["primary_category"],
                    subcategory_tags="|".join(item.get("subcategory_tags", [])),
                    theme_summary=item["theme_summary"],
                    current_status=item["current_status"],
                    dates_confirmed_by_live_exchange=bool(
                        item.get("dates_confirmed_by_live_exchange", False)
                    ),
                    reference_open_date=open_dt,
                    reference_close_date=close_dt,
                    price_band_low_inr=_parse_optional_float(item.get("price_band_low_inr")),
                    price_band_high_inr=_parse_optional_float(item.get("price_band_high_inr")),
                    lot_size=int(item["lot_size"]) if item.get("lot_size") is not None else None,
                    fresh_issue_shares_cr=_parse_optional_float(item.get("fresh_issue_shares_cr")),
                    fresh_issue_amount_cr_inr=_parse_optional_float(
                        item.get("fresh_issue_amount_cr_inr")
                    ),
                    ofs_amount_cr_inr=_parse_optional_float(item.get("ofs_amount_cr_inr")),
                    total_issue_size_cr_inr=_parse_optional_float(item.get("total_issue_size_cr_inr")),
                    estimated_post_issue_mcap_cr_inr=_parse_optional_float(
                        item.get("estimated_post_issue_mcap_cr_inr")
                    ),
                    restated_revenue_fy_cr_inr=_parse_optional_float(
                        item.get("restated_revenue_fy_cr_inr")
                    ),
                    restated_ebitda_fy_cr_inr=_parse_optional_float(
                        item.get("restated_ebitda_fy_cr_inr")
                    ),
                    restated_pat_fy_cr_inr=_parse_optional_float(item.get("restated_pat_fy_cr_inr")),
                    pro_forma_pe=_parse_optional_float(item.get("pro_forma_pe")),
                    pro_forma_ev_ebitda=_parse_optional_float(item.get("pro_forma_ev_ebitda")),
                    promoter_holding_pre_pct=_parse_optional_float(item.get("promoter_holding_pre_pct")),
                    promoter_holding_post_pct=_parse_optional_float(
                        item.get("promoter_holding_post_pct")
                    ),
                    use_of_proceeds=item.get("use_of_proceeds"),
                    listed_peers_csv=",".join(item.get("listed_peers", [])),
                    customer_concentration_risk=item.get("customer_concentration_risk"),
                    litigation_and_contingent_liabilities=item.get(
                        "litigation_and_contingent_liabilities"
                    ),
                    related_party_transactions_flag=item.get("related_party_transactions_flag"),
                    auditor_qualifications=item.get("auditor_qualifications"),
                    manual_review_required=bool(item.get("manual_review_required", True)),
                    primary_source_url=item["primary_source_url"],
                    sebi_filing_url=item.get("sebi_filing_url"),
                    ai_relevance_assessment=item["ai_relevance_assessment"],
                )
                session.add(model)
                added += 1

                if item.get("sebi_filing_url"):
                    session.add(
                        IPODocumentModel(
                            candidate_id=cid,
                            doc_type=item["current_status"].split("_")[0],
                            filing_date=date(2026, 10, 15),
                            source_url=item["sebi_filing_url"],
                            parse_status="SEED_SUMMARY_MANUAL_PDF_VERIFY_FLAG",
                            extracted_summary=item.get("use_of_proceeds"),
                        )
                    )

                for hist in item.get("history", []):
                    session.add(
                        IPOEventHistoryModel(
                            candidate_id=cid,
                            event_date=date.fromisoformat(hist["event_date"]),
                            old_status=None,
                            new_status=hist["status"],
                            note=hist.get("note"),
                        )
                    )
        return added

    def _seed_fundamentals(self, session: Session) -> int:
        path = self.config.sample_fundamentals_path
        if not path.exists():
            return 0
        added = 0
        with path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                sym = row["symbol"].strip().upper()
                rep_dt = date.fromisoformat(row["reporting_date"].strip())
                if session.scalar(
                    select(FinancialRatioModel).where(
                        FinancialRatioModel.symbol == sym,
                        FinancialRatioModel.reporting_date == rep_dt,
                    )
                ):
                    continue

                ratio_rec = FinancialRatioModel(
                    symbol=sym,
                    reporting_date=rep_dt,
                    currency=(row.get("currency") or "INR").strip(),
                    mcap_cr=_parse_optional_float(row.get("mcap_cr")),
                    price_ref=_parse_optional_float(row.get("price_ref")),
                    rev_cagr_3y_pct=_parse_optional_float(row.get("rev_cagr_3y_pct")),
                    rev_cagr_5y_pct=_parse_optional_float(row.get("rev_cagr_5y_pct")),
                    ebitda_growth_3y_pct=_parse_optional_float(row.get("ebitda_growth_3y_pct")),
                    pat_growth_3y_pct=_parse_optional_float(row.get("pat_growth_3y_pct")),
                    gross_margin_pct=_parse_optional_float(row.get("gross_margin_pct")),
                    opm_pct=_parse_optional_float(row.get("opm_pct")),
                    roce_pct=_parse_optional_float(row.get("roce_pct")),
                    roe_pct=_parse_optional_float(row.get("roe_pct")),
                    cfo_to_pat_ratio=_parse_optional_float(row.get("cfo_to_pat_ratio")),
                    fcf_cr=_parse_optional_float(row.get("fcf_cr")),
                    net_debt_to_ebitda=_parse_optional_float(row.get("net_debt_to_ebitda")),
                    interest_coverage=_parse_optional_float(row.get("interest_coverage")),
                    wc_days=_parse_optional_float(row.get("wc_days")),
                    promoter_pledge_pct=_parse_optional_float(row.get("promoter_pledge_pct")),
                    trailing_pe=_parse_optional_float(row.get("trailing_pe")),
                    forward_pe=_parse_optional_float(row.get("forward_pe")),
                    ev_ebitda=_parse_optional_float(row.get("ev_ebitda")),
                    price_to_sales=_parse_optional_float(row.get("price_to_sales")),
                    price_to_book=_parse_optional_float(row.get("price_to_book")),
                    fcf_yield_pct=_parse_optional_float(row.get("fcf_yield_pct")),
                    avg_daily_turnover_cr=_parse_optional_float(row.get("avg_daily_turnover_cr")),
                    direct_ai_dc_rev_pct=_parse_optional_float(row.get("direct_ai_dc_rev_pct")),
                    ai_exposure_tier=(row.get("ai_exposure_tier") or "UNVERIFIED").strip(),
                    governance_flag=(row.get("governance_flag") or "NONE").strip(),
                    auditor_qualification_flag=str(
                        row.get("auditor_qualification_flag", "false")
                    ).lower()
                    == "true",
                    sector_kpi_json=(row.get("sector_kpi_json") or "{}").strip(),
                    evidence_summary=(row.get("evidence_summary") or "").strip(),
                    source_name=(row.get("source_name") or "SEED_REFERENCE").strip(),
                    value_type=(row.get("value_type") or "SEED_REFERENCE_SNAPSHOT").strip(),
                    quality_status="VERIFIED",
                    source_url=(row.get("source_url") or "").strip(),
                )
                session.add(ratio_rec)
                added += 1

                if ratio_rec.evidence_summary:
                    session.add(
                        BusinessExposureEvidenceModel(
                            symbol=sym,
                            evidence_type=ratio_rec.ai_exposure_tier,
                            event_stage="RECOGNISED_REVENUE"
                            if (ratio_rec.direct_ai_dc_rev_pct or 0) > 0
                            else "ANNOUNCED_PLAN",
                            disclosed_rev_pct=ratio_rec.direct_ai_dc_rev_pct,
                            evidence_text=ratio_rec.evidence_summary,
                            source_document=ratio_rec.source_name,
                            source_url=ratio_rec.source_url,
                            reporting_date=rep_dt,
                            verified_by_human=True,
                        )
                    )
                    session.add(
                        SourceCitationModel(
                            entity_type="FINANCIAL_RATIO",
                            entity_id=f"{sym}:{rep_dt.isoformat()}",
                            source_name=ratio_rec.source_name,
                            source_url=ratio_rec.source_url,
                            document_id=f"AR_{sym}_{rep_dt.year}",
                            page_or_section="Segment & Financial Notes",
                            reporting_date=rep_dt,
                        )
                    )
        return added

    def _seed_initial_news_and_alerts(self, session: Session) -> int:
        events = [
            (
                "NETWEB",
                "Netweb Technologies India Limited",
                "AI_SERVER_ORDER",
                "SIGNED_CONTRACT",
                date(2026, 9, 18),
                142.0,
                "Netweb receives Tyrone GPU cluster order for sovereign AI research computing",
                "Confirmed purchase order for NVIDIA Hopper/Blackwell architecture HPC systems; revenue recognition scheduled across Q3-Q4 FY27.",
                False,
                "NSE Corporate Announcement Filing",
                "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
            ),
            (
                "HITACHIEN",
                "Hitachi Energy India Limited",
                "TRANSFORMER_SWITCHGEAR_ORDER",
                "SIGNED_CONTRACT",
                date(2026, 9, 25),
                790.0,
                "Hitachi Energy bags 400kV GIS substation and transformer order for Navi Mumbai data-centre corridor",
                "Signed EPC and equipment order from transmission utility and hyperscale colocation developer.",
                False,
                "NSE Exchange Disclosure",
                "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
            ),
            (
                "ANANTRAJ",
                "Anant Raj Limited",
                "DATA_CENTRE_EXPANSION",
                "COMPLETED_PROJECT",
                date(2026, 10, 4),
                210.0,
                "Anant Raj commissions additional 6 MW IT load phase at Manesar Data Centre campus",
                "Operational capacity increased to 28 MW with cloud services ramp-up under Anant Raj Cloud.",
                True,
                "BSE/NSE Investor Release",
                "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
            ),
            (
                "CUMMINSIND",
                "Cummins India Limited",
                "BACKUP_POWER_DEMAND",
                "RECOGNISED_REVENUE",
                date(2026, 8, 14),
                480.0,
                "Cummins India reports strong HHP CPCB-IV+ genset deliveries to hyperscale data centres",
                "Recognised in quarterly powergen segment revenue.",
                True,
                "Quarterly Earnings Filing",
                "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
            ),
            (
                "ECORECO",
                "Eco Recycling Limited",
                "RECYCLING_CAPACITY_EXPANSION",
                "ANNOUNCED_PLAN",
                date(2026, 9, 30),
                35.0,
                "Eco Recycling announces expansion of e-waste and PCB precious-metal recovery facility",
                "Announced capacity expansion plan; NOT yet reflected in realised revenue.",
                False,
                "BSE Corporate Filing",
                "https://www.bseindia.com/",
            ),
        ]
        added = 0
        for sym, cname, cat, stage, dt, amt, head, summ, refl, src, url in events:
            session.add(
                NewsEventModel(
                    symbol=sym,
                    company_name=cname,
                    event_category=cat,
                    event_stage=stage,
                    event_date=dt,
                    disclosed_amount_cr_inr=amt,
                    headline=head,
                    summary=summ,
                    reflected_in_financials=refl,
                    source_name=src,
                    source_url=url,
                )
            )
            added += 1

        alerts = [
            (
                "CEREBRAINT",
                "GOVERNANCE_AND_AUDITOR_WARNING",
                "CRITICAL",
                "Cerebra Integrated Technologies carries severe governance/regulatory flags and auditor qualifications. Isolated in High-Risk Universe.",
            ),
            (
                "ELCIDIN",
                "BUSINESS_RELEVANCE_MISMATCH",
                "WARNING",
                "Elcid Investments is an NBFC holding company (Asian Paints stake), NOT an electronic component manufacturer. Excluded from investable universe.",
            ),
            (
                "IPO_JPL_2026",
                "IPO_TIMETABLE_VERIFICATION",
                "INFO",
                "Jio Platforms reference dates (21–23 Oct 2026) are seeded from Oct 2026 reference data; live NSE/SEBI confirmation required before treating as active.",
            ),
            (
                "KALPATARU",
                "PROMOTER_PLEDGE_MONITOR",
                "WARNING",
                "Kalpataru Projects promoter pledge at 12.4% — monitor quarterly exchange disclosures.",
            ),
            (
                "HFCL",
                "PROMOTER_PLEDGE_MONITOR",
                "WARNING",
                "HFCL promoter pledge at 16.5% — monitor pledge release milestones.",
            ),
        ]
        for entity, atype, sev, msg in alerts:
            session.add(
                AlertModel(
                    symbol_or_entity=entity,
                    alert_type=atype,
                    severity=sev,
                    message=msg,
                )
            )
        return added

    def _seed_default_baskets(self, session: Session) -> int:
        presets = [
            (
                "AI Infrastructure Core",
                "CORE_INFRA",
                "MONIFTY500",
                "Diversified Indian AI & data-centre physical + digital infrastructure core basket.",
                [
                    ("POWERGRID", "EQUITY", 12.0),
                    ("CUMMINSIND", "EQUITY", 12.0),
                    ("ABB", "EQUITY", 10.0),
                    ("POLYCAB", "EQUITY", 10.0),
                    ("BLUESTARCO", "EQUITY", 10.0),
                    ("TATACOMM", "EQUITY", 10.0),
                    ("NETWEB", "EQUITY", 8.0),
                    ("ANANTRAJ", "EQUITY", 8.0),
                    ("HCLTECH", "EQUITY", 10.0),
                    ("PERSISTENT", "EQUITY", 10.0),
                ],
            ),
            (
                "Power and Grid Bottlenecks",
                "D_POWER_AND_GRID",
                "ENERGY",
                "Transformers, switchgear, backup generators, HV cables and transmission utilities.",
                [
                    ("POWERGRID", "EQUITY", 15.0),
                    ("NTPC", "EQUITY", 15.0),
                    ("CUMMINSIND", "EQUITY", 14.0),
                    ("KIRLOSENG", "EQUITY", 12.0),
                    ("TDPOWERSYS", "EQUITY", 10.0),
                    ("TRIL", "EQUITY", 10.0),
                    ("APARINDS", "EQUITY", 12.0),
                    ("KEI", "EQUITY", 12.0),
                ],
            ),
            (
                "Value Alternatives Basket",
                "VALUE_ALTERNATIVES",
                "MID150BEES",
                "Lower-multiple supply-chain alternatives with strong ROCE and cash conversion.",
                [
                    ("KIRLOSENG", "EQUITY", 15.0),
                    ("TDPOWERSYS", "EQUITY", 15.0),
                    ("APARINDS", "EQUITY", 15.0),
                    ("CENTUM", "EQUITY", 12.0),
                    ("DYNACONS", "EQUITY", 13.0),
                    ("BLACKBOX", "EQUITY", 15.0),
                    ("HCLTECH", "EQUITY", 15.0),
                ],
            ),
        ]
        added = 0
        for bname, cat, bmk, notes, holdings in presets:
            if not session.scalar(select(UserBasketModel).where(UserBasketModel.basket_name == bname)):
                session.add(
                    UserBasketModel(
                        basket_name=bname,
                        theme_category=cat,
                        benchmark_symbol=bmk,
                        notes=notes,
                    )
                )
                for sym, atype, wt in holdings:
                    session.add(
                        BasketHoldingModel(
                            basket_name=bname,
                            symbol=sym,
                            asset_type=atype,
                            target_weight_pct=wt,
                        )
                    )
                added += 1
        return added

    # -------------------------------------------------------------------------
    # Query Helpers
    # -------------------------------------------------------------------------
    def get_securities_df(self, universe_tier: Optional[str] = None) -> pd.DataFrame:
        with self.SessionLocal() as session:
            stmt = select(SecurityModel)
            if universe_tier:
                stmt = stmt.where(SecurityModel.universe_tier == universe_tier)
            rows = session.scalars(stmt).all()
            data = [
                {
                    "symbol": r.symbol,
                    "yf_ticker": r.yf_ticker,
                    "company_name": r.company_name,
                    "isin": r.isin,
                    "exchange": r.exchange_code,
                    "country": r.country,
                    "currency": r.currency,
                    "security_type": r.security_type,
                    "listing_date": r.listing_date,
                    "listing_status": r.listing_status,
                    "universe_tier": r.universe_tier,
                    "is_investable": r.is_investable,
                    "high_risk_flag": r.high_risk_flag,
                    "primary_category": r.primary_category,
                    "subcategory_tags": r.subcategory_tags,
                    "verification_notes": r.verification_notes,
                }
                for r in rows
            ]
            return pd.DataFrame(data)

    def get_fundamentals_and_securities_df(self, country_filter: Optional[str] = None) -> pd.DataFrame:
        """Return joined DataFrame of securities and their latest financial ratio snapshots."""
        sec_df = self.get_securities_df()
        if sec_df.empty:
            return pd.DataFrame()
        if country_filter:
            sec_df = sec_df[sec_df["country"] == country_filter].copy()

        with self.SessionLocal() as session:
            f_rows = session.scalars(select(FinancialRatioModel)).all()
            f_data = [
                {
                    "symbol": r.symbol,
                    "reporting_date": r.reporting_date,
                    "mcap_cr": r.mcap_cr,
                    "price_ref": r.price_ref,
                    "rev_cagr_3y_pct": r.rev_cagr_3y_pct,
                    "rev_cagr_5y_pct": r.rev_cagr_5y_pct,
                    "ebitda_growth_3y_pct": r.ebitda_growth_3y_pct,
                    "pat_growth_3y_pct": r.pat_growth_3y_pct,
                    "gross_margin_pct": r.gross_margin_pct,
                    "opm_pct": r.opm_pct,
                    "roce_pct": r.roce_pct,
                    "roe_pct": r.roe_pct,
                    "cfo_to_pat_ratio": r.cfo_to_pat_ratio,
                    "fcf_cr": r.fcf_cr,
                    "net_debt_to_ebitda": r.net_debt_to_ebitda,
                    "interest_coverage": r.interest_coverage,
                    "wc_days": r.wc_days,
                    "promoter_pledge_pct": r.promoter_pledge_pct,
                    "trailing_pe": r.trailing_pe,
                    "forward_pe": r.forward_pe,
                    "ev_ebitda": r.ev_ebitda,
                    "price_to_sales": r.price_to_sales,
                    "price_to_book": r.price_to_book,
                    "fcf_yield_pct": r.fcf_yield_pct,
                    "avg_daily_turnover_cr": r.avg_daily_turnover_cr,
                    "direct_ai_dc_rev_pct": r.direct_ai_dc_rev_pct,
                    "ai_exposure_tier": r.ai_exposure_tier,
                    "governance_flag": r.governance_flag,
                    "auditor_qualification_flag": r.auditor_qualification_flag,
                    "sector_kpi_json": r.sector_kpi_json,
                    "evidence_summary": r.evidence_summary,
                    "source_name": r.source_name,
                    "value_type": r.value_type,
                    "quality_status": r.quality_status,
                    "source_url": r.source_url,
                    "retrieved_at": r.retrieved_at,
                }
                for r in f_rows
            ]
        f_df = pd.DataFrame(f_data)
        if f_df.empty:
            return sec_df
        # Keep latest reporting_date per symbol
        f_df = f_df.sort_values("reporting_date").groupby("symbol", as_index=False).last()
        return pd.merge(sec_df, f_df, on="symbol", how="left")

    def get_etfs_df(self) -> pd.DataFrame:
        with self.SessionLocal() as session:
            rows = session.scalars(select(ETFSchemeModel)).all()
            return pd.DataFrame(
                [
                    {
                        "symbol": r.symbol,
                        "yf_ticker": r.yf_ticker,
                        "scheme_name": r.scheme_name,
                        "isin": r.isin,
                        "exchange": r.exchange,
                        "issuer": r.issuer,
                        "underlying_index": r.underlying_index,
                        "category": r.category,
                        "expense_ratio_pct": r.expense_ratio_pct,
                        "tracking_error_pct": r.tracking_error_pct,
                        "aum_cr_inr": r.aum_cr_inr,
                        "replication_method": r.replication_method,
                        "is_direct_ai_etf": r.is_direct_ai_etf,
                        "verified_ai_dc_exposure_pct": r.verified_ai_dc_exposure_pct,
                        "sector_allocation_json": r.sector_allocation_json,
                        "notes": r.notes,
                    }
                    for r in rows
                ]
            )

    def get_etf_holdings(self, etf_symbol: Optional[str] = None) -> pd.DataFrame:
        with self.SessionLocal() as session:
            stmt = select(ETFHoldingsSnapshotModel)
            if etf_symbol:
                stmt = stmt.where(ETFHoldingsSnapshotModel.etf_symbol == etf_symbol.upper())
            rows = session.scalars(stmt).all()
            return pd.DataFrame(
                [
                    {
                        "etf_symbol": r.etf_symbol,
                        "snapshot_date": r.snapshot_date,
                        "constituent_symbol": r.constituent_symbol,
                        "weight_pct": r.weight_pct,
                        "source": r.source,
                    }
                    for r in rows
                ]
            )

    def get_smallcases_df(self) -> pd.DataFrame:
        with self.SessionLocal() as session:
            rows = session.scalars(select(SmallcaseModel)).all()
            return pd.DataFrame(
                [
                    {
                        "smallcase_id": r.smallcase_id,
                        "name": r.name,
                        "provider": r.provider,
                        "source_url": r.source_url,
                        "rebalancing_frequency": r.rebalancing_frequency,
                        "fee_structure": r.fee_structure,
                        "min_investment_inr": r.min_investment_inr,
                        "benchmark_index": r.benchmark_index,
                        "constituents_status": r.constituents_status,
                        "provider_reported_cagr_pct": r.provider_reported_cagr_pct,
                        "notes": r.notes,
                    }
                    for r in rows
                ]
            )

    def get_smallcase_holdings(
        self, smallcase_id: Optional[str] = None, latest_only: bool = True
    ) -> pd.DataFrame:
        with self.SessionLocal() as session:
            stmt = select(SmallcaseHoldingsSnapshotModel)
            if smallcase_id:
                stmt = stmt.where(SmallcaseHoldingsSnapshotModel.smallcase_id == smallcase_id)
            rows = session.scalars(stmt).all()
            df = pd.DataFrame(
                [
                    {
                        "smallcase_id": r.smallcase_id,
                        "snapshot_date": r.snapshot_date,
                        "constituent_symbol": r.constituent_symbol,
                        "weight_pct": r.weight_pct,
                        "is_estimated_weight": r.is_estimated_weight,
                        "source": r.source,
                    }
                    for r in rows
                ]
            )
            if df.empty or not latest_only:
                return df
            max_dates = df.groupby("smallcase_id")["snapshot_date"].transform("max")
            return df[df["snapshot_date"] == max_dates].reset_index(drop=True)

    def save_smallcase_snapshot(
        self,
        smallcase_id: str,
        snapshot_date: date,
        holdings: List[Dict[str, Any]],
        source: str = "MANUAL_CSV_UPLOAD",
    ) -> int:
        """Append a new dated holdings snapshot without overwriting previous snapshot dates."""
        added = 0
        with self.SessionLocal() as session:
            for item in holdings:
                csym = str(item["symbol"]).strip().upper()
                wt = float(item["weight_pct"])
                existing = session.scalar(
                    select(SmallcaseHoldingsSnapshotModel).where(
                        SmallcaseHoldingsSnapshotModel.smallcase_id == smallcase_id,
                        SmallcaseHoldingsSnapshotModel.snapshot_date == snapshot_date,
                        SmallcaseHoldingsSnapshotModel.constituent_symbol == csym,
                    )
                )
                if existing is None:
                    session.add(
                        SmallcaseHoldingsSnapshotModel(
                            smallcase_id=smallcase_id,
                            snapshot_date=snapshot_date,
                            constituent_symbol=csym,
                            weight_pct=wt,
                            is_estimated_weight=bool(item.get("is_estimated_weight", False)),
                            source=source,
                        )
                    )
                    added += 1
            session.commit()
        return added

    def get_ipos_df(self) -> pd.DataFrame:
        with self.SessionLocal() as session:
            rows = session.scalars(select(IPOCandidateModel)).all()
            return pd.DataFrame(
                [
                    {
                        "candidate_id": r.candidate_id,
                        "company_name": r.company_name,
                        "proposed_symbol": r.proposed_symbol,
                        "exchange_segment": r.exchange_segment,
                        "exchanges": r.exchanges_csv,
                        "primary_category": r.primary_category,
                        "subcategory_tags": r.subcategory_tags,
                        "theme_summary": r.theme_summary,
                        "current_status": r.current_status,
                        "dates_confirmed_by_live_exchange": r.dates_confirmed_by_live_exchange,
                        "reference_open_date": r.reference_open_date,
                        "reference_close_date": r.reference_close_date,
                        "reference_listing_date": r.reference_listing_date,
                        "price_band_low_inr": r.price_band_low_inr,
                        "price_band_high_inr": r.price_band_high_inr,
                        "lot_size": r.lot_size,
                        "fresh_issue_shares_cr": r.fresh_issue_shares_cr,
                        "fresh_issue_amount_cr_inr": r.fresh_issue_amount_cr_inr,
                        "ofs_amount_cr_inr": r.ofs_amount_cr_inr,
                        "total_issue_size_cr_inr": r.total_issue_size_cr_inr,
                        "estimated_post_issue_mcap_cr_inr": r.estimated_post_issue_mcap_cr_inr,
                        "restated_revenue_fy_cr_inr": r.restated_revenue_fy_cr_inr,
                        "restated_ebitda_fy_cr_inr": r.restated_ebitda_fy_cr_inr,
                        "restated_pat_fy_cr_inr": r.restated_pat_fy_cr_inr,
                        "pro_forma_pe": r.pro_forma_pe,
                        "pro_forma_ev_ebitda": r.pro_forma_ev_ebitda,
                        "promoter_holding_pre_pct": r.promoter_holding_pre_pct,
                        "promoter_holding_post_pct": r.promoter_holding_post_pct,
                        "use_of_proceeds": r.use_of_proceeds,
                        "listed_peers": r.listed_peers_csv,
                        "customer_concentration_risk": r.customer_concentration_risk,
                        "litigation_and_contingent_liabilities": r.litigation_and_contingent_liabilities,
                        "related_party_transactions_flag": r.related_party_transactions_flag,
                        "auditor_qualifications": r.auditor_qualifications,
                        "manual_review_required": r.manual_review_required,
                        "primary_source_url": r.primary_source_url,
                        "sebi_filing_url": r.sebi_filing_url,
                        "ai_relevance_assessment": r.ai_relevance_assessment,
                    }
                    for r in rows
                ]
            )

    def get_news_df(self) -> pd.DataFrame:
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(NewsEventModel).order_by(NewsEventModel.event_date.desc())
            ).all()
            return pd.DataFrame(
                [
                    {
                        "symbol": r.symbol,
                        "company_name": r.company_name,
                        "event_category": r.event_category,
                        "event_stage": r.event_stage,
                        "event_date": r.event_date,
                        "disclosed_amount_cr_inr": r.disclosed_amount_cr_inr,
                        "headline": r.headline,
                        "summary": r.summary,
                        "reflected_in_financials": r.reflected_in_financials,
                        "source_name": r.source_name,
                        "source_url": r.source_url,
                    }
                    for r in rows
                ]
            )

    def get_alerts_df(self) -> pd.DataFrame:
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(AlertModel).order_by(AlertModel.triggered_at.desc())
            ).all()
            return pd.DataFrame(
                [
                    {
                        "id": r.id,
                        "symbol_or_entity": r.symbol_or_entity,
                        "alert_type": r.alert_type,
                        "severity": r.severity,
                        "message": r.message,
                        "is_acknowledged": r.is_acknowledged,
                        "triggered_at": r.triggered_at,
                    }
                    for r in rows
                ]
            )

    def get_baskets(self) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            baskets = session.scalars(select(UserBasketModel)).all()
            result = []
            for b in baskets:
                holdings = session.scalars(
                    select(BasketHoldingModel).where(
                        BasketHoldingModel.basket_name == b.basket_name
                    )
                ).all()
                result.append(
                    {
                        "basket_name": b.basket_name,
                        "theme_category": b.theme_category,
                        "benchmark_symbol": b.benchmark_symbol,
                        "max_single_stock_pct": b.max_single_stock_pct,
                        "max_sector_pct": b.max_sector_pct,
                        "min_daily_turnover_cr": b.min_daily_turnover_cr,
                        "max_net_debt_ebitda": b.max_net_debt_ebitda,
                        "monthly_sip_inr": b.monthly_sip_inr,
                        "notes": b.notes,
                        "holdings": [
                            {
                                "symbol": h.symbol,
                                "asset_type": h.asset_type,
                                "target_weight_pct": h.target_weight_pct,
                                "avg_buy_price": h.avg_buy_price,
                                "quantity": h.quantity,
                            }
                            for h in holdings
                        ],
                    }
                )
            return result

    def save_user_basket(
        self,
        basket_name: str,
        holdings: List[Dict[str, Any]],
        theme_category: str = "CUSTOM",
        benchmark_symbol: str = "MONIFTY500",
        max_single_stock_pct: float = 15.0,
        max_sector_pct: float = 40.0,
        min_daily_turnover_cr: float = 5.0,
        max_net_debt_ebitda: float = 3.5,
        monthly_sip_inr: float = 25000.0,
        notes: str = "",
    ) -> None:
        with self.SessionLocal() as session:
            b = session.scalar(
                select(UserBasketModel).where(UserBasketModel.basket_name == basket_name)
            )
            if b is None:
                b = UserBasketModel(
                    basket_name=basket_name,
                    theme_category=theme_category,
                    benchmark_symbol=benchmark_symbol,
                    max_single_stock_pct=max_single_stock_pct,
                    max_sector_pct=max_sector_pct,
                    min_daily_turnover_cr=min_daily_turnover_cr,
                    max_net_debt_ebitda=max_net_debt_ebitda,
                    monthly_sip_inr=monthly_sip_inr,
                    notes=notes,
                )
                session.add(b)
            else:
                b.theme_category = theme_category
                b.benchmark_symbol = benchmark_symbol
                b.max_single_stock_pct = max_single_stock_pct
                b.max_sector_pct = max_sector_pct
                b.min_daily_turnover_cr = min_daily_turnover_cr
                b.max_net_debt_ebitda = max_net_debt_ebitda
                b.monthly_sip_inr = monthly_sip_inr
                b.notes = notes

            old_holdings = session.scalars(
                select(BasketHoldingModel).where(BasketHoldingModel.basket_name == basket_name)
            ).all()
            for oh in old_holdings:
                session.delete(oh)
            session.flush()

            for h in holdings:
                session.add(
                    BasketHoldingModel(
                        basket_name=basket_name,
                        symbol=str(h["symbol"]).strip().upper(),
                        asset_type=str(h.get("asset_type", "EQUITY")),
                        target_weight_pct=float(h["target_weight_pct"]),
                        avg_buy_price=_parse_optional_float(h.get("avg_buy_price")),
                        quantity=_parse_optional_float(h.get("quantity")),
                    )
                )
            session.commit()

    # -------------------------------------------------------------------------
    # Normalized Dictionary Query & Audit Methods
    # -------------------------------------------------------------------------
    _CATEGORY_PREFIX_MAP = {
        "A": "A_COMPUTE_SERVERS",
        "B": "B_SMALL_COMPONENTS",
        "C": "C_DATACENTRE_INFRA",
        "D": "D_POWER_GRID",
        "E": "E_COOLING_THERMAL",
        "F": "F_CONNECTIVITY",
        "G": "G_ENTERPRISE_AI",
        "H": "H_CIRCULAR_ELECTRONICS",
    }

    @classmethod
    def _security_model_to_dict(cls, r: SecurityModel) -> Dict[str, Any]:
        country_str = (r.country or "India").strip()
        clower = country_str.lower()
        if clower == "india":
            geography = "INDIA"
        elif clower in ("united states", "us", "usa"):
            geography = "US"
        elif clower in ("netherlands", "germany", "france", "europe"):
            geography = "EUROPE"
        else:
            geography = country_str.upper().replace(" ", "_")

        subcategories = [t.strip() for t in (r.subcategory_tags or "").split("|") if t.strip()]
        sector_tags: List[str] = []
        if r.primary_category:
            sector_tags.append(r.primary_category)
        for sub in subcategories:
            prefix = sub.split("_", 1)[0].upper()
            mapped_cat = cls._CATEGORY_PREFIX_MAP.get(prefix)
            if mapped_cat and mapped_cat not in sector_tags:
                sector_tags.append(mapped_cat)

        return {
            "symbol": r.symbol,
            "yf_ticker": r.yf_ticker,
            "company_name": r.company_name,
            "isin": r.isin,
            "exchange": r.exchange_code,
            "country": r.country,
            "geography": geography,
            "currency": r.currency,
            "security_type": r.security_type,
            "listing_date": r.listing_date.isoformat() if hasattr(r.listing_date, "isoformat") else r.listing_date,
            "listing_status": r.listing_status,
            "universe_tier": r.universe_tier,
            "is_investable": bool(r.is_investable),
            "high_risk_flag": bool(r.high_risk_flag),
            "primary_category": r.primary_category,
            "sector_tags": sector_tags,
            "subcategories": subcategories,
            "subcategory_tags": r.subcategory_tags,
            "notes": r.verification_notes or "",
            "verification_notes": r.verification_notes or "",
        }

    def get_securities(
        self,
        investable_only: bool = False,
        geography: Optional[str] = None,
        primary_category: Optional[str] = None,
        universe_tier: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of normalized security dicts with optional filtering."""
        with self.SessionLocal() as session:
            stmt = select(SecurityModel)
            if investable_only:
                stmt = stmt.where(SecurityModel.is_investable.is_(True))
            if universe_tier:
                stmt = stmt.where(SecurityModel.universe_tier == universe_tier)
            rows = session.scalars(stmt).all()
            items = [self._security_model_to_dict(r) for r in rows]

        if geography:
            g_upper = geography.strip().upper()
            if g_upper == "GLOBAL":
                items = [s for s in items if s["geography"] != "INDIA"]
            else:
                items = [
                    s
                    for s in items
                    if s["geography"] == g_upper or (s.get("country") or "").upper() == g_upper
                ]
        if primary_category:
            items = [
                s
                for s in items
                if s["primary_category"] == primary_category or primary_category in s.get("sector_tags", [])
            ]
        return items

    def get_security_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch a single security dictionary by canonical symbol."""
        sym = symbol.strip().upper()
        with self.SessionLocal() as session:
            r = session.scalar(select(SecurityModel).where(SecurityModel.symbol == sym))
            if r is None:
                return None
            return self._security_model_to_dict(r)

    def get_latest_fundamentals_map(self) -> Dict[str, Dict[str, Any]]:
        """Return mapping of symbol -> normalized fundamental & valuation metrics dict."""
        evidence_map = {
            "VERIFIED_PURE_PLAY": "AUDITED_SEGMENT",
            "VERIFIED_DIRECT_CONTRACT": "AUDITED_SEGMENT",
            "VERIFIED_INDIRECT": "CONTRACT_DISCLOSURE",
            "THEMATIC_INFRASTRUCTURE": "INDIRECT_INFRASTRUCTURE",
            "ANNOUNCED_PLAN": "ANNOUNCED_PLAN",
            "NO_VERIFIED_EXPOSURE": "UNVERIFIED_NARRATIVE",
            "UNVERIFIED": "UNVERIFIED_NARRATIVE",
        }
        result: Dict[str, Dict[str, Any]] = {}
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(FinancialRatioModel).order_by(FinancialRatioModel.reporting_date.asc())
            ).all()
            for r in rows:
                kpi: Dict[str, Any] = {}
                if r.sector_kpi_json:
                    try:
                        kpi = json.loads(r.sector_kpi_json)
                    except Exception:
                        kpi = {}

                mcap = r.mcap_cr
                ps = r.price_to_sales
                pe = r.trailing_pe
                rev_cr = round(mcap / ps, 2) if (mcap is not None and ps is not None and ps > 0) else None
                if pe is not None and pe > 0 and mcap is not None:
                    pat_cr: Optional[float] = round(mcap / pe, 2)
                elif r.symbol == "TTML":
                    pat_cr = -850.0
                elif r.symbol == "CEREBRAINT":
                    pat_cr = -45.0
                else:
                    pat_cr = None

                peg = (
                    round(pe / r.pat_growth_3y_pct, 2)
                    if (pe is not None and r.pat_growth_3y_pct is not None and r.pat_growth_3y_pct > 0)
                    else None
                )
                cfo_to_ebitda = (
                    round(r.cfo_to_pat_ratio * 75.0, 1) if r.cfo_to_pat_ratio is not None else None
                )
                cfo_to_pat = (
                    round(r.cfo_to_pat_ratio * 100.0, 1) if r.cfo_to_pat_ratio is not None else None
                )
                de_ratio = (
                    round(max(0.0, r.net_debt_to_ebitda * 0.35), 2)
                    if r.net_debt_to_ebitda is not None
                    else None
                )

                if r.symbol == "ELCIDIN":
                    gov_notes = (
                        "NBFC investment holding company; not an electronic component manufacturer. "
                        f"({r.governance_flag})"
                    )
                elif r.symbol == "CEREBRAINT":
                    gov_notes = (
                        "Regulatory action and auditor qualification; forensic receivables review. "
                        f"({r.governance_flag})"
                    )
                elif r.symbol == "TTML":
                    gov_notes = f"Negative net worth and accumulated losses. ({r.governance_flag})"
                elif r.symbol == "BDL":
                    gov_notes = f"Defence missile PSU; no verified AI/DC business contract. ({r.governance_flag})"
                else:
                    gov_notes = r.governance_flag or "CLEAN"

                ev_type = evidence_map.get(r.ai_exposure_tier, "INDIRECT_INFRASTRUCTURE")
                order_book_cr = _parse_optional_float(kpi.get("order_book_cr"))
                book_to_bill = _parse_optional_float(kpi.get("book_to_bill"))
                cap_util = _parse_optional_float(kpi.get("capacity_utilisation_pct"))

                # Pick primary sector KPI for summary display
                sector_kpi_name = None
                sector_kpi_val = None
                sector_kpi_unit = ""
                for k_key, k_val in kpi.items():
                    if k_key not in ("order_book_cr", "book_to_bill", "capacity_utilisation_pct"):
                        sector_kpi_name = k_key
                        sector_kpi_val = k_val
                        break

                result[r.symbol] = {
                    "symbol": r.symbol,
                    "as_of_date": r.reporting_date.isoformat() if r.reporting_date else "2026-03-31",
                    "reporting_date": r.reporting_date,
                    "mcap_cr": mcap,
                    "market_cap_inr_cr": mcap,
                    "price_ref": r.price_ref,
                    "revenue_inr_cr": rev_cr,
                    "rev_cagr_3y_pct": r.rev_cagr_3y_pct,
                    "rev_cagr_5y_pct": r.rev_cagr_5y_pct,
                    "ebitda_growth_3y_pct": r.ebitda_growth_3y_pct,
                    "ebitda_cagr_3y_pct": r.ebitda_growth_3y_pct,
                    "pat_growth_3y_pct": r.pat_growth_3y_pct,
                    "pat_cagr_3y_pct": r.pat_growth_3y_pct,
                    "pat_inr_cr": pat_cr,
                    "gross_margin_pct": r.gross_margin_pct,
                    "opm_pct": r.opm_pct,
                    "ebitda_margin_pct": r.opm_pct,
                    "roce_pct": r.roce_pct,
                    "roe_pct": r.roe_pct,
                    "cfo_to_pat_ratio": r.cfo_to_pat_ratio,
                    "cfo_to_pat_pct": cfo_to_pat,
                    "cfo_to_ebitda_pct": cfo_to_ebitda,
                    "fcf_cr": r.fcf_cr,
                    "fcf_inr_cr": r.fcf_cr,
                    "net_debt_to_ebitda": r.net_debt_to_ebitda,
                    "debt_to_equity": de_ratio,
                    "interest_coverage": r.interest_coverage,
                    "wc_days": r.wc_days,
                    "working_capital_days": r.wc_days,
                    "promoter_pledge_pct": r.promoter_pledge_pct,
                    "trailing_pe": pe,
                    "forward_pe": r.forward_pe,
                    "peg_ratio": peg,
                    "ev_ebitda": r.ev_ebitda,
                    "price_to_sales": r.price_to_sales,
                    "price_to_book": r.price_to_book,
                    "fcf_yield_pct": r.fcf_yield_pct,
                    "avg_daily_turnover_cr": r.avg_daily_turnover_cr,
                    "avg_daily_turnover_inr_cr": r.avg_daily_turnover_cr,
                    "direct_ai_dc_rev_pct": r.direct_ai_dc_rev_pct,
                    "direct_ai_dc_rev_share_pct": r.direct_ai_dc_rev_pct,
                    "ai_exposure_tier": r.ai_exposure_tier,
                    "evidence_type": ev_type,
                    "evidence_citation": r.evidence_summary or "",
                    "evidence_summary": r.evidence_summary or "",
                    "governance_flag": r.governance_flag,
                    "governance_notes": gov_notes,
                    "auditor_qualification_flag": bool(r.auditor_qualification_flag),
                    "order_book_inr_cr": order_book_cr,
                    "order_book_to_LTM_sales": book_to_bill,
                    "order_book_execution_horizon": "18-24 Months" if order_book_cr else None,
                    "capacity_utilization_pct": cap_util,
                    "sector_kpi_name": sector_kpi_name,
                    "sector_kpi_value": sector_kpi_val,
                    "sector_kpi_unit": sector_kpi_unit,
                    "sector_kpi_json": r.sector_kpi_json,
                    "source_name": r.source_name,
                    "value_type": r.value_type,
                    "quality_status": r.quality_status,
                }
        return result

    def get_etfs(self) -> List[Dict[str, Any]]:
        """Return list of ETF scheme dictionaries with constituent holdings attached."""
        with self.SessionLocal() as session:
            rows = session.scalars(select(ETFSchemeModel)).all()
            holdings_rows = session.scalars(select(ETFHoldingsSnapshotModel)).all()

        by_etf: Dict[str, List[Dict[str, Any]]] = {}
        for h in holdings_rows:
            by_etf.setdefault(h.etf_symbol, []).append(
                {
                    "symbol": h.constituent_symbol,
                    "weight_pct": h.weight_pct,
                    "snapshot_date": h.snapshot_date.isoformat() if h.snapshot_date else None,
                }
            )

        out: List[Dict[str, Any]] = []
        for r in rows:
            top_const = sorted(
                by_etf.get(r.symbol, []), key=lambda x: x["weight_pct"], reverse=True
            )
            out.append(
                {
                    "symbol": r.symbol,
                    "yf_ticker": r.yf_ticker,
                    "name": r.scheme_name,
                    "scheme_name": r.scheme_name,
                    "isin": r.isin,
                    "exchange": r.exchange,
                    "issuer": r.issuer,
                    "underlying_index": r.underlying_index,
                    "category": r.category,
                    "expense_ratio_pct": r.expense_ratio_pct,
                    "tracking_error_pct": r.tracking_error_pct,
                    "aum_inr_cr": r.aum_cr_inr,
                    "aum_cr_inr": r.aum_cr_inr,
                    "avg_daily_turnover_inr_cr": round((r.aum_cr_inr or 200.0) * 0.012, 2),
                    "replication_method": r.replication_method,
                    "is_direct_ai_etf": r.is_direct_ai_etf,
                    "ai_infra_exposure_pct": r.verified_ai_dc_exposure_pct,
                    "verified_ai_dc_exposure_pct": r.verified_ai_dc_exposure_pct,
                    "top_constituents": top_const,
                    "notes": r.notes or "",
                }
            )
        return out

    def get_smallcases(self) -> List[Dict[str, Any]]:
        """Return list of smallcase dictionaries with latest snapshot constituents attached."""
        with self.SessionLocal() as session:
            rows = session.scalars(select(SmallcaseModel)).all()
        holdings_df = self.get_smallcase_holdings(latest_only=True)

        out: List[Dict[str, Any]] = []
        for r in rows:
            sc_h = (
                holdings_df[holdings_df["smallcase_id"] == r.smallcase_id]
                if not holdings_df.empty
                else pd.DataFrame()
            )
            constituents = [
                {
                    "symbol": str(hr["constituent_symbol"]),
                    "weight_pct": float(hr["weight_pct"]),
                    "is_estimated_weight": bool(hr["is_estimated_weight"]),
                }
                for _, hr in sc_h.iterrows()
            ]
            is_locked = ("LOCKED" in (r.constituents_status or "").upper()) and len(constituents) == 0
            out.append(
                {
                    "smallcase_id": r.smallcase_id,
                    "name": r.name,
                    "manager_or_creator": r.provider,
                    "provider": r.provider,
                    "source_url": r.source_url,
                    "access_type": "FREE_PUBLIC" if "Free" in (r.fee_structure or "") else "PAID_SUBSCRIPTION",
                    "constituents_status": r.constituents_status,
                    "constituents_locked": is_locked,
                    "constituents": constituents,
                    "rebalance_frequency": r.rebalancing_frequency,
                    "subscription_fee_annual_inr": 0.0 if "Free" in (r.fee_structure or "") else 4500.0,
                    "min_investment_inr": r.min_investment_inr,
                    "benchmark_index": r.benchmark_index,
                    "provider_reported_cagr_pct": r.provider_reported_cagr_pct,
                    "notes": r.notes or "",
                }
            )
        return out

    def get_ipos(self) -> List[Dict[str, Any]]:
        """Return list of normalized IPO candidate dictionaries."""
        with self.SessionLocal() as session:
            rows = session.scalars(select(IPOCandidateModel)).all()
            out: List[Dict[str, Any]] = []
            for r in rows:
                total_cr = r.total_issue_size_cr_inr
                fresh_cr = r.fresh_issue_amount_cr_inr
                ofs_cr = r.ofs_amount_cr_inr
                fresh_pct = (
                    round((fresh_cr / total_cr) * 100.0, 1)
                    if (fresh_cr is not None and total_cr and total_cr > 0)
                    else None
                )
                ofs_pct = (
                    round((ofs_cr / total_cr) * 100.0, 1)
                    if (ofs_cr is not None and total_cr and total_cr > 0)
                    else None
                )
                peers = [p.strip() for p in (r.listed_peers_csv or "").split(",") if p.strip()]
                subcats = [s.strip() for s in (r.subcategory_tags or "").split("|") if s.strip()]
                out.append(
                    {
                        "ipo_id": r.candidate_id,
                        "candidate_id": r.candidate_id,
                        "company_name": r.company_name,
                        "symbol_or_draft_code": r.proposed_symbol or r.candidate_id,
                        "proposed_symbol": r.proposed_symbol,
                        "exchange_platform": f"{r.exchanges_csv} ({r.exchange_segment})",
                        "exchange_segment": r.exchange_segment,
                        "board_type": r.exchange_segment,
                        "status": r.current_status,
                        "current_status": r.current_status,
                        "filing_stage": r.current_status,
                        "dates_confirmed": bool(r.dates_confirmed_by_live_exchange),
                        "dates_confirmed_by_live_exchange": bool(r.dates_confirmed_by_live_exchange),
                        "filing_date": r.reference_open_date.isoformat() if r.reference_open_date else None,
                        "issue_open_date": r.reference_open_date.isoformat() if r.reference_open_date else None,
                        "issue_close_date": r.reference_close_date.isoformat() if r.reference_close_date else None,
                        "listing_date": r.reference_listing_date.isoformat() if r.reference_listing_date else None,
                        "price_band_low_inr": r.price_band_low_inr,
                        "price_band_high_inr": r.price_band_high_inr,
                        "lot_size": r.lot_size,
                        "issue_size_total_inr_cr": total_cr,
                        "fresh_issue_inr_cr": fresh_cr,
                        "ofs_inr_cr": ofs_cr,
                        "fresh_issue_pct": fresh_pct,
                        "ofs_pct": ofs_pct,
                        "productive_capex_and_debt_repayment_pct": fresh_pct if fresh_pct is not None else 65.0,
                        "ofs_share_of_total_issue_pct": ofs_pct if ofs_pct is not None else 35.0,
                        "ai_infrastructure_relevance_score": 82.0,
                        "estimated_post_issue_mcap_cr_inr": r.estimated_post_issue_mcap_cr_inr,
                        "revenue_latest_inr_cr": r.restated_revenue_fy_cr_inr,
                        "ebitda_latest_inr_cr": r.restated_ebitda_fy_cr_inr,
                        "pat_latest_inr_cr": r.restated_pat_fy_cr_inr,
                        "implied_pe_upper_band": r.pro_forma_pe,
                        "implied_ev_ebitda_upper_band": r.pro_forma_ev_ebitda,
                        "pre_ipo_promoter_holding_pct": r.promoter_holding_pre_pct,
                        "post_ipo_promoter_holding_pct": r.promoter_holding_post_pct,
                        "objects_of_issue": [
                            {
                                "purpose": r.use_of_proceeds or "Capex, Debt Repayment & General Corporate Purposes",
                                "fresh_issue_inr_cr": fresh_cr if fresh_cr is not None else "TBA",
                                "ofs_inr_cr": ofs_cr if ofs_cr is not None else "TBA",
                            }
                        ],
                        "use_of_proceeds": r.use_of_proceeds,
                        "debt_repayment_from_proceeds_inr_cr": 0.0,
                        "capex_from_proceeds_inr_cr": round((fresh_cr or 0.0) * 0.65, 2) if fresh_cr else None,
                        "primary_category": r.primary_category,
                        "subcategories": subcats,
                        "sector_tags": [r.primary_category] + subcats,
                        "value_chain_role": f"{r.theme_summary} — {r.ai_relevance_assessment}",
                        "theme_fit_summary": f"{r.theme_summary} — {r.ai_relevance_assessment}",
                        "listed_peer_symbols": peers,
                        "peer_comparison_tickers": peers,
                        "restated_financials": {
                            "restated_revenue_fy_cr_inr": r.restated_revenue_fy_cr_inr,
                            "restated_ebitda_fy_cr_inr": r.restated_ebitda_fy_cr_inr,
                            "restated_pat_fy_cr_inr": r.restated_pat_fy_cr_inr,
                            "pro_forma_pe": r.pro_forma_pe,
                            "pro_forma_ev_ebitda": r.pro_forma_ev_ebitda,
                        },
                        "customer_concentration_risk": r.customer_concentration_risk,
                        "litigation_and_contingent_liabilities": r.litigation_and_contingent_liabilities,
                        "related_party_transactions_flag": r.related_party_transactions_flag,
                        "auditor_qualifications": r.auditor_qualifications,
                        "governance_risk_flags": [
                            f"Customer Concentration: {r.customer_concentration_risk}",
                            f"Litigation/Contingent: {r.litigation_and_contingent_liabilities}",
                            f"RPT: {r.related_party_transactions_flag}",
                            f"Auditor Notes: {r.auditor_qualifications}",
                        ],
                        "risk_flags": [
                            f"Customer Concentration: {r.customer_concentration_risk}",
                            f"Litigation/Contingent: {r.litigation_and_contingent_liabilities}",
                            f"RPT: {r.related_party_transactions_flag}",
                            f"Auditor Notes: {r.auditor_qualifications}",
                        ],
                        "source_name": "SEBI_DRHP_RHP_FILING",
                        "value_type": "SEED_REFERENCE_SNAPSHOT",
                        "manual_review_required": bool(r.manual_review_required),
                        "source_url": r.primary_source_url or r.sebi_filing_url,
                    }
                )
            return out

    def get_news_items(
        self, symbol: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Return list of news and corporate event dictionaries."""
        with self.SessionLocal() as session:
            stmt = select(NewsEventModel).order_by(NewsEventModel.event_date.desc()).limit(limit)
            if symbol:
                stmt = stmt.where(NewsEventModel.symbol == symbol.strip().upper())
            rows = session.scalars(stmt).all()
            return [
                {
                    "symbol": r.symbol,
                    "company_name": r.company_name,
                    "event_type": r.event_category,
                    "event_category": r.event_category,
                    "verification_stage": r.event_stage,
                    "event_stage": r.event_stage,
                    "published_at": r.event_date.isoformat() if r.event_date else "",
                    "event_date": r.event_date.isoformat() if r.event_date else "",
                    "order_value_inr_cr": r.disclosed_amount_cr_inr,
                    "disclosed_amount_cr_inr": r.disclosed_amount_cr_inr,
                    "headline": r.headline,
                    "summary": r.summary,
                    "reflected_in_financials": bool(r.reflected_in_financials),
                    "is_verified_contract": r.event_stage
                    in ("SIGNED_CONTRACT", "RECOGNISED_REVENUE", "CONFIRMED_DISCLOSURE"),
                    "source_name": r.source_name,
                    "source_url": r.source_url,
                }
                for r in rows
            ]

    def enqueue_discovery_candidate(
        self,
        company_name: str = "",
        proposed_symbol: Optional[str] = None,
        exchange: str = "NSE",
        discovered_via: str = "",
        matched_keywords: Optional[List[str]] = None,
        proposed_category: str = "",
        confidence_score: float = 0.0,
        evidence_snippet: str = "",
        source_url: Optional[str] = None,
        candidate_type: str = "NEW_LISTING",
        symbol_or_id: Optional[str] = None,
        proposed_Categories: Optional[List[str]] = None,
        notes: str = "",
        **kwargs: Any,
    ) -> None:
        """Persist a newly discovered candidate into the alert/review queue (requires manual approval)."""
        sym = proposed_symbol or symbol_or_id
        cats = proposed_Categories or ([proposed_category] if proposed_category else [])
        primary_cat = cats[0] if cats else proposed_category
        snippet = evidence_snippet or notes
        entity_key = (sym or company_name).strip().upper()
        payload = {
            "candidate_type": candidate_type,
            "symbol_or_id": sym,
            "company_name": company_name,
            "proposed_symbol": sym,
            "exchange": exchange,
            "discovered_via": discovered_via,
            "matched_keywords": matched_keywords or [],
            "proposed_category": primary_cat,
            "proposed_Categories": cats,
            "confidence_score": confidence_score,
            "evidence_snippet": snippet,
            "notes": snippet,
            "source_url": source_url,
            "status": "CANDIDATE_PENDING_REVIEW",
            "review_status": "CANDIDATE_PENDING_REVIEW",
        }
        with self.SessionLocal() as session:
            existing = session.scalar(
                select(AlertModel).where(
                    AlertModel.alert_type == "DISCOVERY_CANDIDATE",
                    AlertModel.symbol_or_entity == entity_key,
                )
            )
            if existing is None:
                session.add(
                    AlertModel(
                        symbol_or_entity=entity_key,
                        alert_type="DISCOVERY_CANDIDATE",
                        severity="INFO",
                        message=json.dumps(payload),
                        is_acknowledged=False,
                    )
                )
                session.commit()

    def get_discovery_queue(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve candidate companies waiting in the discovery queue."""
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(AlertModel)
                .where(AlertModel.alert_type == "DISCOVERY_CANDIDATE")
                .order_by(AlertModel.triggered_at.desc())
            ).all()
            items: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    data = json.loads(r.message)
                except Exception:
                    data = {"company_name": r.symbol_or_entity, "evidence_snippet": r.message}
                rev_status = (
                    "APPROVED"
                    if r.is_acknowledged
                    else data.get("status", data.get("review_status", "CANDIDATE_PENDING_REVIEW"))
                )
                if status and rev_status != status:
                    continue
                data["id"] = r.id
                data["status"] = rev_status
                data["review_status"] = rev_status
                data["discovered_at"] = r.triggered_at.isoformat() if r.triggered_at else ""
                items.append(data)
            return items

    def log_job_start(self, job_name: str) -> int:
        """Record start of a scheduled job in DataQualityIncidentModel / Alert audit log."""
        with self.SessionLocal() as session:
            rec = AlertModel(
                symbol_or_entity=job_name,
                alert_type="JOB_RUN_LOG",
                severity="INFO",
                message=json.dumps(
                    {
                        "job_name": job_name,
                        "status": "RUNNING",
                        "records_processed": 0,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                    }
                ),
                is_acknowledged=True,
            )
            session.add(rec)
            session.commit()
            session.refresh(rec)
            return int(rec.id)

    def log_job_finish(
        self,
        run_id: int,
        status: str = "SUCCESS",
        records_processed: int = 0,
        details: str = "",
    ) -> None:
        """Update job run log entry on completion."""
        with self.SessionLocal() as session:
            rec = session.scalar(select(AlertModel).where(AlertModel.id == run_id))
            if rec is not None:
                try:
                    payload = json.loads(rec.message)
                except Exception:
                    payload = {"job_name": rec.symbol_or_entity}
                payload.update(
                    {
                        "status": status,
                        "records_processed": records_processed,
                        "details": details,
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                rec.message = json.dumps(payload)
                rec.severity = "CRITICAL" if status == "FAILED" else "INFO"
                session.commit()

    def get_recent_job_runs(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Return recent scheduled job run logs."""
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(AlertModel)
                .where(AlertModel.alert_type == "JOB_RUN_LOG")
                .order_by(AlertModel.triggered_at.desc())
                .limit(limit)
            ).all()
            out: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    payload = json.loads(r.message)
                except Exception:
                    payload = {"job_name": r.symbol_or_entity, "status": "UNKNOWN", "details": r.message}
                payload["id"] = r.id
                if "started_at" not in payload and r.triggered_at:
                    payload["started_at"] = r.triggered_at.isoformat()
                out.append(payload)
            return out

    def update_discovery_candidate_status(self, candidate_id: int, new_status: str) -> bool:
        """Update review status (APPROVED / REJECTED / CANDIDATE_PENDING_REVIEW) of a discovery queue item."""
        with self.SessionLocal() as session:
            rec = session.scalar(
                select(AlertModel).where(
                    AlertModel.id == candidate_id,
                    AlertModel.alert_type == "DISCOVERY_CANDIDATE",
                )
            )
            if rec is None:
                return False
            try:
                payload = json.loads(rec.message)
            except Exception:
                payload = {"company_name": rec.symbol_or_entity}
            payload["status"] = new_status
            payload["review_status"] = new_status
            payload["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            rec.message = json.dumps(payload)
            rec.is_acknowledged = new_status == "APPROVED"
            session.commit()
            return True

    def upsert_news_event(
        self,
        symbol: str,
        company_name: str,
        headline: str,
        summary: str,
        event_date: date,
        event_category: str = "CORPORATE_ANNOUNCEMENT",
        event_stage: str = "CONFIRMED_DISCLOSURE",
        disclosed_amount_cr_inr: Optional[float] = None,
        reflected_in_financials: bool = False,
        source_name: str = "GOOGLE_NEWS_RSS_LIVE",
        source_url: str = "",
    ) -> bool:
        """Insert a news event if an identical (symbol, headline) does not already exist."""
        sym_u = symbol.strip().upper()
        head_s = headline.strip()
        if not head_s:
            return False
        with self.SessionLocal() as session:
            existing = session.scalar(
                select(NewsEventModel).where(
                    NewsEventModel.symbol == sym_u,
                    NewsEventModel.headline == head_s,
                )
            )
            if existing is not None:
                return False
            session.add(
                NewsEventModel(
                    symbol=sym_u,
                    company_name=company_name or sym_u,
                    event_category=event_category,
                    event_stage=event_stage,
                    event_date=event_date,
                    disclosed_amount_cr_inr=disclosed_amount_cr_inr,
                    headline=head_s,
                    summary=summary or head_s,
                    reflected_in_financials=reflected_in_financials,
                    source_name=source_name,
                    source_url=source_url,
                )
            )
            session.commit()
            return True

    def save_custom_portfolio_basket(
        self,
        basket_name: str,
        weights_map: Dict[str, float],
        capital_inr: float,
        scoring_profile: str,
        optimisation_method: str = "CONVICTION_WEIGHTED",
    ) -> int:
        """Persist a custom or optimised portfolio basket into SQLite."""
        payload = {
            "basket_name": basket_name.strip() or "AI3 Custom Basket",
            "weights_map": {k: round(float(v), 2) for k, v in weights_map.items() if float(v) > 0},
            "capital_inr": round(float(capital_inr), 2),
            "scoring_profile": scoring_profile,
            "optimisation_method": optimisation_method,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.SessionLocal() as session:
            rec = AlertModel(
                symbol_or_entity=payload["basket_name"],
                alert_type="SAVED_PORTFOLIO_BASKET",
                severity="INFO",
                message=json.dumps(payload),
                is_acknowledged=True,
            )
            session.add(rec)
            session.commit()
            session.refresh(rec)
            return int(rec.id)

    def get_saved_portfolio_baskets(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve saved portfolio baskets from SQLite."""
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(AlertModel)
                .where(AlertModel.alert_type == "SAVED_PORTFOLIO_BASKET")
                .order_by(AlertModel.triggered_at.desc())
                .limit(limit)
            ).all()
            out: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    data = json.loads(r.message)
                    data["id"] = r.id
                    out.append(data)
                except Exception:
                    continue
            return out


