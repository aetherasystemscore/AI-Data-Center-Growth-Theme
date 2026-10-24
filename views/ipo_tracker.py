"""Page 7: IPO, DRHP, RHP & Newly Listed Company Tracker (Section 8 of the Master Project Prompt)."""

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

from analytics.equity_enrichment import compute_enriched_equity_metrics
from data.ingestion import DataIngestionService
from data.validation import validate_ipo_record
from database.repository import AI3Repository
from jobs.discover_ipos import run_discover_ipos


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("🚀 IPO, DRHP, RHP & Newly Listed AI Infrastructure Tracker")
    st.markdown(
        "Evaluate Mainboard and SME IPO candidates, DRHP/RHP filings, Objects of the Issue (productive capex vs OFS), "
        "restated financials, and newly listed AI/component companies (<3 years on exchange)."
    )

    ipos = repo.get_ipos()
    all_secs = repo.get_securities(geography="INDIA")
    f_map = repo.get_latest_fundamentals_map()

    st.subheader("1. Pre-IPO, DRHP & RHP Filing Pipeline")
    st.info(
        "🛡️ **Strict Date Integrity Rule:** Unconfirmed IPO opening, closing, or listing dates are **always** displayed as "
        "`UNCONFIRMED / TBA` and never fabricated."
    )

    ipo_summary = []
    for ipo in ipos:
        val_check = validate_ipo_record(ipo)
        dates_confirmed = bool(ipo.get("dates_confirmed", False))
        ipo_summary.append(
            {
                "IPO ID": ipo["ipo_id"],
                "Company": ipo["company_name"],
                "Board": ipo["board_type"],
                "Filing Stage": ipo["filing_stage"],
                "Issue Open Date": ipo["issue_open_date"] if (dates_confirmed and ipo["issue_open_date"]) else "UNCONFIRMED / TBA",
                "Listing Date": ipo["listing_date"] if (dates_confirmed and ipo["listing_date"]) else "UNCONFIRMED / TBA",
                "Fresh Issue (Rs Cr)": ipo["fresh_issue_inr_cr"] if ipo["fresh_issue_inr_cr"] is not None else "TBA",
                "OFS (Rs Cr)": ipo["ofs_inr_cr"] if ipo["ofs_inr_cr"] is not None else "TBA",
                "Productive Capex + Debt Paydown (%)": ipo["productive_capex_and_debt_repayment_pct"],
                "OFS Share of Issue (%)": ipo["ofs_share_of_total_issue_pct"],
                "AI Relevance Score (100)": ipo["ai_infrastructure_relevance_score"],
                "Validation Status": "VALID" if val_check.is_valid else "INVALID",
            }
        )
    df_ipo = pd.DataFrame(ipo_summary)
    st.dataframe(df_ipo, use_container_width=True, hide_index=True)

    ipo_b1, ipo_b2 = st.columns([1.5, 2.5])
    ipo_b1.download_button(
        "📥 Export IPO & DRHP Pipeline (CSV)",
        data=df_ipo.to_csv(index=False).encode("utf-8"),
        file_name="ai3_ipo_drhp_pipeline.csv",
        mime="text/csv",
        use_container_width=True,
    )
    if ipo_b2.button("🔍 Scan Live SEBI DRHP/RHP Feed & Update Pipeline", type="primary"):
        with st.spinner("Scanning SEBI DRHP/RHP pipeline & verifying IPO date guards..."):
            res = run_discover_ipos(repo)
            st.success(res.get("message", "IPO pipeline verified."))
            st.rerun()

    st.subheader("Deep-Dive DRHP / RHP Filing Inspector")
    ipo_by_id = {i["ipo_id"]: i for i in ipos}
    sel_ipo_id = st.selectbox(
        "Select IPO Candidate",
        options=list(ipo_by_id.keys()),
        format_func=lambda k: f"{ipo_by_id[k]['company_name']} ({ipo_by_id[k]['filing_stage']})",
    )
    sel_ipo = ipo_by_id[sel_ipo_id]

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(f"### {sel_ipo['company_name']} (`{sel_ipo['ipo_id']}`)")
        st.markdown(f"**Value-Chain Role:** {sel_ipo['value_chain_role']}")
        st.markdown(f"**Sector Tags:** `{', '.join(sel_ipo['sector_tags'])}`")
        st.markdown(f"**Listed Peer Comparisons:** `{', '.join(sel_ipo['peer_comparison_tickers'])}`")
        st.markdown("#### Objects of the Issue Breakdown")
        obj_df = pd.DataFrame(sel_ipo["objects_of_issue"])
        st.dataframe(obj_df, use_container_width=True, hide_index=True)

    with c2:
        st.markdown("#### Restated Financials & Filing Risk Flags")
        st.json(sel_ipo["restated_financials"])
        for rf in sel_ipo["risk_flags"]:
            st.warning(f"**Filing Flag:** `{rf}`")
        st.caption(f"Source: `{sel_ipo['source_name']}` ({sel_ipo['value_type']})")

    st.divider()
    st.subheader("2. Newly Listed AI & Component Equities (< 3–5 Years Listed History)")
    st.caption(
        "Newly listed companies lacking 5-year revenue CAGR history are retained with `5Y Rev CAGR = None` "
        "and evaluated on 3Y / since-listing metrics."
    )
    recent_rows = []
    for sec in all_secs:
        f = f_map.get(sec["symbol"], {})
        ld = sec.get("listing_date") or ""
        if ld >= "2022-01-01" or f.get("rev_cagr_5y_pct") is None:
            enr = compute_enriched_equity_metrics(sec, f)
            recent_rows.append(
                {
                    "Symbol": sec["symbol"],
                    "Company": sec["company_name"],
                    "Exchange": sec["exchange"],
                    "Listing Date": ld or "N/A",
                    "Live CMP (Rs)": enr["cmp"],
                    "1Y Return (%)": enr["return_1y_pct"],
                    "Primary Category": sec["primary_category"],
                    "Investable": sec["is_investable"],
                    "3Y Rev CAGR (%)": f.get("rev_cagr_3y_pct"),
                    "5Y Rev CAGR (%)": f.get("rev_cagr_5y_pct"),  # Preserved as None/NaN when <5Y history
                    "ROCE (%)": f.get("roce_pct"),
                    "Trailing P/E": f.get("trailing_pe"),
                    "Direct AI/DC Rev (%)": f.get("direct_ai_dc_rev_share_pct"),
                }
            )
    st.dataframe(pd.DataFrame(recent_rows), use_container_width=True, hide_index=True)


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
