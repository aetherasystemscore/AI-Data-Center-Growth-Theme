"""Corporate actions adjustment engine for stock splits, bonus issues, and cash dividends."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List
import pandas as pd


@dataclass
class CorporateActionEvent:
    symbol: str
    ex_date: date
    action_type: str  # "SPLIT", "BONUS", "DIVIDEND"
    ratio_numerator: float = 1.0  # e.g., 5 for a 5-for-1 split, or 2 for a 1:1 bonus (new shares per old share = 2/1)
    ratio_denominator: float = 1.0
    cash_dividend: float = 0.0


def compute_split_adjustment_factor(numerator: float, denominator: float) -> float:
    """Return backward price multiplier for a stock split (e.g., 1 old -> 5 new => 1/5 = 0.20)."""
    if numerator <= 0 or denominator <= 0:
        return 1.0
    return float(denominator) / float(numerator)


def compute_bonus_adjustment_factor(bonus_shares: float, existing_shares: float) -> float:
    """Return backward price multiplier for a bonus issue (e.g., 1:1 bonus => 1/(1+1) = 0.50)."""
    if bonus_shares < 0 or existing_shares <= 0:
        return 1.0
    return float(existing_shares) / float(existing_shares + bonus_shares)


def apply_corporate_actions_to_prices(
    price_df: pd.DataFrame, actions: List[CorporateActionEvent]
) -> pd.DataFrame:
    """Adjust historical OHLCV prices prior to each corporate action's ex_date."""
    if price_df.empty:
        return price_df.copy()

    df = price_df.sort_values("trade_date").copy()
    close_col = "close_price" if "close_price" in df.columns else "close"
    open_col = "open_price" if "open_price" in df.columns else "open"
    high_col = "high_price" if "high_price" in df.columns else "high"
    low_col = "low_price" if "low_price" in df.columns else "low"

    if "adj_close" not in df.columns:
        df["adj_close"] = df[close_col].astype(float)
    else:
        df["adj_close"] = df["adj_close"].astype(float)

    df["adj_open"] = df.get(open_col, df[close_col]).astype(float)
    df["adj_high"] = df.get(high_col, df[close_col]).astype(float)
    df["adj_low"] = df.get(low_col, df[close_col]).astype(float)
    df["adj_volume"] = df.get("volume", pd.Series(0.0, index=df.index)).astype(float)

    sorted_actions = sorted(actions, key=lambda a: a.ex_date, reverse=True)
    for act in sorted_actions:
        mask_prior = pd.to_datetime(df["trade_date"]).dt.date < act.ex_date
        if not mask_prior.any():
            continue

        if act.action_type.upper() == "SPLIT":
            mult = compute_split_adjustment_factor(act.ratio_numerator, act.ratio_denominator)
            if mult > 0 and mult != 1.0:
                df.loc[mask_prior, "adj_close"] *= mult
                df.loc[mask_prior, "adj_open"] *= mult
                df.loc[mask_prior, "adj_high"] *= mult
                df.loc[mask_prior, "adj_low"] *= mult
                df.loc[mask_prior, "adj_volume"] /= mult
        elif act.action_type.upper() == "BONUS":
            mult = compute_bonus_adjustment_factor(act.ratio_numerator, act.ratio_denominator)
            if mult > 0 and mult != 1.0:
                df.loc[mask_prior, "adj_close"] *= mult
                df.loc[mask_prior, "adj_open"] *= mult
                df.loc[mask_prior, "adj_high"] *= mult
                df.loc[mask_prior, "adj_low"] *= mult
                df.loc[mask_prior, "adj_volume"] /= mult
        elif act.action_type.upper() == "DIVIDEND" and act.cash_dividend > 0:
            prior_closes = df.loc[mask_prior, "adj_close"]
            if not prior_closes.empty:
                ref_close = float(prior_closes.iloc[-1])
                if ref_close > act.cash_dividend:
                    div_factor = (ref_close - act.cash_dividend) / ref_close
                    df.loc[mask_prior, "adj_close"] *= div_factor
                    df.loc[mask_prior, "adj_open"] *= div_factor
                    df.loc[mask_prior, "adj_high"] *= div_factor
                    df.loc[mask_prior, "adj_low"] *= div_factor

    return df


apply_point_in_time_adjustments = apply_corporate_actions_to_prices

