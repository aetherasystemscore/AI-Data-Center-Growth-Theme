"""Shared Streamlit page bootstrapper for both st.navigation and standalone pages/*.py execution."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from core.config import get_settings
from core.schemas import ScoringProfile
from data.ingestion import DataIngestionService
from database.repository import AI3Repository

_IN_NAVIGATION_RUNNER: bool = False


@st.cache_resource
def init_platform() -> tuple[AI3Repository, DataIngestionService]:
    """Initialize SQLite repository and seed/bootstrap data once per server process."""
    repo = AI3Repository()
    ingestion = DataIngestionService(repo=repo)
    ingestion.ensure_bootstrapped()
    return repo, ingestion


def render_sidebar_controls() -> None:
    """Render shared AI3 sidebar branding, active scoring profile selector, and data-provenance notice."""
    settings = get_settings()
    with st.sidebar:
        st.markdown("## ⚡ AI3 Intelligence")
        st.caption(
            "AI Infrastructure, Data Centre, Small Components, Circular Electronics & IPO Research Platform"
        )
        st.divider()
        profile_options = [p.value for p in ScoringProfile]
        default_prof_idx = profile_options.index(ScoringProfile.DEFAULT_100PT.value)
        active_profile = st.selectbox(
            "Active Scoring Profile",
            options=profile_options,
            index=default_prof_idx,
            key="ai3_active_scoring_profile_select",
            help="Adjusts the 6-component weights in the 100-point AI Infrastructure Exposure Model.",
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


def run_standalone_page(render_fn: Callable[[AI3Repository, DataIngestionService], None]) -> None:
    """Execute a page's render(repo, ingestion) function whether invoked via st.navigation or direct /<page> URL."""
    if not _IN_NAVIGATION_RUNNER:
        try:
            st.set_page_config(
                page_title="AI3 | AI Infrastructure Investment Intelligence",
                page_icon="⚡",
                layout="wide",
                initial_sidebar_state="expanded",
            )
        except Exception:
            pass
        render_sidebar_controls()

    repo, ingestion = init_platform()
    render_fn(repo, ingestion)
