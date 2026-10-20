"""Page 3: Deep Company Research Terminal."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_PAGES_DIR = str(Path(__file__).resolve().parent)
if _PAGES_DIR in sys.path:
    sys.path.remove(_PAGES_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ai.document_extraction import extract_facts_from_filing_text
from ai.research_summariser import generate_company_research_memo
from analytics.exposure_scoring import score_company_exposure
from analytics.fundamentals import evaluate_fundamental_health
from analytics.technicals import compute_technical_indicators
from analytics.valuation import compute_valuation_metrics
from data.ingestion import DataIngestionService
from database.repository import AI3Repository
from portfolio.basket_builder import MARKET_ACCESS_GUIDANCE


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("🏛️ Deep Company Research & Fact-vs-Narrative Terminal")

    all_secs = repo.get_securities()
    f_map = repo.get_latest_fundamentals_map()
    sec_by_sym = {s["symbol"]: s for s in all_secs}

    sym_list = sorted(list(sec_by_sym.keys()))
    default_idx = sym_list.index("NETWEB") if "NETWEB" in sym_list else 0

    col_sel1, col_sel2 = st.columns([2, 2])
    with col_sel1:
        symbol = st.selectbox(
            "Select Security (Ticker Verified)",
            options=sym_list,
            index=default_idx,
            format_func=lambda s: f"{s} — {sec_by_sym[s]['company_name']} ({sec_by_sym[s]['exchange']})",
        )
    with col_sel2:
        profile = st.session_state.get("active_scoring_profile", "DEFAULT_100PT")
        st.metric("Active Scoring Profile", profile)

    sec = sec_by_sym[symbol]
    f = f_map.get(symbol, {})
    peer_f = [
        f_map.get(s["symbol"], {})
        for s in all_secs
        if s.get("primary_category") == sec.get("primary_category") and s["geography"] == sec["geography"]
    ]

    score_bd = score_company_exposure(sec, f, profile=profile)
    fund_health = evaluate_fundamental_health(f, sec)
    val_metrics = compute_valuation_metrics(f, peer_records=peer_f)

    # Header status banner
    if score_bd.investability_blocked or not sec["is_investable"]:
        st.error(
            f"🚨 **HIGH-RISK / NON-INVESTABLE SECURITY (`{sec['universe_tier']}`):** "
            f"{sec['company_name']} (`{symbol}`) is blocked from standard investable portfolios due to critical risk flags."
        )
    else:
        st.success(
            f"✅ **Verified Investable Security (`{sec['exchange']}:{symbol}`)** | "
            f"Primary Segment: `{sec['primary_category']}` | Subcategories: `{', '.join(sec.get('subcategories', []))}`"
        )

    if sec["geography"] != "INDIA":
        access = MARKET_ACCESS_GUIDANCE.get(sec["geography"], MARKET_ACCESS_GUIDANCE["US"])
        st.info(
            f"🌏 **Global Research Benchmark ({sec['geography']}):** {access['access_route']}\n\n"
            f"- **Taxation:** {access['taxation_note']}\n"
            f"- **Currency Risk:** {access['currency_risk']}"
        )

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Base AI Score (100)", f"{score_bd.total_score:.1f}/100", f"Profile: {score_bd.profile_adjusted_score:.1f}")
    m2.metric(
        "Direct AI/DC Rev %",
        f"{f.get('direct_ai_dc_rev_share_pct'):.1f}%" if f.get("direct_ai_dc_rev_share_pct") is not None else "N/A",
        score_bd.evidence_type.value,
    )
    m3.metric(
        "Trailing P/E",
        f"{val_metrics['trailing_pe']:.1f}x" if val_metrics["trailing_pe"] is not None else "N/A",
        f"Fwd: {val_metrics['forward_pe']:.1f}x" if val_metrics["forward_pe"] is not None else "Fwd: N/A",
    )
    m4.metric(
        "ROCE / ROE",
        f"{f.get('roce_pct'):.1f}%" if f.get("roce_pct") is not None else "N/A",
        f"ROE: {f.get('roe_pct'):.1f}%" if f.get("roe_pct") is not None else "ROE: N/A",
    )
    m5.metric(
        "Order Book / Sales",
        f"{f.get('order_book_to_LTM_sales'):.2f}x" if f.get("order_book_to_LTM_sales") is not None else "N/A",
        f"Rs {f.get('order_book_inr_cr'):,.0f} Cr" if f.get("order_book_inr_cr") else "No Backlog Disclosed",
    )
    m6.metric(
        "Sector KPI",
        f"{f.get('sector_kpi_value')} {f.get('sector_kpi_unit') or ''}" if f.get("sector_kpi_value") is not None else "N/A",
        f.get("sector_kpi_name") or "Operational Metric",
    )

    st.divider()

    col_score, col_memo = st.columns([2, 3])
    with col_score:
        st.subheader("100-Point AI Exposure Breakdown")
        comp_df = pd.DataFrame(
            [
                {"Component": "1. Direct AI/DC Revenue (Max 25)", "Score": score_bd.direct_ai_dc_revenue_score, "Max": 25.0},
                {"Component": "2. Confirmed Backlog (Max 15)", "Score": score_bd.contract_backlog_visibility_score, "Max": 15.0},
                {"Component": "3. Customer Quality (Max 15)", "Score": score_bd.customer_quality_score, "Max": 15.0},
                {"Component": "4. Supply-Chain Criticality (Max 15)", "Score": score_bd.supply_chain_criticality_score, "Max": 15.0},
                {"Component": "5. Margin & ROCE Quality (Max 10)", "Score": score_bd.margin_and_roce_score, "Max": 10.0},
                {"Component": "6. Balance Sheet Strength (Max 10)", "Score": score_bd.balance_sheet_strength_score, "Max": 10.0},
                {"Component": "7. Valuation Reasonableness (Max 10)", "Score": score_bd.valuation_reasonableness_score, "Max": 10.0},
            ]
        )
        st.dataframe(comp_df, use_container_width=True, hide_index=True)

        if score_bd.risk_flags:
            st.markdown("#### ⚠️ Active Risk Flags")
            for rf in score_bd.risk_flags:
                st.warning(f"**[{rf.severity.value}] {rf.code} ({rf.category}):** {rf.description}")
        else:
            st.success("No severe governance, balance-sheet, or liquidity risk flags triggered.")

    with col_memo:
        st.subheader("Structured Institutional Research Memo")
        news_items = repo.get_news_items(symbol=symbol)
        memo = generate_company_research_memo(sec, f, news_items=news_items)
        st.markdown(f"**Verdict:** `{memo.fact_vs_narrative_verdict}`")
        st.markdown(f"**Verified Business Exposure:** {memo.verified_business_exposure}")
        st.markdown("**Bull Case (Evidence-Backed):**")
        for b in memo.bull_case:
            st.markdown(f"- {b}")
        st.markdown("**Bear Case & Key Risks:**")
        for r in memo.bear_case_and_risks:
            st.markdown(f"- {r}")
        st.markdown("**Key Uncertainties & Missing History:**")
        for u in memo.key_uncertainties:
            st.markdown(f"- {u}")
        st.caption("Citations: " + " | ".join(memo.evidence_citations))

    st.divider()

    # Price & Technicals section
    st.subheader("📈 Price Action, Moving Averages (20/50/200 DMA) & Technical Regime")
    end_dt = date.today()
    start_dt = end_dt - timedelta(days=500)
    price_res = ingestion.get_or_generate_price_history(symbol, start_date=start_dt, end_date=end_dt)
    df_p = price_res.get("df")
    if df_p is not None and not df_p.empty:
        tech = compute_technical_indicators(df_p)
        t1, t2, t3, t4, t5, t6 = st.columns(6)
        t1.metric("Latest Close", f"{tech['latest_close']}", f"Regime: {tech['trend_regime']}")
        t2.metric("1M / 3M Return", f"{tech['return_1m_pct']}%", f"3M: {tech['return_3m_pct']}%")
        t3.metric("6M / 12M Return", f"{tech['return_6m_pct']}%", f"12M: {tech['return_12m_pct']}%")
        t4.metric("RSI(14) / ATR(14)", f"{tech['rsi_14']}", f"ATR: {tech['atr_14']}")
        t5.metric("Annualised Vol", f"{tech['annualised_vol_pct']}%", f"Max DD: {tech['max_drawdown_pct']}%")
        t6.metric("20D Avg Turnover", f"Rs {tech['avg_daily_turnover_20d_cr']} Cr", f"Source: {price_res['value_type']}")

        work = df_p.sort_values("trade_date").copy()
        work["DMA20"] = work["close"].rolling(20).mean()
        work["DMA50"] = work["close"].rolling(50).mean()
        work["DMA200"] = work["close"].rolling(200).mean()

        fig_p = go.Figure()
        fig_p.add_trace(go.Scatter(x=work["trade_date"], y=work["close"], name="Close", line=dict(width=2)))
        fig_p.add_trace(go.Scatter(x=work["trade_date"], y=work["DMA50"], name="50 DMA", line=dict(dash="dot")))
        fig_p.add_trace(go.Scatter(x=work["trade_date"], y=work["DMA200"], name="200 DMA", line=dict(dash="dash")))
        fig_p.update_layout(height=360, margin=dict(t=20, l=10, r=10, b=10))
        st.plotly_chart(fig_p, use_container_width=True)

    st.divider()
    with st.expander("📄 Interactive Filing & DRHP Fact-vs-Narrative Extractor"):
        default_sample = f.get("evidence_citation") or (
            "Company signed a non-binding MOU exploring potential AI data centre opportunities; no revenue recognized in FY25."
        )
        sample_text = st.text_area("Paste Annual Report, Investor Presentation, or DRHP Excerpt:", value=default_sample, height=100)
        if st.button("Extract & Verify Claims"):
            extracted = extract_facts_from_filing_text(symbol, sample_text)
            st.json(extracted.model_dump())


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
