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
import plotly.express as px
import streamlit as st

from analytics.equity_enrichment import (
    compute_enriched_equity_metrics,
    get_2y_quarterly_shareholding_and_price,
)
from analytics.value_alternatives import find_value_alternatives
from data.ingestion import DataIngestionService
from database.repository import AI3Repository


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("💎 Value Alternative Finder (Target vs Supply-Chain Relative Value)")
    st.caption(
        "Compare any popular/expensive target stock (e.g., DIXON, ABB, SIEMENS, HITACHIEN) directly alongside 3–5 cheaper supply-chain alternatives "
        "with Fundamental Score, Technical Score, Analyst Consensus, 2-Year Price Trend, and 2-Year Promoter/FII/DII Holding Trends."
    )

    profile = st.session_state.get("active_scoring_profile", "HIGH_GROWTH_INFRA")
    all_secs = repo.get_securities()
    f_map = repo.get_latest_fundamentals_map()
    sec_by_sym = {s["symbol"]: s for s in all_secs}

    popular_defaults = [
        "DIXON",
        "ABB",
        "SIEMENS",
        "HITACHIEN",
        "CUMMINSIND",
        "KAYNES",
        "BLUESTARCO",
        "POLYCAB",
        "PERSISTENT",
        "NETWEB",
    ]
    all_india_syms = [s["symbol"] for s in all_secs if s["geography"] == "INDIA"]
    ordered_syms = [s for s in popular_defaults if s in sec_by_sym] + [
        s for s in all_india_syms if s not in popular_defaults
    ]

    col1, col2, col3 = st.columns([2.2, 1, 1])
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

    t_sec = sec_by_sym[target_sym]
    t_f = f_map.get(target_sym, {})
    t_enr = compute_enriched_equity_metrics(t_sec, t_f, profile=profile)

    # Target stock KPI strip so the target's own scores and trends are front and center
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric(f"🎯 {target_sym} CMP", f"Rs {t_enr['cmp']:,.2f}", f"P/E: {report.target_trailing_pe or 'N/A'}x")
    k2.metric("AI Exposure Score", f"{report.target_ai_exposure_score}/100", f"Profile: {t_enr['profile_score']}/100")
    k3.metric("Fundamental Score", f"{t_enr['fundamental_score']}/100", f"ROCE: {t_f.get('roce_pct') or 'N/A'}%")
    k4.metric("Technical Score", f"{t_enr['technical_score']}/100", t_enr["technical_regime"])
    k5.metric("Analyst Score", f"{t_enr['analyst_score']}/100", f"{t_enr['analyst_rating']} ({t_enr['analyst_upside_pct']:+.1f}%)")
    k6.metric("1Y / 2Y Price Trend", f"1Y: {t_enr['return_1y_pct']:+.1f}%", f"2Y: {t_enr['return_2y_pct']:+.1f}%")

    if not report.alternatives:
        st.warning("No cheaper investable alternatives found for this security under current constraints.")
        return

    # Build unified comparison table with TARGET BENCHMARK as Row #0 followed by shortlisted alternatives
    summary_rows = [
        {
            "Role": f"🎯 TARGET ({target_sym})",
            "Symbol": target_sym,
            "Company": report.target_company_name,
            "CMP (Rs)": t_enr["cmp"],
            "Similarity (%)": 100.0,
            "AI Score (/100)": report.target_ai_exposure_score,
            "Fundamental Score (/100)": t_enr["fundamental_score"],
            "Technical Score (/100)": t_enr["technical_score"],
            "Analyst Score (/100)": t_enr["analyst_score"],
            "Analyst Rating": t_enr["analyst_rating"],
            "Trailing P/E": report.target_trailing_pe,
            "P/E Discount vs Target (%)": 0.0,
            "EV/EBITDA": report.target_ev_ebitda,
            "EV/EBITDA Discount (%)": 0.0,
            "PEG": t_f.get("peg_ratio"),
            "ROCE (%)": t_f.get("roce_pct"),
            "3Y Rev CAGR (%)": t_f.get("rev_cagr_3y_pct"),
            "Order Book/Sales (x)": t_f.get("order_book_to_LTM_sales"),
            "Debt/Equity": t_f.get("debt_to_equity"),
            "Price Trend (1M | 6M | 1Y | 2Y)": t_enr["price_trend_summary"],
            "Promoter Holding (2Y Trend)": t_enr["promoter_trend"],
            "FII Holding (2Y Trend)": t_enr["fii_trend"],
            "DII Holding (2Y Trend)": t_enr["dii_trend"],
        }
    ]

    for idx, alt in enumerate(report.alternatives, start=1):
        vc = alt.valuation_comparison
        qc = alt.quality_comparison
        a_sec = sec_by_sym.get(alt.symbol, {"symbol": alt.symbol, "is_investable": True})
        a_f = f_map.get(alt.symbol, {})
        a_enr = compute_enriched_equity_metrics(a_sec, a_f, profile=profile)
        summary_rows.append(
            {
                "Role": f"💎 ALT #{idx}",
                "Symbol": alt.symbol,
                "Company": alt.company_name,
                "CMP (Rs)": a_enr["cmp"],
                "Similarity (%)": alt.similarity_score,
                "AI Score (/100)": alt.ai_exposure_score,
                "Fundamental Score (/100)": a_enr["fundamental_score"],
                "Technical Score (/100)": a_enr["technical_score"],
                "Analyst Score (/100)": a_enr["analyst_score"],
                "Analyst Rating": a_enr["analyst_rating"],
                "Trailing P/E": vc["alternative_trailing_pe"],
                "P/E Discount vs Target (%)": vc["pe_discount_pct"],
                "EV/EBITDA": vc["alternative_ev_ebitda"],
                "EV/EBITDA Discount (%)": vc["ev_ebitda_discount_pct"],
                "PEG": vc["alternative_peg"],
                "ROCE (%)": qc["alternative_roce_pct"],
                "3Y Rev CAGR (%)": qc["alternative_rev_cagr_3y_pct"],
                "Order Book/Sales (x)": qc["alternative_order_book_to_sales"],
                "Debt/Equity": qc["alternative_debt_to_equity"],
                "Price Trend (1M | 6M | 1Y | 2Y)": a_enr["price_trend_summary"],
                "Promoter Holding (2Y Trend)": a_enr["promoter_trend"],
                "FII Holding (2Y Trend)": a_enr["fii_trend"],
                "DII Holding (2Y Trend)": a_enr["dii_trend"],
            }
        )

    st.subheader(f"Target Benchmark (`{target_sym}`) vs Shortlisted Value Alternatives")
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    # 2-Year Price Trend & Shareholding Trend (Promoter / FII / DII) across Target + Alternatives
    st.divider()
    st.subheader(f"📊 2-Year Price & Shareholding Trend (Promoter / FII / DII): `{target_sym}` vs Alternatives")
    compare_syms = [target_sym] + [alt.symbol for alt in report.alternatives]
    q_all: list[dict] = []
    for sym in compare_syms:
        s_obj = sec_by_sym.get(sym, {"symbol": sym, "is_investable": True})
        f_obj = f_map.get(sym, {})
        q_all.extend(get_2y_quarterly_shareholding_and_price(s_obj, f_obj))
    df_q = pd.DataFrame(q_all)

    ch1, ch2 = st.columns(2)
    with ch1:
        # Normalized 2Y price index (Start = 100) so different rupee prices compare cleanly
        df_q["Normalized Price (Base=100)"] = df_q.groupby("Symbol")["Quarter Close Price"].transform(
            lambda s: round((s / s.iloc[0]) * 100.0, 1)
        )
        fig_pr = px.line(
            df_q,
            x="Quarter",
            y="Normalized Price (Base=100)",
            color="Symbol",
            markers=True,
            title="2-Year Indexed Price Trend (Base 100 = 8 Quarters Ago)",
        )
        fig_pr.update_layout(height=310, margin=dict(t=35, l=10, r=10, b=10))
        st.plotly_chart(fig_pr, use_container_width=True)

    with ch2:
        hold_metric = st.selectbox(
            "Select 2-Year Ownership Cohort to Plot",
            ["FII + DII Institutional (%)", "Promoter (%)", "FII (%)", "DII (%)"],
            index=0,
        )
        fig_sh = px.line(
            df_q,
            x="Quarter",
            y=hold_metric,
            color="Symbol",
            markers=True,
            title=f"2-Year {hold_metric} Trend (Last 8 Quarters)",
        )
        fig_sh.update_layout(height=265, margin=dict(t=35, l=10, r=10, b=10))
        st.plotly_chart(fig_sh, use_container_width=True)

    with st.expander("📋 View Full 8-Quarter (2-Year) Promoter, FII, DII & Price Table"):
        st.dataframe(df_q, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Detailed Trade-Off & Thesis Invalidation Analysis")
    for idx, alt in enumerate(report.alternatives, start=1):
        a_enr = compute_enriched_equity_metrics(sec_by_sym.get(alt.symbol, {"symbol": alt.symbol}), f_map.get(alt.symbol, {}), profile=profile)
        with st.expander(
            f"#{idx} {alt.symbol} — {alt.company_name} | Similarity: {alt.similarity_score}% | "
            f"P/E Discount: {alt.valuation_comparison['pe_discount_pct']}% | "
            f"Fund: {a_enr['fundamental_score']}/100 | Tech: {a_enr['technical_score']}/100 | Analyst: {a_enr['analyst_rating']}",
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
                st.markdown(
                    f"**2Y Ownership & Price Summary:** `{a_enr['price_trend_summary']}` • `{a_enr['combined_holding_trend']}`"
                )


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
