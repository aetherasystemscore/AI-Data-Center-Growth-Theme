"""Page 4: Value Alternative Finder (Section 12 of the Master Project Prompt)."""

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

from analytics.value_alternatives import find_value_alternatives
from data.ingestion import DataIngestionService
from database.repository import AI3Repository


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("💎 Value Alternative Finder (Supply-Chain Relative Value)")
    st.markdown(
        "Identify **3–5 better-value companies** operating in the same AI/data-centre supply chain as a popular or expensive stock, "
        "complete with business similarity scores, valuation discounts, quality comparisons, and thesis-invalidation risks."
    )

    all_secs = repo.get_securities()
    f_map = repo.get_latest_fundamentals_map()
    sec_by_sym = {s["symbol"]: s for s in all_secs}

    popular_defaults = ["DIXON", "ABB", "SIEMENS", "HITACHIEN", "CUMMINSIND", "KAYNES", "BLUESTARCO", "POLYCAB", "PERSISTENT", "NETWEB"]
    all_india_syms = [s["symbol"] for s in all_secs if s["geography"] == "INDIA"]
    ordered_syms = [s for s in popular_defaults if s in sec_by_sym] + [s for s in all_india_syms if s not in popular_defaults]

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        target_sym = st.selectbox(
            "Select Popular / Expensive Target Stock",
            options=ordered_syms,
            index=0,
            format_func=lambda s: (
                f"{s} — {sec_by_sym[s]['company_name']} "
                f"(P/E: {f_map.get(s, {}).get('trailing_pe') or 'N/A'}x | EV/EBITDA: {f_map.get(s, {}).get('ev_ebitda') or 'N/A'}x)"
            ),
        )
    with col2:
        top_n = st.slider("Number of Alternatives", 3, 5, 4)
    with col3:
        include_global = st.checkbox("Include Global Benchmarks", value=False)

    report = find_value_alternatives(
        target_symbol=target_sym,
        securities=all_secs,
        fundamentals_map=f_map,
        top_n=top_n,
        include_global_benchmarks=include_global,
    )

    t_f = f_map.get(target_sym, {})
    st.info(
        f"**Target Benchmark:** `{report.target_symbol}` ({report.target_company_name}) | "
        f"**Trailing P/E:** `{report.target_trailing_pe or 'N/A'}x` | "
        f"**EV/EBITDA:** `{report.target_ev_ebitda or 'N/A'}x` | "
        f"**ROCE:** `{t_f.get('roce_pct') or 'N/A'}%` | "
        f"**AI Exposure Score:** `{report.target_ai_exposure_score}/100`"
    )

    if not report.alternatives:
        st.warning("No cheaper investable alternatives found for this security under current constraints.")
        return

    summary_rows = []
    for alt in report.alternatives:
        vc = alt.valuation_comparison
        qc = alt.quality_comparison
        summary_rows.append(
            {
                "Alternative Symbol": alt.symbol,
                "Company": alt.company_name,
                "Business Similarity (%)": alt.similarity_score,
                "AI Exposure Score": alt.ai_exposure_score,
                "Alt Trailing P/E": vc["alternative_trailing_pe"],
                "P/E Discount vs Target (%)": vc["pe_discount_pct"],
                "Alt EV/EBITDA": vc["alternative_ev_ebitda"],
                "EV/EBITDA Discount (%)": vc["ev_ebitda_discount_pct"],
                "Alt PEG": vc["alternative_peg"],
                "Alt ROCE (%)": qc["alternative_roce_pct"],
                "Alt 3Y Rev CAGR (%)": qc["alternative_rev_cagr_3y_pct"],
                "Alt Order Book/Sales (x)": qc["alternative_order_book_to_sales"],
                "Alt Debt/Equity": qc["alternative_debt_to_equity"],
            }
        )

    st.subheader(f"Shortlisted Value Alternatives for `{target_sym}`")
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Detailed Trade-Off & Thesis Invalidation Analysis")
    for idx, alt in enumerate(report.alternatives, start=1):
        with st.expander(
            f"#{idx} {alt.symbol} — {alt.company_name} | Similarity: {alt.similarity_score}% | "
            f"P/E Discount: {alt.valuation_comparison['pe_discount_pct']}% | AI Score: {alt.ai_exposure_score}/100",
            expanded=(idx <= 2),
        ):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Shared Value-Chain Categories:** `{', '.join(alt.shared_categories) or 'Adjacent Supply Chain'}`")
                st.markdown(f"**Shared Subcategories:** `{', '.join(alt.shared_subcategories) or 'Component / Infrastructure Peer'}`")
                st.markdown(f"**Why `{alt.symbol}` Is Cheaper than `{target_sym}`:**\n> {alt.why_cheaper}")
            with c2:
                st.markdown(f"**What Could Break the Thesis:**\n> {alt.what_breaks_thesis}")
                st.markdown(f"**Liquidity & Position-Sizing Suitability:**\n> {alt.liquidity_suitability}")


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
