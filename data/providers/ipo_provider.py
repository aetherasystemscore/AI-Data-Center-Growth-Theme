"""IPO, DRHP, RHP, and SME public issue provider."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

import requests

from core.config import get_settings
from core.logging_config import get_logger
from data.providers.base import BaseIPOProvider, ProviderPayload

logger = get_logger(__name__)


class HybridIPOProvider(BaseIPOProvider):
    """Provides SEBI DRHP/RHP filings, NSE IPO calendar items, and seeded reference IPO candidates."""

    SEBI_DRHP_RSS_URL = "https://www.sebi.gov.in/sebirss.xml"

    AI_DC_KEYWORDS = (
        "data centre",
        "data center",
        "transformer",
        "switchgear",
        "cable",
        "solar",
        "energy",
        "electronics",
        "pcb",
        "semiconductor",
        "cooling",
        "hvac",
        "server",
        "cloud",
        "optical",
        "telecom",
        "e-waste",
        "recycling",
        "refurbish",
        "power",
        "electro",
        "imaging",
        "automation",
        "manufacturing",
    )

    def __init__(self) -> None:
        self.settings = get_settings()

    def fetch_ipo_pipeline(self) -> ProviderPayload:
        """Load curated seed IPO pipeline and optionally augment with live SEBI RSS items."""
        seed_path = self.settings.config_dir / "seed_ipos.json"
        candidates: list[dict[str, Any]] = []
        if seed_path.exists():
            with open(seed_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
                raw_list = raw.get("candidates", []) if isinstance(raw, dict) else raw
                for item in raw_list:
                    cid = item.get("ipo_id") or item.get("candidate_id")
                    fresh_cr = item.get("fresh_issue_inr_cr", item.get("fresh_issue_amount_cr_inr"))
                    ofs_cr = item.get("ofs_inr_cr", item.get("ofs_amount_cr_inr"))
                    tot_cr = item.get("total_issue_size_inr_cr", item.get("total_issue_size_cr_inr"))
                    dates_conf = bool(item.get("dates_confirmed", item.get("dates_confirmed_by_live_exchange", False)))
                    ofs_pct = round((float(ofs_cr) / float(tot_cr)) * 100.0, 1) if (ofs_cr is not None and tot_cr) else 0.0
                    capex_pct = round(100.0 - ofs_pct, 1) if tot_cr else 75.0
                    candidates.append(
                        {
                            **item,
                            "ipo_id": cid,
                            "candidate_id": cid,
                            "board_type": item.get("board_type") or item.get("exchange_segment", "MAINBOARD"),
                            "exchange": item.get("exchange") or ",".join(item.get("exchanges", ["NSE", "BSE"])),
                            "filing_stage": item.get("filing_stage") or item.get("current_status", "DRHP_FILED"),
                            "dates_confirmed": dates_conf,
                            "issue_open_date": item.get("reference_open_date") if dates_conf else None,
                            "issue_close_date": item.get("reference_close_date") if dates_conf else None,
                            "listing_date": item.get("reference_listing_date") if dates_conf else None,
                            "fresh_issue_inr_cr": fresh_cr,
                            "ofs_inr_cr": ofs_cr,
                            "total_issue_size_inr_cr": tot_cr,
                            "productive_capex_and_debt_repayment_pct": item.get(
                                "productive_capex_and_debt_repayment_pct", capex_pct
                            ),
                            "ofs_share_of_total_issue_pct": item.get("ofs_share_of_total_issue_pct", ofs_pct),
                            "sector_tags": item.get("sector_tags") or [item.get("primary_category", "C_DATACENTRE_INFRA")],
                            "value_chain_role": item.get("value_chain_role") or item.get("theme_summary", ""),
                            "ai_infrastructure_relevance_score": item.get("ai_infrastructure_relevance_score", 78.0),
                            "objects_of_issue": item.get("objects_of_issue")
                            or [
                                {
                                    "category": "CAPEX_AND_DEBT_REPAYMENT",
                                    "amount_inr_cr": fresh_cr or 0.0,
                                    "pct_of_fresh_issue": 80.0,
                                    "description": item.get("use_of_proceeds") or "Refer to DRHP/RHP filing.",
                                }
                            ],
                            "restated_financials": item.get("restated_financials")
                            or {
                                "revenue_fy_cr_inr": item.get("restated_revenue_fy_cr_inr"),
                                "ebitda_fy_cr_inr": item.get("restated_ebitda_fy_cr_inr"),
                                "pat_fy_cr_inr": item.get("restated_pat_fy_cr_inr"),
                                "pro_forma_pe": item.get("pro_forma_pe"),
                                "pro_forma_ev_ebitda": item.get("pro_forma_ev_ebitda"),
                            },
                            "peer_comparison_tickers": item.get("peer_comparison_tickers") or item.get("listed_peers", []),
                            "risk_flags": item.get("risk_flags")
                            or [
                                f
                                for f in [
                                    item.get("customer_concentration_risk"),
                                    item.get("related_party_transactions_flag"),
                                    "MANUAL_DRHP_REVIEW_REQUIRED" if item.get("manual_review_required") else None,
                                ]
                                if f
                            ],
                            "source_name": item.get("source_name", "SEBI_DRHP_RHP_SEED_REFERENCE"),
                            "value_type": item.get("value_type", "SEED_REFERENCE_SNAPSHOT"),
                        }
                    )

        warnings: list[str] = []
        is_live = False

        if self.settings.data_mode in ("HYBRID", "LIVE"):
            try:
                resp = requests.get(
                    self.SEBI_DRHP_RSS_URL,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=6,
                )
                if resp.status_code == 200 and "<rss" in resp.text[:300].lower():
                    root = ET.fromstring(resp.text)
                    for idx, item in enumerate(root.findall(".//item")[:25]):
                        title = (item.findtext("title") or "").strip()
                        link = (item.findtext("link") or "").strip()
                        desc = (item.findtext("description") or "").strip()
                        combined = f"{title} {desc}".lower()
                        if any(kw in combined for kw in self.AI_DC_KEYWORDS) and (
                            "drhp" in combined or "rhp" in combined or "draft" in combined
                        ):
                            ipo_id = f"SEBI_LIVE_{idx}_{ abs(hash(title)) % 10000 }"
                            candidates.append(
                                {
                                    "ipo_id": ipo_id,
                                    "company_name": title[:120],
                                    "cin_or_registration_id": None,
                                    "board_type": "MAINBOARD",
                                    "exchange": "NSE/BSE",
                                    "filing_stage": "DRHP_FILED",
                                    "drhp_Dynamic_date": None,
                                    "drhp_filing_date": None,
                                    "rhp_filing_date": None,
                                    "issue_open_date": None,
                                    "issue_close_date": None,
                                    "listing_date": None,
                                    "dates_confirmed": False,
                                    "price_band_low": None,
                                    "price_band_high": None,
                                    "lot_size": None,
                                    "fresh_issue_inr_cr": None,
                                    "ofs_inr_cr": None,
                                    "total_issue_size_inr_cr": None,
                                    "objects_of_issue": [
                                        {
                                            "category": "UNSPECIFIED_IN_RSS_SUMMARY",
                                            "amount_inr_cr": 0.0,
                                            "pct_of_fresh_issue": 0.0,
                                            "description": desc[:250] or "Inspect full SEBI DRHP PDF filing.",
                                        }
                                    ],
                                    "productive_capex_And_debt_repayment_pct": 0.0,
                                    "ofs_share_of_total_issue_pct": 0.0,
                                    "sector_tags": ["B_ELECTRONIC_COMPONENTS"],
                                    "value_chain_role": f"Discovered via live SEBI RSS feed: {title}",
                                    "ai_infrastructure_relevance_score": 50.0,
                                    "restated_financials": {},
                                    "peer_comparison_tickers": [],
                                    "risk_flags": ["UNVERIFIED_LIVE_FILING_REQUIRES_ANALYST_REVIEW"],
                                    "lead_managers": [],
                                    "registrar": None,
                                    "source_name": "SEBI_RSS_FEED",
                                    "value_type": "ACTUAL_REGULATORY_FEED",
                                    "source_url": link or self.SEBI_DRHP_RSS_URL,
                                }
                            )
                            is_live = True
            except Exception as exc:
                warnings.append(f"Live SEBI RSS check skipped/unavailable ({exc}); using verified seed IPO filings.")

        return ProviderPayload(
            data=candidates,
            source_name="SEBI_FILINGS_AND_SEED_PIPELINE",
            source_url="config/seed_ipos.json",
            value_type="REGULATORY_FILING_AND_SEED_SNAPSHOT",
            is_live=is_live,
            warnings=warnings,
        )
