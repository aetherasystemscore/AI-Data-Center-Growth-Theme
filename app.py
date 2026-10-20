"""Main Streamlit entry point for AI Infrastructure Investment Intelligence (AI3)."""

from __future__ import annotations

import streamlit as st

from core.page_bootstrap import init_platform, render_sidebar_controls, render_top_bar

st.set_page_config(
    page_title="AI3 | AI Infrastructure Investment Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    repo, ingestion = init_platform()

    # 1. Top-Left Sidebar Navigation Module + Scoring Profile + Live Host CPU/RAM Telemetry
    selected_module = render_sidebar_controls()

    # 2. Compact Top Host Telemetry Strip + 1-Click Horizontal Module Bar
    render_top_bar(show_quick_nav=True)

    # 3. Render Selected Module from views/
    if selected_module == "dashboard":
        from views.dashboard import render

        render(repo, ingestion)
    elif selected_module == "stock_screener":
        from views.stock_screener import render

        render(repo, ingestion)
    elif selected_module == "company_research":
        from views.company_research import render

        render(repo, ingestion)
    elif selected_module == "value_alternatives":
        from views.value_alternatives import render

        render(repo, ingestion)
    elif selected_module == "etf_analysis":
        from views.etf_analysis import render

        render(repo, ingestion)
    elif selected_module == "smallcase_analysis":
        from views.smallcase_analysis import render

        render(repo, ingestion)
    elif selected_module == "ipo_tracker":
        from views.ipo_tracker import render

        render(repo, ingestion)
    elif selected_module == "circular_electronics":
        from views.circular_electronics import render

        render(repo, ingestion)
    elif selected_module == "portfolio_builder":
        from views.portfolio_builder import render

        render(repo, ingestion)
    elif selected_module == "backtesting":
        from views.backtesting import render

        render(repo, ingestion)
    elif selected_module == "settings":
        from views.settings import render

        render(repo, ingestion)
    elif selected_module == "paper_trading":
        from views.paper_trading import render

        render(repo, ingestion)


if __name__ == "__main__":
    main()
