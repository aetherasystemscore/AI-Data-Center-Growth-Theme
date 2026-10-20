"""Fundamental analysis engine covering growth, profitability, cash conversion, balance sheet, governance, and sector KPIs."""

from __future__ import annotations

from typing import Any


def evaluate_fundamental_health(f: dict[str, Any], sec: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate a company's fundamental profile while strictly preserving None for missing metrics.

    Newly listed companies lacking 5-year history are evaluated using available 3Y/1Y/listing-since metrics
    and flagged transparently rather than dropped or penalised with zeroes.
    """
    rev_cagr_3y = f.get("rev_cagr_3y_pct")
    rev_cagr_5y = f.get("rev_cagr_5y_pct")
    pat_cagr_3y = f.get("pat_cagr_3y_pct")
    ebitda_margin = f.get("ebitda_margin_pct")
    opm = f.get("operating_margin_pct")
    pat_margin = f.get("pat_margin_pct")
    roce = f.get("roce_pct")
    roe = f.get("roe_pct")
    roic = f.get("roic_pct")
    cfo_to_ebitda = f.get("cfo_to_ebitda_pct")
    fcf_cr = f.get("fcf_inr_cr")
    d_to_e = f.get("debt_to_equity")
    int_cov = f.get("interest_coverage")
    wc_days = f.get("working_capital_days")
    ob_to_sales = f.get("order_book_to_LTM_sales")
    promoter_pledge = f.get("promoter_pledge_pct")
    auditor_qual = bool(f.get("auditor_qualification_flag", False))

    missing_fields: list[str] = []
    for key in (
        "rev_cagr_3y_pct",
        "rev_cagr_5y_pct",
        "roce_pct",
        "roe_pct",
        "cfo_to_ebitda_pct",
        "debt_to_equity",
        "trailing_pe",
    ):
        if f.get(key) is None:
            missing_fields.append(key)

    is_newly_listed = rev_cagr_5y is None and rev_cagr_3y is not None
    effective_rev_growth = rev_cagr_3y if rev_cagr_3y is not None else rev_cagr_5y

    # Sub-scores (0 to 100 scale) computed only from available metrics
    growth_points: list[float] = []
    if effective_rev_growth is not None:
        growth_points.append(max(0.0, min(100.0, (effective_rev_growth + 8.0) * 2.6)))
    if pat_cagr_3y is not None:
        growth_points.append(max(0.0, min(100.0, (pat_cagr_3y + 8.0) * 2.4)))
    if ob_to_sales is not None and ob_to_sales > 0:
        growth_points.append(max(20.0, min(100.0, ob_to_sales * 42.0)))
    growth_score = round(sum(growth_points) / len(growth_points), 1) if growth_points else None

    profitability_points: list[float] = []
    if roce is not None:
        profitability_points.append(max(0.0, min(100.0, roce * 3.5)))
    if roe is not None:
        profitability_points.append(max(0.0, min(100.0, roe * 3.5)))
    if ebitda_margin is not None:
        profitability_points.append(max(0.0, min(100.0, ebitda_margin * 3.8)))
    profitability_score = (
        round(sum(profitability_points) / len(profitability_points), 1) if profitability_points else None
    )

    cash_points: list[float] = []
    if cfo_to_ebitda is not None:
        cash_points.append(max(0.0, min(100.0, cfo_to_ebitda * 1.15)))
    if wc_days is not None:
        cash_points.append(max(0.0, min(100.0, 100.0 - max(0.0, wc_days - 30.0) * 0.45)))
    if fcf_cr is not None and f.get("pat_inr_cr") not in (None, 0):
        pat_val = f["pat_inr_cr"]
        if pat_val > 0:
            fcf_conv = (fcf_cr / pat_val) * 100.0
            cash_points.append(max(10.0, min(100.0, fcf_conv)))
    cash_conversion_score = round(sum(cash_points) / len(cash_points), 1) if cash_points else None

    bs_points: list[float] = []
    if d_to_e is not None:
        if d_to_e <= 0.15:
            bs_points.append(95.0)
        elif d_to_e <= 0.5:
            bs_points.append(82.0)
        elif d_to_e <= 1.0:
            bs_points.append(65.0)
        elif d_to_e <= 2.0:
            bs_points.append(40.0)
        else:
            bs_points.append(10.0)
    if int_cov is not None:
        if int_cov >= 10.0:
            bs_points.append(95.0)
        elif int_cov >= 4.0:
            bs_points.append(75.0)
        elif int_cov >= 2.0:
            bs_points.append(50.0)
        else:
            bs_points.append(10.0)
    balance_sheet_score = round(sum(bs_points) / len(bs_points), 1) if bs_points else None

    gov_score = 85.0
    if promoter_pledge is not None and promoter_pledge > 0:
        gov_score -= min(50.0, promoter_pledge * 1.5)
    if auditor_qual:
        gov_score = min(gov_score, 15.0)
    gov_notes = (f.get("governance_notes") or "").lower()
    if "critical" in gov_notes or "regulatory action" in gov_notes or "shell" in gov_notes:
        gov_score = min(gov_score, 20.0)

    return {
        "symbol": f.get("symbol"),
        "is_newly_listed": is_newly_listed,
        "effective_rev_cagr_pct": effective_rev_growth,
        "growth_score": growth_score,
        "profitability_score": profitability_score,
        "cash_conversion_score": cash_conversion_score,
        "balance_sheet_score": balance_sheet_score,
        "governance_score": round(max(0.0, gov_score), 1),
        "missing_fields": missing_fields,
        "sector_kpi_summary": (
            f"{f.get('sector_kpi_name')}: {f.get('sector_kpi_value')} {f.get('sector_kpi_unit') or ''}".strip()
            if f.get("sector_kpi_name") and f.get("sector_kpi_value") is not None
            else None
        ),
        "opm_pct": opm,
        "pat_margin_pct": pat_margin,
        "roic_pct": roic,
    }
