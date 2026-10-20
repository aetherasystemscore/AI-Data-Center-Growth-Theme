"""Main Streamlit entry point for AI Infrastructure Investment Intelligence (AI3)."""

from __future__ import annotations

import streamlit as st

import core.page_bootstrap as page_bootstrap
from core.page_bootstrap import init_platform, render_sidebar_controls

st.set_page_config(
    page_title="AI3 | AI Infrastructure Investment Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    repo, ingestion = init_platform()

    if hasattr(st, "navigation") and hasattr(st, "Page"):
        pages = [
            st.Page(
                "pages/dashboard.py",
                title="1. Executive Dashboard",
                icon="📊",
                url_path="dashboard",
                default=True,
            ),
            st.Page(
                "pages/stock_screener.py",
                title="2. AI Value-Chain Screener",
                icon="🔍",
                url_path="stock_screener",
            ),
            st.Page(
                "pages/company_research.py",
                title="3. Deep Company Research",
                icon="🏢",
                url_path="company_research",
            ),
            st.Page(
                "pages/value_alternatives.py",
                title="4. Value Alternative Finder",
                icon="💎",
                url_path="value_alternatives",
            ),
            st.Page(
                "pages/etf_analysis.py",
                title="5. ETF Research & Overlap",
                icon="📦",
                url_path="etf_analysis",
            ),
            st.Page(
                "pages/smallcase_analysis.py",
                title="6. Smallcase & Look-Through",
                icon="🧩",
                url_path="smallcase_analysis",
            ),
            st.Page(
                "pages/ipo_tracker.py",
                title="7. IPO, DRHP & New Listings",
                icon="🚀",
                url_path="ipo_tracker",
            ),
            st.Page(
                "pages/circular_electronics.py",
                title="8. Circular Electronics & E-Waste",
                icon="♻️",
                url_path="circular_electronics",
            ),
            st.Page(
                "pages/portfolio_builder.py",
                title="9. Portfolio Builder & Optimiser",
                icon="📐",
                url_path="portfolio_builder",
            ),
            st.Page(
                "pages/backtesting.py",
                title="10. Point-in-Time Backtesting",
                icon="📈",
                url_path="backtesting",
            ),
            st.Page(
                "pages/settings.py",
                title="11. Discovery Jobs & Settings",
                icon="⚙️",
                url_path="settings",
            ),
        ]
        pg = st.navigation(pages, position="sidebar", expanded=True)
        render_sidebar_controls()
        page_bootstrap._IN_NAVIGATION_RUNNER = True
        try:
            pg.run()
        finally:
            page_bootstrap._IN_NAVIGATION_RUNNER = False
        return

    # Fallback for older Streamlit versions without st.navigation
    render_sidebar_controls()
    with st.sidebar:
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
