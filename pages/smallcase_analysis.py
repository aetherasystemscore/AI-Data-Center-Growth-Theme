"""Page 6: Smallcase & Thematic Basket Overlap Analyzer (Section 7 of the Master Project Prompt)."""

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

from data.ingestion import DataIngestionService
from database.repository import AI3Repository
from portfolio.overlap import (
    compare_smallcase_fee_vs_diy,
    compute_basket_overlap,
    compute_lookthrough_stock_exposure,
    parse_user_smallcase_csv,
)


def render(repo: AI3Repository, ingestion: DataIngestionService) -> None:
    st.title("🧺 Smallcase & Thematic Basket Overlap Analyzer")
    st.markdown(
        "Evaluate public and custom AI/Data-Centre smallcase portfolios, quantify constituent overlap against ETFs and direct stocks, "
        "and compare subscription/rebalance fee drag against DIY direct equity replication."
    )

    smallcases = repo.get_smallcases()
    etfs = repo.get_etfs()

    sc_rows = []
    for sc in smallcases:
        sc_rows.append(
            {
                "Smallcase ID": sc["smallcase_id"],
                "Name": sc["name"],
                "Manager / Creator": sc["manager_or_creator"],
                "Access Status": sc["access_type"],
                "Constituents Disclosed": "LOCKED (Requires CSV Upload)" if sc["constituents_locked"] else f"{len(sc['constituents'])} Stocks",
                "Rebalance Frequency": sc["rebalance_frequency"],
                "Annual Fee (Rs)": sc["subscription_fee_annual_inr"],
                "Min Investment (Rs)": sc["min_investment_inr"],
            }
        )
    st.subheader("Tracked Smallcase & Thematic Baskets")
    st.dataframe(pd.DataFrame(sc_rows), use_container_width=True, hide_index=True)

    st.info(
        "🔒 **Data Integrity Policy:** For subscription-locked commercial smallcases (such as *Niveshaay AI & TechStack*), "
        "AI3 **never** guesses or fabricates hidden constituents. Subscribers may upload their exported CSV below to unlock full overlap analysis."
    )

    with st.expander("📤 Upload Custom or Subscribed Smallcase Constituents (CSV)"):
        default_csv = (
            "symbol,weight_pct,role\n"
            "NETWEB,14.0,AI & HPC Servers\n"
            "HITACHIEN,14.0,HVDC & Data-Centre Substations\n"
            "CUMMINSIND,12.0,Backup Gensets\n"
            "BLUESTARCO,12.0,Precision Cooling\n"
            "POLYCAB,12.0,Power & Optical Cables\n"
            "KAYNES,12.0,EMS & OSAT\n"
            "ANANTRAJ,12.0,Colocation Data Centres\n"
            "PERSISTENT,12.0,AI Data Engineering"
        )
        csv_input = st.text_area("Paste `symbol,weight_pct,role` CSV:", value=default_csv, height=160)
        custom_name = st.text_input("Custom Smallcase Name", value="User Uploaded AI Smallcase")
        if st.button("Parse & Register Custom Smallcase in Session"):
            parsed = parse_user_smallcase_csv(csv_input)
            if parsed:
                st.session_state["user_custom_smallcase"] = {
                    "smallcase_id": "SC_USER_CUSTOM",
                    "name": custom_name,
                    "constituents_locked": False,
                    "constituents": parsed,
                }
                st.success(f"Loaded {len(parsed)} constituents for `{custom_name}`.")

    # Build dictionary of unlocked smallcases
    unlocked_scs = {
        sc["smallcase_id"]: {c["symbol"]: float(c["weight_pct"]) for c in sc["constituents"]}
        for sc in smallcases
        if not sc["constituents_locked"] and sc["constituents"]
    }
    if "user_custom_smallcase" in st.session_state:
        usc = st.session_state["user_custom_smallcase"]
        unlocked_scs[usc["smallcase_id"]] = {c["symbol"]: float(c["weight_pct"]) for c in usc["constituents"]}

    st.divider()
    st.subheader("1. Smallcase vs Smallcase / ETF Overlap Calculator")
    etf_baskets = {f"ETF:{e['symbol']}": e["top_constituents"] for e in etfs}
    combined_baskets = {**unlocked_scs, **etf_baskets}
    basket_names = list(combined_baskets.keys())

    if len(basket_names) >= 2:
        c1, c2 = st.columns(2)
        with c1:
            b_a = st.selectbox("Select Basket A (Smallcase or ETF)", basket_names, index=0)
        with c2:
            b_b = st.selectbox("Select Basket B (Smallcase or ETF)", basket_names, index=min(1, len(basket_names) - 1))

        ov = compute_basket_overlap(b_a, combined_baskets[b_a], b_b, combined_baskets[b_b])
        m1, m2, m3 = st.columns(3)
        m1.metric("Weighted Overlap (%)", f"{ov.weighted_overlap_pct}%")
        m2.metric("Jaccard Index", f"{ov.jaccard_similarity:.3f}")
        m3.metric("Shared Stocks", f"{ov.shared_symbols_count}")
        if ov.shared_symbols:
            st.dataframe(pd.DataFrame(ov.shared_symbols), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("2. Multi-Sleeve Look-Through Exposure (Direct Stocks + ETFs + Smallcases)")
    sample_lookthrough = compute_lookthrough_stock_exposure(
        direct_stock_weights={"NETWEB": 10.0, "HITACHIEN": 10.0, "CUMMINSIND": 10.0},
        etf_allocations={"NIFTYBEES": 25.0, "ITBEES": 15.0},
        smallcase_allocations={"SC_AI_DC_VALUE_CHAIN": 30.0},
        etf_constituents_map={e["symbol"]: e["top_constituents"] for e in etfs},
        smallcase_constituents_map=unlocked_scs,
    )
    st.dataframe(pd.DataFrame(sample_lookthrough[:20]), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("3. Smallcase Subscription Fee & Churn Drag vs DIY Replication Calculator")
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        inv_amt = st.number_input("Investment Capital (Rs)", min_value=50000.0, value=300000.0, step=50000.0)
    with fc2:
        sub_fee = st.number_input("Annual Subscription Fee (Rs)", min_value=0.0, value=7000.0, step=1000.0)
    with fc3:
        gross_cagr = st.slider("Expected Gross CAGR (%)", 8.0, 30.0, 18.0, 1.0)
    with fc4:
        horizon_yrs = st.slider("Holding Horizon (Years)", 1, 10, 5)

    comp = compare_smallcase_fee_vs_diy(
        investment_amount_inr=inv_amt,
        subscription_fee_annual_inr=sub_fee,
        expected_gross_cagr_pct=gross_cagr,
        horizon_years=horizon_yrs,
    )
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Annual Subscription Fee Drag", f"{comp['annual_fee_drag_pct']}% / yr")
    k2.metric("Smallcase Net CAGR", f"{comp['smallcase_net_cagr_pct']}%")
    k3.metric("DIY Direct Replication Net CAGR", f"{comp['diy_net_cagr_pct']}%")
    k4.metric(f"{horizon_yrs}Y Cumulative DIY Savings", f"Rs {comp['cumulative_cost_savings_diy_inr']:,.0f}")


if __name__ in ("__main__", "__page__"):
    from core.page_bootstrap import run_standalone_page

    run_standalone_page(render)
