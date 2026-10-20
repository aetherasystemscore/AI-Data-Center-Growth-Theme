"""Data validation, CSV import verification, stale-data detection, and source-conflict resolution."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from core.schemas import DataQualityStatus, TrackedValue


@dataclass
class ValidationResult:
    is_valid: bool
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    cleaned_data: Any = None


REQUIRED_SMALLCASE_CSV_COLUMNS = {"symbol", "weight_pct"}
REQUIRED_STOCK_CSV_COLUMNS = {"symbol", "company_name", "isin", "exchange", "primary_category"}

# Source hierarchy per Section 18 (1 = highest priority)
SOURCE_PRIORITY: Dict[str, int] = {
    "NSE_OFFICIAL_FILING": 1,
    "BSE_OFFICIAL_FILING": 1,
    "SEBI_RHP_DRHP": 2,
    "NSE_ANNUAL_REPORT_SEED": 3,
    "BSE_FILINGS_SEED": 3,
    "SEC_10K_SEED": 3,
    "SEC_20F_SEED": 3,
    "AMC_FACTSHEET_SEED": 4,
    "GOVERNMENT_CPCB_CEA": 5,
    "LICENSED_API": 6,
    "YFINANCE_LIVE": 7,
    "PUBLIC_THEME_REFERENCE": 7,
    "NEWS_CORROBORATION": 8,
    "SYNTHETIC_SAMPLE": 9,
}


def sanitize_missing_value(val: Any) -> Optional[float]:
    """Strictly convert missing, NaN, empty or invalid values to None. Never substitute zero."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if pd.isna(val):
            return None
        return float(val)
    s = str(val).strip()
    if not s or s.upper() in ("NULL", "NONE", "NAN", "NA", "N/A", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def validate_smallcase_csv(df: pd.DataFrame) -> Tuple[bool, List[str], pd.DataFrame]:
    """Validate a user-uploaded smallcase or custom basket CSV."""
    errors: List[str] = []
    if df is None or df.empty:
        return False, ["Uploaded CSV is empty."], pd.DataFrame()

    cols_lower = {c.strip().lower(): c for c in df.columns}
    missing = REQUIRED_SMALLCASE_CSV_COLUMNS - set(cols_lower.keys())
    if missing:
        return False, [f"Missing required columns: {', '.join(sorted(missing))}"], pd.DataFrame()

    cleaned_rows = []
    for idx, row in df.iterrows():
        sym = str(row[cols_lower["symbol"]]).strip().upper()
        wt = sanitize_missing_value(row[cols_lower["weight_pct"]])
        if not sym or " " in sym:
            errors.append(f"Row {idx + 1}: Invalid ticker symbol '{sym}'.")
            continue
        if wt is None or wt < 0 or wt > 100:
            errors.append(f"Row {idx + 1}: Invalid weight_pct '{row[cols_lower['weight_pct']]}' for {sym}.")
            continue
        cleaned_rows.append({"symbol": sym, "weight_pct": wt})

    out_df = pd.DataFrame(cleaned_rows)
    if not out_df.empty:
        out_df = out_df.groupby("symbol", as_index=False)["weight_pct"].sum()
        total_w = out_df["weight_pct"].sum()
        if total_w <= 0:
            errors.append("Total portfolio weight must be greater than 0%.")
    return len(errors) == 0, errors, out_df


def resolve_source_conflict(candidates: List[TrackedValue]) -> Optional[TrackedValue]:
    """Select the highest-priority non-missing TrackedValue and mark conflict resolution."""
    valid = [c for c in candidates if not c.is_missing]
    if not valid:
        return candidates[0] if candidates else None

    if len(valid) == 1:
        return valid[0]

    sorted_vals = sorted(
        valid,
        key=lambda x: (
            SOURCE_PRIORITY.get(x.source, 99),
            -(x.reporting_date.toordinal() if x.reporting_date else 0),
        ),
    )
    winner = sorted_vals[0].model_copy(deep=True)
    distinct_numbers = {round(v.value or 0.0, 4) for v in valid if v.value is not None}
    if len(distinct_numbers) > 1:
        winner.quality_status = DataQualityStatus.CONFLICT_RESOLVED
        other_sources = ", ".join(f"{v.source}={v.value}" for v in sorted_vals[1:])
        winner.transformation_applied = (
            f"Resolved source conflict in favour of {winner.source} over [{other_sources}]"
        )
    return winner


def check_staleness(
    reporting_Or_trade_date: Optional[date],
    max_age_days: int,
    reference_date: Optional[date] = None,
) -> Tuple[bool, int]:
    """Return (is_stale, age_in_days)."""
    if reporting_Or_trade_date is None:
        return True, 9999
    ref = reference_date or date.today()
    age = (ref - reporting_Or_trade_date).days
    return age > max_age_days, age


parse_optional_float = sanitize_missing_value


def ensure_missing_not_zero(record: Dict[str, Any], numeric_fields: List[str]) -> Dict[str, Any]:
    """Ensure missing numeric fields remain None rather than being coerced to 0."""
    out = dict(record)
    for f in numeric_fields:
        out[f] = sanitize_missing_value(out.get(f))
    return out


def validate_ohlcv_dataframe(df: pd.DataFrame, symbol: str) -> ValidationResult:
    """Validate OHLCV price dataframe for corrupt bars, negative prices, or missing columns."""
    errors: List[str] = []
    warnings: List[str] = []
    if df is None or df.empty:
        return ValidationResult(is_valid=False, errors=[f"Empty OHLCV dataframe for {symbol}"])

    required_cols = {"trade_date", "open", "high", "low", "close", "volume"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        return ValidationResult(
            is_valid=False,
            errors=[f"Missing required OHLCV columns for {symbol}: {sorted(missing_cols)}"],
        )

    clean = df.copy()
    clean = clean.drop_duplicates(subset=["trade_date"], keep="last").sort_values("trade_date")

    if (clean["close"] <= 0).any() or (clean["open"] <= 0).any():
        errors.append(f"Non-positive open/close prices detected for {symbol}")

    bad_hl = clean["high"] < clean["low"]
    if bad_hl.any():
        errors.append(f"High < Low detected on {int(bad_hl.sum())} bars for {symbol}")

    return ValidationResult(
        is_valid=len(errors) == 0,
        warnings=warnings,
        errors=errors,
        cleaned_data=clean,
    )


def validate_ipo_record(record: Dict[str, Any]) -> ValidationResult:
    """Validate IPO pipeline entry so unconfirmed dates are never presented as confirmed."""
    errors: List[str] = []
    warnings: List[str] = []
    dates_confirmed = bool(
        record.get("dates_confirmed", record.get("dates_confirmed_by_live_exchange", False))
    )
    if not dates_confirmed:
        for dt_field in ("issue_open_date", "issue_close_date", "listing_date"):
            if record.get(dt_field) is not None:
                errors.append(
                    f"IPO {record.get('ipo_id') or record.get('candidate_id')}: {dt_field} must be None when dates_confirmed=False"
                )
    return ValidationResult(
        is_valid=len(errors) == 0,
        warnings=warnings,
        errors=errors,
        cleaned_data=record,
    )

