"""Pydantic v2 schemas for strict data validation, provenance, and AI output verification."""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class ValueType(str, Enum):
    REPORTED = "REPORTED"
    CALCULATED = "CALCULATED"
    ESTIMATED = "ESTIMATED"
    SEED_REFERENCE_SNAPSHOT = "SEED_REFERENCE_SNAPSHOT"
    SYNTHETIC_SAMPLE = "SYNTHETIC_SAMPLE"


class DataQualityStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PROVISIONAL = "PROVISIONAL"
    STALE = "STALE"
    MISSING = "MISSING"
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"
    UNVERIFIED_NEEDS_REVIEW = "UNVERIFIED_NEEDS_REVIEW"


classIPOStatus = Enum


class IPOStatus(str, Enum):
    DRHP_FILED = "DRHP_FILED"
    DRHP_FILED_SEBI_OBSERVATION = "DRHP_FILED_SEBI_OBSERVATION"
    UDRHP_FILED = "UDRHP_FILED"
    RHP_FILED = "RHP_FILED"
    RHP_ADDENDUM_FILED = "RHP_ADDENDUM_FILED"
    RHP_REFERENCE_NEEDS_LIVE_CHECK = "RHP_REFERENCE_NEEDS_LIVE_CHECK"
    RHP_REFERENCE_TIMETABLE_UNCONFIRMED = "RHP_REFERENCE_TIMETABLE_UNCONFIRMED"
    UPCOMING = "UPCOMING"
    UPCOMING_CONFIRMED = "UPCOMING_CONFIRMED"
    OPEN = "OPEN"
    OPEN_FOR_BIDDING = "OPEN_FOR_BIDDING"
    CLOSED = "CLOSED"
    ALLOTMENT_PENDING = "ALLOTMENT_PENDING"
    LISTED = "LISTED"
    POSTPONED = "POSTPONED"
    WITHDRAWN = "WITHDRAWN"
    POSTPONED_OR_WITHDRAWN = "POSTPONED_OR_WITHDRAWN"


class ListingStatus(str, Enum):
    ACTIVE = "ACTIVE"
    NEWLY_LISTED = "NEWLY_LISTED"
    ILLIQUID_HIGH_RISK = "ILLIQUID_HIGH_RISK"
    SUSPENDED_OR_DISTRESSED = "SUSPENDED_OR_DISTRESSED"
    DELISTED = "DELISTED"
    UNVERIFIED_TICKER = "UNVERIFIED_TICKER"
    CANDIDATE_PENDING_REVIEW = "CANDIDATE_PENDING_REVIEW"


class UniverseTier(str, Enum):
    CORE_INDIA = "CORE_INDIA"
    INVESTABLE_INDIA = "INVESTABLE_INDIA"
    HIGH_RISK_RESEARCH = "HIGH_RISK_RESEARCH"
    GLOBAL_BENCHMARK = "GLOBAL_BENCHMARK"
    DISCOVERY_QUEUE = "DISCOVERY_QUEUE"


class EvidenceType(str, Enum):
    AUDITED_SEGMENT = "AUDITED_SEGMENT"
    CONTRACT_DISCLOSURE = "CONTRACT_DISCLOSURE"
    INDIRECT_INFRASTRUCTURE = "INDIRECT_INFRASTRUCTURE"
    ANNOUNCED_PLAN = "ANNOUNCED_PLAN"
    PRESS_RELEASE_ONLY = "PRESS_RELEASE_ONLY"
    UNVERIFIED_NARRATIVE = "UNVERIFIED_NARRATIVE"
    VERIFIED_REALISED_REVENUE = "AUDITED_SEGMENT"
    SIGNED_ORDER_BOOK_CONTRACT = "CONTRACT_DISCLOSURE"


