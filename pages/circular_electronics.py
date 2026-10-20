"""Page 8: Circular Electronics, ITAD, Server Refurbishment & E-Waste Module (Section 4H & 5 of Master Prompt)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_PAGES_DIR = str(Path(__file__).resolve().parent)
if _PAGES_DIR in sys.path:
    sys.path.remove(_PAGES_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd
import streamlit as st

from analytics.exposure_scoring import score_company_exposure
from data.ingestion import DataIngestionService
from database.repository import AI3Repository


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("♻️ Circular Electronics, Server Refurbishment & E-Waste Module")
    st.markdown(
        "Research companies involved in **IT Asset Disposition (ITAD)**, **enterprise server refurbishment**, "
        "**PCB & precious-metal recovery**, **copper/cable recycling**, and **battery/power-electronics circularity**."
    )

    st.warning(
        "**Mandatory Governance & Liquidity Gatekeeper (Section 5 Rule):**\n"
        "For Indian circular-electronics candidates (`ECORECO`, `CEREBRAINT`, `NAMOEWASTE`), AI3 validates current business "
        "activities, auditor reports, exchange status, and daily liquidity before permitting inclusion in any investable basket."
    )

    all_secs = repo.get_securities()
    f_map = repo.get_latest_fundamentals_map()

    circular_rows = []
    adjacent_rows = []

    for sec in all_secs:
        tags = sec.get("sector_tags", [])
        f = f_map.get(sec["symbol"], {})
        bd = score_company_exposure(sec, f, profile="CIRCULAR_ECONOMY_FOCUS")

        row_data = {
            "Symbol": sec["symbol"],
            "Company": sec["company_name"],
            "Exchange": sec["exchange"],
            "Geography": sec["geography"],
            "Universe Tier": sec["universe_tier"],
            "Investable Status": "APPROVED_INVESTABLE" if (sec["is_investable"] and not bd.investability_blocked) else "ISOLATED_HIGH_RISK_RESEARCH",
            "Subcategories": ", ".join(sec.get("subcategories", [])),
            "Circular Profile Score": bd.profile_adjusted_score,
            "Revenue (Rs Cr)": f.get("revenue_inr_cr"),
            "PAT (Rs Cr)": f.get("pat_inr_cr"),
            "ROCE (%)": f.get("roce_pct"),
            "Daily Turnover (Rs Cr)": f.get("avg_daily_turnover_inr_cr"),
            "Auditor Qualification": bool(f.get("auditor_qualification_flag", False)),
            "Operational KPI": f"{f.get('sector_kpi_name') or 'N/A'}: {f.get('sector_kpi_value') or 'N/A'} {f.get('sector_kpi_unit') or ''}",
            "Governance & Liquidity Notes": f.get("governance_notes") or sec.get("notes"),
        }

        if "H_CIRCULAR_ELECTRONICS" in tags:
            circular_rows.append(row_data)
        elif sec["symbol"] in ("APARINDS", "POLYCAB", "KEI", "REDINGTON", "RASHI", "DIXON", "SYRMA"):
            adjacent_rows.append(row_data)

    st.subheader("1. Dedicated E-Waste, ITAD & Circular Electronics Candidates")
    st.dataframe(pd.DataFrame(circular_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("2. Candidate-by-Candidate Due Diligence Verdict")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("#### `ECORECO` — Eco Recycling Ltd (BSE)")
        st.info(
            "- **Business:** CPCB-authorised e-waste recycling, ITAD, data destruction & precious metal recovery.\n"
            "- **Financials:** Profitable (ROCE ~21.5%, low debt), capacity ~25,200 MTPA.\n"
            "- **Gatekeeper Status:** `HIGH_RISK_RESEARCH` due to micro-cap daily liquidity (~Rs 1.8 Cr/day ADV). Suitable only for specialist micro-cap research with strict limit orders."
        )
    with c2:
        st.markdown("#### `NAMOEWASTE` — Namo eWaste Management (NSE SME)")
        st.info(
            "- **Business:** E-waste collection, PCB dismantling, and lithium-ion battery recycling (listed Sept 2024 on NSE Emerge).\n"
            "- **Financials:** Profitable SME growth stage, working capital cycle ~82 days.\n"
            "- **Gatekeeper Status:** `HIGH_RISK_RESEARCH` due to SME lot-size liquidity (~Rs 1.2 Cr/day ADV) and <2Y listed track record."
        )
    with c3:
        st.markdown("#### `CEREBRAINT` — Cerebra Integrated Technologies")
        st.error(
            "- **Business:** Historical e-waste narrative.\n"
            "- **Red Flags:** Auditor qualifications, severe receivable write-offs, negative net returns, and regulatory scrutiny.\n"
            "- **Gatekeeper Status:** `BLOCKED / DO NOT INVEST` (`auditor_qualification_flag=True`). Never included in investable portfolios."
        )

    st.divider()
    st.subheader("3. Circular Supply-Chain Taxonomy Coverage (`H1` – `H12`)")
    tax_sub = [
        {"Code": "H1", "Subcategory": "IT Asset Disposition (ITAD)", "Indian / Global Coverage": "ECORECO (India), ERI (Global Unlisted Benchmark)"},
        {"Code": "H2", "Subcategory": "Enterprise Server Refurbishment", "Indian / Global Coverage": "ECORECO, Unlisted Hyperscale Reverse-Logistics Vendors"},
        {"Code": "H5/H6", "Subcategory": "E-Waste Collection & PCB Recycling", "Indian / Global Coverage": "ECORECO, NAMOEWASTE"},
        {"Code": "H7", "Subcategory": "Copper & Precious-Metal Recovery", "Indian / Global Coverage": "ECORECO, NAMOEWASTE (plus industrial copper users POLYCAB, KEI, APARINDS)"},
        {"Code": "H8", "Subcategory": "Battery & Power-Electronics Recycling", "Indian / Global Coverage": "NAMOEWASTE, Exicom / Tata Power Storage Ecosystem"},
        {"Code": "H9", "Subcategory": "Certified Data Destruction", "Indian / Global Coverage": "ECORECO (Onsite/Offsite degaussing & shredding)"},
    ]
    st.dataframe(pd.DataFrame(tax_sub), use_container_width=True, hide_index=True)


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
