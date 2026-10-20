"""SQLAlchemy 2.x ORM models implementing all 27 tables specified in Section 22 + Alerts."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# 1. Exchanges
class ExchangeModel(Base):
    __tablename__ = "exchanges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[str] = mapped_column(String(60), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    timezone_str: Mapped[str] = mapped_column(String(40), default="Asia/Kolkata")
    access_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# 2. Securities
class SecurityModel(Base):
    __tablename__ = "securities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    yf_ticker: Mapped[str] = mapped_column(String(40), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    isin: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    exchange_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(60), default="India")
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    security_type: Mapped[str] = mapped_column(String(30), default="EQUITY")
    listing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    listing_status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    universe_tier: Mapped[str] = mapped_column(String(40), default="INVESTABLE_INDIA")
    is_investable: Mapped[bool] = mapped_column(Boolean, default=True)
    high_risk_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    primary_category: Mapped[str] = mapped_column(String(60), nullable=False)
    subcategory_tags: Mapped[str] = mapped_column(String(255), default="")
    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)


# 3. Company Aliases
class CompanyAliasModel(Base):
    __tablename__ = "company_aliases"
    __table_args__ = (UniqueConstraint("security_symbol", "alias", name="uq_sec_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    security_symbol: Mapped[str] = mapped_column(
        String(32), ForeignKey("securities.symbol"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    alias_type: Mapped[str] = mapped_column(String(40), default="EXCHANGE_TICKER")
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


# 4. Security Listing History
class SecurityListingHistoryModel(Base):
    __tablename__ = "security_listing_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    isin: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    old_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    new_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 5. Price History
class PriceHistoryModel(Base):
    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("symbol", "trade_date", name="uq_price_sym_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    high_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    low_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
    adj_close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    source: Mapped[str] = mapped_column(String(60), default="YFINANCE")
    value_type: Mapped[str] = mapped_column(String(40), default="REPORTED")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 6. Corporate Actions
class CorporateActionModel(Base):
    __tablename__ = "corporate_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    ex_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)  # SPLIT, BONUS, DIVIDEND, MERGER
    ratio_numerator: Mapped[float] = mapped_column(Float, default=1.0)
    ratio_denominator: Mapped[float] = mapped_column(Float, default=1.0)
    cash_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="EXCHANGE_FILING")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# 7. Financial Statements
class FinancialStatementModel(Base):
    __tablename__ = "financial_statements"
    __table_args__ = (
        UniqueConstraint("symbol", "period_end", "statement_type", name="uq_fin_stmt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    statement_type: Mapped[str] = mapped_column(String(30), default="ANNUAL_CONSOLIDATED")
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    unit: Mapped[str] = mapped_column(String(20), default="CRORE")
    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ebitda: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ebit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cfo: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    capex: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    free_cash_flow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_debt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cash_and_equivalents: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_worth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    value_type: Mapped[str] = mapped_column(String(40), default="REPORTED")
    quality_status: Mapped[str] = mapped_column(String(40), default="VERIFIED")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 8. Financial Ratios & Sector KPIs
class FinancialRatioModel(Base):
    __tablename__ = "financial_ratios"
    __table_args__ = (UniqueConstraint("symbol", "reporting_date", name="uq_fin_ratio_sym_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reporting_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    mcap_cr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_ref: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rev_cagr_3y_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rev_cagr_5y_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ebitda_growth_3y_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pat_growth_3y_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gross_margin_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opm_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    roce_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    roe_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cfo_to_pat_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fcf_cr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_debt_to_ebitda: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    interest_coverage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wc_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    promoter_pledge_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trailing_pe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    forward_pe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ev_ebitda: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_to_sales: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_to_book: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fcf_yield_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_daily_turnover_cr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    direct_ai_dc_rev_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_exposure_tier: Mapped[str] = mapped_column(String(40), default="UNVERIFIED")
    governance_flag: Mapped[str] = mapped_column(String(80), default="NONE")
    auditor_qualification_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    sector_kpi_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False)
    value_type: Mapped[str] = mapped_column(String(40), default="REPORTED")
    quality_status: Mapped[str] = mapped_column(String(40), default="VERIFIED")
    source_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 9. ETF Schemes
class ETFSchemeModel(Base):
    __tablename__ = "etf_schemes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    yf_ticker: Mapped[str] = mapped_column(String(40), nullable=False)
    scheme_name: Mapped[str] = mapped_column(String(200), nullable=False)
    isin: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), default="NSE")
    issuer: Mapped[str] = mapped_column(String(120), nullable=False)
    underlying_index: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    expense_ratio_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tracking_error_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    aum_cr_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    replication_method: Mapped[str] = mapped_column(String(40), default="FULL_REPLICATION")
    is_direct_ai_etf: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_ai_dc_exposure_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sector_allocation_json: Mapped[str] = mapped_column(Text, default="{}")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# 10. ETF Holdings Snapshots (Append-only dated snapshots — never overwrite history)
class ETFHoldingsSnapshotModel(Base):
    __tablename__ = "etf_holdings_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "etf_symbol", "snapshot_date", "constituent_symbol", name="uq_etf_snap_holding"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    etf_symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    constituent_symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    weight_pct: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(80), default="AMC_FACTSHEET_SEED")
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 11. Smallcases
class SmallcaseModel(Base):
    __tablename__ = "smallcases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    smallcase_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rebalancing_frequency: Mapped[str] = mapped_column(String(40), default="QUARTERLY")
    fee_structure: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    min_investment_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    benchmark_index: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    constituents_status: Mapped[str] = mapped_column(String(60), nullable=False)
    provider_reported_cagr_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# 12. Smallcase Holdings Snapshots (Append-only dated snapshots — never overwrite history)
class SmallcaseHoldingsSnapshotModel(Base):
    __tablename__ = "smallcase_holdings_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "smallcase_id", "snapshot_date", "constituent_symbol", name="uq_sc_snap_holding"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    smallcase_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    constituent_symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    weight_pct: Mapped[float] = mapped_column(Float, nullable=False)
    is_estimated_weight: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(80), default="PUBLIC_REFERENCE_OR_CSV")
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 13. IPO Candidates
class IPOCandidateModel(Base):
    __tablename__ = "ipo_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    proposed_symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    exchange_segment: Mapped[str] = mapped_column(String(30), default="MAINBOARD")
    exchanges_csv: Mapped[str] = mapped_column(String(40), default="NSE,BSE")
    primary_category: Mapped[str] = mapped_column(String(60), nullable=False)
    subcategory_tags: Mapped[str] = mapped_column(String(120), default="")
    theme_summary: Mapped[str] = mapped_column(Text, nullable=False)
    current_status: Mapped[str] = mapped_column(String(60), nullable=False)
    dates_confirmed_by_live_exchange: Mapped[bool] = mapped_column(Boolean, default=False)
    reference_open_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    reference_close_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    reference_allotment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    reference_listing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    price_band_low_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_band_high_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lot_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fresh_issue_shares_cr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fresh_issue_amount_cr_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ofs_amount_cr_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_issue_size_cr_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_post_issue_mcap_cr_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    restated_revenue_fy_cr_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    restated_ebitda_fy_cr_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    restated_pat_fy_cr_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pro_forma_pe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pro_forma_ev_ebitda: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    promoter_holding_pre_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    promoter_holding_post_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    use_of_proceeds: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    listed_peers_csv: Mapped[str] = mapped_column(String(255), default="")
    customer_concentration_risk: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    litigation_and_contingent_liabilities: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    related_party_transactions_flag: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auditor_qualifications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    primary_source_url: Mapped[str] = mapped_column(String(255), nullable=False)
    sebi_filing_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ai_relevance_assessment: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)


# 14. IPO Documents
class IPODocumentModel(Base):
    __tablename__ = "ipo_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(40), nullable=False)  # DRHP, UDRHP, RHP, ADDENDUM
    filing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    source_url: Mapped[str] = mapped_column(String(255), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(40), default="MANUAL_REVIEW_REQUIRED")
    extracted_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 15. IPO Event History
class IPOEventHistoryModel(Base):
    __tablename__ = "ipo_event_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    old_status: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    new_status: Mapped[str] = mapped_column(String(60), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 16. Company-Sector Mappings
class CompanySectorMappingModel(Base):
    __tablename__ = "company_sector_mappings"
    __table_args__ = (
        UniqueConstraint("symbol", "category_code", "subcategory_id", name="uq_comp_sec_map"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False)
    subcategory_id: Mapped[str] = mapped_column(String(20), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence_level: Mapped[str] = mapped_column(String(20), default="VERIFIED")


# 17. Business-Exposure Evidence
class BusinessExposureEvidenceModel(Base):
    __tablename__ = "business_exposure_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_stage: Mapped[str] = mapped_column(String(50), default="RECOGNISED_REVENUE")
    disclosed_rev_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_document: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reporting_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    verified_by_human: Mapped[bool] = mapped_column(Boolean, default=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 18. News Events
class NewsEventModel(Base):
    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    event_category: Mapped[str] = mapped_column(String(60), nullable=False)
    event_stage: Mapped[str] = mapped_column(String(50), nullable=False)  # ANNOUNCED_PLAN, SIGNED_CONTRACT, COMPLETED_PROJECT, RECOGNISED_REVENUE
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    disclosed_amount_cr_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    headline: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reflected_in_financials: Mapped[bool] = mapped_column(Boolean, default=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 19. Research Scores
class ResearchScoreModel(Base):
    __tablename__ = "research_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    profile_name: Mapped[str] = mapped_column(String(80), nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(30), default="v1.0.0")
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    business_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    growth_earnings_score: Mapped[float] = mapped_column(Float, nullable=False)
    valuation_score: Mapped[float] = mapped_column(Float, nullable=False)
    balance_sheet_score: Mapped[float] = mapped_column(Float, nullable=False)
    technical_momentum_score: Mapped[float] = mapped_column(Float, nullable=False)
    verified_exposure_score: Mapped[float] = mapped_column(Float, nullable=False)
    data_confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    missing_metrics_json: Mapped[str] = mapped_column(Text, default="[]")
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 20. Score Methodology Versions
class ScoreMethodologyVersionModel(Base):
    __tablename__ = "score_methodology_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_tag: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    profile_name: Mapped[str] = mapped_column(String(80), nullable=False)
    weights_json: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 21. Value-Alternative Comparisons
class ValueAlternativeComparisonModel(Base):
    __tablename__ = "value_alternative_comparisons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    alternative_symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    value_advantage_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(30), default="MEDIUM")
    reason_summary: Mapped[str] = mapped_column(Text, nullable=False)
    tradeoff_summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_gaps: Mapped[str] = mapped_column(Text, nullable=False)
    invalidation_triggers: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 22. User Baskets
class UserBasketModel(Base):
    __tablename__ = "user_baskets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    basket_name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    theme_category: Mapped[str] = mapped_column(String(80), default="CUSTOM")
    benchmark_symbol: Mapped[str] = mapped_column(String(32), default="MONIFTY500")
    max_single_stock_pct: Mapped[float] = mapped_column(Float, default=15.0)
    max_sector_pct: Mapped[float] = mapped_column(Float, default=40.0)
    min_daily_turnover_cr: Mapped[float] = mapped_column(Float, default=5.0)
    max_net_debt_ebitda: Mapped[float] = mapped_column(Float, default=3.5)
    monthly_sip_inr: Mapped[float] = mapped_column(Float, default=25000.0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)


# 23. Basket Holdings
class BasketHoldingModel(Base):
    __tablename__ = "basket_holdings"
    __table_args__ = (UniqueConstraint("basket_name", "symbol", name="uq_basket_sym"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    basket_name: Mapped[str] = mapped_column(
        String(120), ForeignKey("user_baskets.basket_name"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), default="EQUITY")
    target_weight_pct: Mapped[float] = mapped_column(Float, nullable=False)
    avg_buy_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 24. Backtest Runs
class BacktestRunModel(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_name: Mapped[str] = mapped_column(String(120), nullable=False)
    basket_or_strategy: Mapped[str] = mapped_column(String(120), nullable=False)
    benchmark_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    rebalance_frequency: Mapped[str] = mapped_column(String(30), default="QUARTERLY")
    transaction_cost_bps: Mapped[float] = mapped_column(Float, default=25.0)
    slippage_bps: Mapped[float] = mapped_column(Float, default=15.0)
    signal_delay_days: Mapped[int] = mapped_column(Integer, default=1)
    cagr_pct: Mapped[float] = mapped_column(Float, nullable=False)
    volatility_pct: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False)
    sharpe_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    sortino_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    calmar_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    turnover_pct: Mapped[float] = mapped_column(Float, nullable=False)
    hit_rate_pct: Mapped[float] = mapped_column(Float, nullable=False)
    benchmark_excess_cagr_pct: Mapped[float] = mapped_column(Float, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 25. Data-Quality Incidents & New Listing Queue
class DataQualityIncidentModel(Base):
    __tablename__ = "data_quality_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol_or_entity: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    incident_type: Mapped[str] = mapped_column(String(60), nullable=False)  # STALE_DATA, SOURCE_CONFLICT, MISSING_METRIC, NEW_LISTING_REVIEW, REJECTED_CANDIDATE
    severity: Mapped[str] = mapped_column(String(20), default="WARNING")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(40), default="OPEN")
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 26. AI Model Outputs
class AIModelOutputModel(Base):
    __tablename__ = "ai_model_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(60), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    validated_json: Mapped[str] = mapped_column(Text, nullable=False)
    needs_verification: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 27. Source Citations
class SourceCitationModel(Base):
    __tablename__ = "source_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    document_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    page_or_section: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    reporting_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)


# 28. Alerts (Section 24)
class AlertModel(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol_or_entity: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