class ScoringProfile(str, Enum):
    DEFAULT_100PT = "DEFAULT_100PT"
    CONSERVATIVE_QUALITY = "CONSERVATIVE_QUALITY"
    BALANCED_GARP = "BALANCED_GARP"
    HIGH_GROWTH_INFRA = "HIGH_GROWTH_INFRA"
    SMALL_CAP_SUPPLIERS = "SMALL_CAP_SUPPLIERS"
    CIRCULAR_ECONOMY_FOCUS = "CIRCULAR_ECONOMY_FOCUS"
    VALUE_CONTRARIAN = "VALUE_CONTRARIAN"
    LOW_VOLATILITY_DEFENSIVE = "LOW_VOLATILITY_DEFENSIVE"
    IPO_NEW_LISTING = "IPO_NEW_LISTING"


class OptimisationMethod(str, Enum):
    EQUAL_WEIGHT = "EQUAL_WEIGHT"
    CONVICTION_WEIGHT = "CONVICTION_WEIGHT"
    INVERSE_VOLATILITY = "INVERSE_VOLATILITY"
    MINIMUM_VARIANCE = "MINIMUM_VARIANCE"
    MAXIMUM_SHARPE = "MAXIMUM_SHARPE"
    HRP = "HRP"
    BLACK_LITTERMAN = "BLACK_LITTERMAN"
    CORE_SATELLITE = "CORE_SATELLITE"


class RiskFlagSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    CRITICAL_BLOCK = "CRITICAL"


class TrackedValue(BaseModel):
    """Wraps any financial metric with full provenance per Section 18 requirements."""

    metric_name: str
    value: Optional[float] = None
    unit: str = "RATIO"
    currency: str = "INR"
    source: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reporting_date: Optional[date] = None
    value_type: ValueType = ValueType.REPORTED
    quality_status: DataQualityStatus = DataQualityStatus.VERIFIED
    source_url: Optional[str] = None
    document_id: Optional[str] = None
    transformation_applied: Optional[str] = None

    @property
    def is_missing(self) -> bool:
        return self.value is None

    def is_stale(self, max_age_days: int, reference_date: Optional[date] = None) -> bool:
        ref = reference_date or date.today()
        if self.reporting_date is not None:
            return (ref - self.reporting_date).days > max_age_days
        return (ref - self.retrieved_at.date()).days > max_age_days


