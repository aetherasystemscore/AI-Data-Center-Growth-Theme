"""Main Streamlit entry point for AI Infrastructure Investment Intelligence (AI3)."""

from __future__ import annotations

import streamlit as st

from core.config import get_settings
from core.schemas import ScoringProfile
from data.ingestion import DataIngestionService
from database.repository import AI3Repository


st.set_page_config(
    page_title="AI3 | AI Infrastructure Investment Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def init_platform() -> tuple[AI3Repository, DataIngestionService]:
    repo = AI3Repository()
    ingestion = DataIngestionService(repo=repo)
    ingestion.ensure_bootstrapped()
    return repo, ingestion


def main() -> None:
    repo, ingestion = init_platform()
    settings = get_settings()

    with st.sidebar:
        st.markdown("## ⚡ AI3 Intelligence")
        st.caption(
            "AI Infrastructure, Data Centre, Small Components, Circular Electronics & IPO Research Platform"
        )
        st.divider()

        page_options = {
            "1. Executive Dashboard": "dashboard",
            "2. AI Value-Chain Screener": "stock_screener",
            "3. Deep Company Research": "company_research",
            "4. Value Alternative Finder": "value_alternatives",
            "5. ETF Research & Overlap": "etf_analysis",
            "6. Smallcase & Look-Through": "smallcase_analysis",
            "7. IPO, DRHP & New Listings": "ipo_tracker",
            "8. Circular Electronics & E-Waste": "circular_electronics",
            "9. Portfolio Builder & Optimiser": "portfolio_builder",
            "10. Point-in-Time Backtesting": "backtesting",
            "11. Discovery Jobs & Settings": "settings",
        }

        selected_label = st.radio(
            "Navigation Module",
            options=list(page_options.keys()),
            index=0,
        )
        selected_module = page_options[selected_label]

        st.divider()
        profile_options = [p.value for p in ScoringProfile]
        default_prof_idx = profile_options.index(ScoringProfile.DEFAULT_100PT.value)
        active_profile = st.selectbox(
            "Active Scoring Profile",
            options=profile_options,
            index=default_prof_idx,
            help="Adjusts the 7-factor weights in the 100-point AI Infrastructure Exposure Model.",
        )
        st.session_state["active_scoring_profile"] = active_profile

        st.info(
            f"**Data Mode:** `{settings.data_mode}`\n\n"
            "All metrics carry provenance tags (`SEED_REFERENCE_SNAPSHOT`, `ACTUAL_MARKET_CLOSE`, or `SYNTHETIC_SAMPLE_CALIBRATED`). "
            "Missing fields remain `N/A` (never replaced with `0`)."
        )
        st.caption(
            "**Disclaimer:** Research and portfolio analysis tool only. Not SEBI-registered investment advice. "
            "Does not execute trades or auto-subscribe to IPOs."
        )

    if selected_module == "dashboard":
        from pages.dashboard import render

        render(repo, ingestion)
    elif selected_module == "stock_screener":
        from pages.stock_screener import render

        render(repo, ingestion)
    elif selected_module == "company_research":
        from pages.company_research import render

        render(repo, ingestion)
    elif selected_module == "value_alternatives":
        from pages.value_alternatives import render

        render(repo, ingestion)
    elif selected_module == "etf_analysis":
        from pages.etf_analysis import render

        render(repo, ingestion)
    elif selected_module == "smallcase_analysis":
        from pages.smallcase_analysis import render

        render(repo, ingestion)
    elif selected_module == "ipo_tracker":
        from pages.ipo_tracker import render

        render(repo, ingestion)
    elif selected_module == "circular_electronics":
        from pages.circular_electronics import render

        render(repo, ingestion)
    elif selected_module == "portfolio_builder":
        from pages.portfolio_builder import render

        render(repo, ingestion)
    elif selected_module == "backtesting":
        from pages.backtesting import render

        render(repo, ingestion)
    elif selected_module == "settings":
        from pages.settings import render

        render(repo, ingestion)


if __name__ == "__main__":
    main()