class SecurityRecordSchema(BaseModel):
    """Validated security master entry."""

    symbol: str
    yf_ticker: str
    company_name: str
    isin: str
    exchange: str
    country: str = "India"
    currency: str = "INR"
    security_type: str = "EQUITY"
    listing_date: Optional[date] = None
    listing_status: str = "ACTIVE"
    universe_tier: str = "INVESTABLE_INDIA"
    is_investable: bool = True
    high_risk_flag: bool = False
    primary_category: str
    subcategory_tags: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)
    verification_notes: str = ""

    @field_validator("symbol")
    @classmethod
    def validate_symbol_not_company_name(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned or " " in cleaned or len(cleaned) > 20:
            raise ValueError(
                f"Invalid ticker symbol '{v}'. Never use a company name as a substitute for a verified ticker."
            )
        return cleaned

    @model_validator(mode="after")
    def enforce_investability_rules(self) -> "SecurityRecordSchema":
        if self.high_risk_flag or self.universe_tier == "HIGH_RISK_RESEARCH":
            self.is_investable = False
        if self.listing_status not in ("ACTIVE",):
            self.is_investable = False
        if "UNVERIFIED" in self.isin.upper():
            self.is_investable = False
            self.high_risk_flag = True
        return self


class IPOCandidateSchema(BaseModel):
    """Validated IPO pipeline record with anti-fabrication invariants."""

    candidate_id: str
    company_name: str
    proposed_symbol: Optional[str] = None
    exchange_segment: str = "MAINBOARD"
    exchanges: List[str] = Field(default_factory=lambda: ["NSE", "BSE"])
    primary_category: str
    subcategory_tags: List[str] = Field(default_factory=list)
    theme_summary: str
    current_status: IPOStatus
    dates_confirmed_by_live_exchange: bool = False
    reference_open_date: Optional[date] = None
    reference_close_date: Optional[date] = None
    reference_allotment_date: Optional[date] = None
    reference_listing_date: Optional[date] = None
    price_band_low_inr: Optional[float] = None
    price_band_high_inr: Optional[float] = None
    lot_size: Optional[int] = None
    fresh_issue_shares_cr: Optional[float] = None
    fresh_issue_amount_cr_inr: Optional[float] = None
    ofs_amount_cr_inr: Optional[float] = None
    total_issue_size_cr_inr: Optional[float] = None
    estimated_post_issue_mcap_cr_inr: Optional[float] = None
    restated_revenue_fy_cr_inr: Optional[float] = None
    restated_ebitda_fy_cr_inr: Optional[float] = None
    restated_pat_fy_cr_inr: Optional[float] = None
    pro_forma_pe: Optional[float] = None
    pro_forma_ev_ebitda: Optional[float] = None
    promoter_holding_pre_pct: Optional[float] = None
    promoter_holding_post_pct: Optional[float] = None
    use_of_proceeds: Optional[str] = None
    listed_peers: List[str] = Field(default_factory=list)
    customer_concentration_risk: Optional[str] = None
    litigation_and_contingent_liabilities: Optional[str] = None
    related_party_transactions_flag: Optional[str] = None
    auditor_qualifications: Optional[str] = None
    manual_review_required: bool = True
    primary_source_url: str
    sebi_filing_url: Optional[str] = None
    ai_relevance_assessment: str

    @model_validator(mode="after")
    def enforce_date_confirmation_invariants(self) -> "IPOCandidateSchema":
        # Invariant: An IPO with no confirmed dates or unverified live status is never displayed as confirmed UPCOMING/OPEN
        if (
            self.reference_open_date is None
            or self.reference_close_date is None
            or not self.dates_confirmed_by_live_exchange
        ):
            if self.current_status in (IPOStatus.UPCOMING, IPOStatus.OPEN):
                self.current_status = IPOStatus.RHP_REFERENCE_NEEDS_LIVE_CHECK
            self.dates_confirmed_by_live_exchange = False
        return self


class AIExtractedEvidenceSchema(BaseModel):
    """Strict schema for validating AI research outputs (Section 19 & 27)."""

    symbol: str
    model_name: str
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    supply_chain_category: str
    direct_exposure_confidence: str = Field(
        pattern="^(HIGH|MEDIUM|LOW|UNVERIFIED)$"
    )
    is_realised_revenue: bool = False
    event_stage: str = Field(
        pattern="^(ANNOUNCED_PLAN|SIGNED_CONTRACT|COMPLETED_PROJECT|RECOGNISED_REVENUE|PRESS_RELEASE_ONLY)$"
    )
    source_document: str
    source_page_or_passage: str
    summary_interpretation: str
    verified_facts: List[str] = Field(default_factory=list)
    needs_verification_banner: bool = True

    @model_validator(mode="after")
    def enforce_ai_safety_rules(self) -> "AIExtractedEvidenceSchema":
        # Invariant: A press release is never treated as realised revenue
        if self.event_stage in ("PRESS_RELEASE_ONLY", "ANNOUNCED_PLAN"):
            self.is_realised_revenue = False
            if self.direct_exposure_confidence == "HIGH":
                self.direct_exposure_confidence = "MEDIUM"
        if not self.source_document.strip() or not self.source_page_or_passage.strip():
            self.needs_verification_banner = True
            self.direct_exposure_confidence = "UNVERIFIED"
        return self


class ScoringWeightsSchema(BaseModel):
    """Configurable 100-point scoring profile weights."""

    profile_name: str = "Balanced Default"
    business_quality: float = 20.0
    growth_and_earnings: float = 20.0
    valuation: float = 20.0
    balance_sheet_cash_flow: float = 15.0
    technical_momentum: float = 15.0
    verified_ai_dc_exposure: float = 10.0

    @property
    def total_weight(self) -> float:
        return (
            self.business_quality
            + self.growth_and_earnings
            + self.valuation
            + self.balance_sheet_cash_flow
            + self.technical_momentum
            + self.verified_ai_dc_exposure
        )

    def normalized_weights(self) -> Dict[str, float]:
        tot = self.total_weight
        if tot <= 0:
            raise ValueError("Total scoring weights must be positive.")
        scale = 100.0 / tot
        return {
            "business_quality": self.business_quality * scale,
            "growth_and_earnings": self.growth_and_earnings * scale,
            "valuation": self.valuation * scale,
            "balance_sheet_cash_flow": self.balance_sheet_cash_flow * scale,
            "technical_momentum": self.technical_momentum * scale,
            "verified_ai_dc_exposure": self.verified_ai_dc_exposure * scale,
        }


class RiskFlag(BaseModel):
    code: str
    severity: RiskFlagSeverity
    category: str = "GENERAL"
    description: str
    metric_value: Optional[float] = None
    source_citation: Optional[str] = None


class ExposureScoreBreakdown(BaseModel):
    symbol: str
    direct_ai_dc_revenue_score: float = Field(ge=0.0, le=25.0)
    contract_backlog_visibility_score: float = Field(ge=0.0, le=15.0)
    customer_quality_score: float = Field(ge=0.0, le=15.0)
    supply_chain_criticality_score: float = Field(ge=0.0, le=15.0)
    margin_and_roce_score: float = Field(ge=0.0, le=10.0)
    balance_sheet_strength_score: float = Field(ge=0.0, le=10.0)
    valuation_reasonableness_score: float = Field(ge=0.0, le=10.0)
    total_score: float = Field(ge=0.0, le=100.0)
    profile_name: str = ScoringProfile.DEFAULT_100PT.value
    profile_adjusted_score: float = Field(ge=0.0, le=100.0)
    evidence_type: EvidenceType
    evidence_citation: str = ""
    risk_flags: List[RiskFlag] = Field(default_factory=list)
    has_critical_red_flag: bool = False
    investability_blocked: bool = False


class ValueAlternativeCandidate(BaseModel):
    symbol: str
    company_name: str
    similarity_score: float = Field(ge=0.0, le=100.0)
    shared_categories: List[str] = Field(default_factory=list)
    shared_subcategories: List[str] = Field(default_factory=list)
    valuation_comparison: Dict[str, Any] = Field(default_factory=dict)
    quality_comparison: Dict[str, Any] = Field(default_factory=dict)
    why_cheaper: str
    what_breaks_thesis: str
    liquidity_suitability: str
    ai_exposure_score: float = Field(ge=0.0, le=100.0)


class ValueAlternativeReport(BaseModel):
    target_symbol: str
    target_company_name: str
    target_trailing_pe: Optional[float] = None
    target_ev_ebitda: Optional[float] = None
    target_ai_exposure_score: float = Field(ge=0.0, le=100.0)
    alternatives: List[ValueAlternativeCandidate] = Field(default_factory=list)


class OverlapResult(BaseModel):
    basket_a_name: str
    basket_b_name: str
    weighted_overlap_pct: float = Field(ge=0.0, le=100.0)
    jaccard_similarity: float = Field(ge=0.0, le=1.0)
    shared_symbols_count: int = 0
    shared_symbols: List[Dict[str, Any]] = Field(default_factory=list)
    sector_overlap_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class AIResearchMemo(BaseModel):
    symbol: str
    company_name: str
    fact_vs_narrative_verdict: str
    verified_business_exposure: str
    bull_case: List[str]
    bear_case_and_risks: List[str]
    key_uncertainties: List[str]
    evidence_citations: List[str]
    generated_by: str
    needs_verification: bool = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

