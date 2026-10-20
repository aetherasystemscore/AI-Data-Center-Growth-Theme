"""Market price and volume history provider (yfinance live adapter + deterministic baseline generator)."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from core.config import get_settings
from core.logging_config import get_logger
from data.providers.base import BasePriceProvider, ProviderPayload

logger = get_logger(__name__)


def _exchange_to_yf_suffix(exchange: str, symbol: str) -> str:
    ex = exchange.upper()
    if ex in ("NSE", "NSE_SME"):
        return f"{symbol}.NS"
    if ex == "BSE":
        return f"{symbol}.BO"
    if ex == "TWSE":
        return f"{symbol}.TW"
    if ex == "TSE":
        return f"{symbol}.T"
    if ex == "KRX":
        return f"{symbol}.KS"
    if ex == "XETRA":
        return f"{symbol}.DE"
    if ex == "EURONEXT":
        return f"{symbol}.PA"
    return symbol


class HybridPriceProvider(BasePriceProvider):
    """Fetches historical OHLCV data via yfinance when online or generates deterministic baseline series anchored to reference prices."""

    def __init__(self, base_prices: dict[str, float] | None = None) -> None:
        self.settings = get_settings()
        self.base_prices = base_prices or {}

    def fetch_price_history(
        self,
        symbol: str,
        exchange: str,
        start_date: date,
        end_date: date,
        listing_date: date | None = None,
        reference_price: float | None = None,
        annual_return_hint_pct: float | None = None,
        volatility_hint_pct: float | None = None,
        avg_daily_turnover_cr: float | None = None,
    ) -> ProviderPayload:
        """Fetch OHLCV history with point-in-time listing date enforcement."""
        effective_start = max(start_date, listing_date) if listing_date else start_date
        if effective_start > end_date:
            return ProviderPayload(
                data=pd.DataFrame(),
                source_name="NO_PRE_LISTING_DATA",
                value_type="ACTUAL",
                is_live=False,
                warnings=[f"{symbol} was not listed between {start_date} and {end_date}."],
            )

        if self.settings.data_mode == "LIVE":
            try:
                import yfinance as yf

                yf_ticker = _exchange_to_yf_suffix(exchange, symbol)
                df = yf.download(
                    yf_ticker,
                    start=effective_start.isoformat(),
                    end=(end_date + timedelta(days=1)).isoformat(),
                    progress=False,
                    auto_adjust=False,
                    timeout=8,
                )
                if df is not None and not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = [c[0] for c in df.columns]
                    out = pd.DataFrame()
                    out["trade_date"] = pd.to_datetime(df.index).date
                    out["open"] = df["Open"].astype(float).values
                    out["high"] = df["High"].astype(float).values
                    out["low"] = df["Low"].astype(float).values
                    out["close"] = df["Close"].astype(float).values
                    out["adj_close"] = (
                        df["Adj Close"].astype(float).values
                        if "Adj Close" in df.columns
                        else df["Close"].astype(float).values
                    )
                    out["volume"] = df["Volume"].fillna(0).astype(float).values
                    out["turnover_inr_cr"] = (out["close"] * out["volume"]) / 1e7
                    out["adjustment_factor"] = out["adj_close"] / out["close"].replace(0, np.nan)
                    out["adjustment_factor"] = out["adjustment_factor"].fillna(1.0)
                    out["source_name"] = "YFINANCE_LIVE"
                    out["value_type"] = "ACTUAL_MARKET_CLOSE"
                    return ProviderPayload(
                        data=out,
                        source_name="YFINANCE_LIVE",
                        source_url=f"https://finance.yahoo.com/quote/{yf_ticker}",
                        value_type="ACTUAL_MARKET_CLOSE",
                        is_live=True,
                    )
            except Exception as exc:
                logger.warning("Live yfinance fetch failed for %s (%s); using reference baseline.", symbol, exc)

        # Deterministic baseline price generator anchored to reference_price on end_date
        df_synth = self._generate_seeded_ohlcv(
            symbol=symbol,
            start_date=effective_start,
            end_date=end_date,
            end_price=reference_price or self.base_prices.get(symbol, 1000.0),
            annual_drift_pct=annual_return_hint_pct if annual_return_hint_pct is not None else 18.0,
            annual_vol_pct=volatility_hint_pct if volatility_hint_pct is not None else 28.0,
            avg_daily_turnover_cr=avg_daily_turnover_cr if avg_daily_turnover_cr is not None else 25.0,
        )
        return ProviderPayload(
            data=df_synth,
            source_name="SEED_REFERENCE_PRICE_MODEL",
            source_url="config/sample_fundamentals_synthetic.csv",
            value_type="SYNTHETIC_SAMPLE_CALIBRATED",
            is_live=False,
        )

    @staticmethod
    def _generate_seeded_ohlcv(
        symbol: str,
        start_date: date,
        end_date: date,
        end_price: float,
        annual_drift_pct: float = 18.0,
        annual_vol_pct: float = 28.0,
        avg_daily_turnover_cr: float = 25.0,
    ) -> pd.DataFrame:
        """Generate reproducible business-day OHLCV series ending at `end_price` on `end_date`."""
        b_days = pd.bdate_range(start=start_date, end=end_date)
        n = len(b_days)
        if n == 0:
            return pd.DataFrame()

        seed_int = int(hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed_int)

        dt = 1.0 / 252.0
        mu = (annual_drift_pct / 100.0) * dt
        sigma = (annual_vol_pct / 100.0) * np.sqrt(dt)

        # Market factor (deterministic common seed so stocks have realistic correlation)
        mkt_rng = np.random.default_rng(20260331)
        # Generate a long market factor from 2018-01-01 to 2027-12-31 and slice by date
        full_calendar = pd.bdate_range(start="2018-01-01", end="2027-12-31")
        mkt_shocks_all = mkt_rng.normal(0.0004, 0.009, size=len(full_calendar))
        mkt_series = pd.Series(mkt_shocks_all, index=full_calendar)
        common_shock = mkt_series.reindex(b_days).fillna(0.0).values

        idio_shock = rng.normal(mu * 0.6, sigma * 0.85, size=n)
        daily_log_ret = 0.45 * common_shock + idio_shock
        daily_log_ret[-1] = 0.0

        # Work backwards from end_price so the final close matches reference_price
        rev_cum = np.cumsum(daily_log_ret[::-1])[::-1]
        close = end_price * np.exp(-rev_cum)
        close[-1] = end_price
        close = np.maximum(close, 1.0)

        intraday_spread = np.abs(rng.normal(0.012, 0.006, size=n))
        open_p = close * (1.0 + rng.normal(0.0, 0.005, size=n))
        high_p = np.maximum(open_p, close) * (1.0 + intraday_spread)
        low_p = np.minimum(open_p, close) * np.maximum(0.5, 1.0 - intraday_spread)

        vol_mult = rng.lognormal(mean=0.0, sigma=0.35, size=n)
        turnover_cr = np.maximum(0.001, avg_daily_turnover_cr * vol_mult)
        volume = np.maximum(1.0, (turnover_cr * 1e7) / close)

        df = pd.DataFrame(
            {
                "trade_date": [d.date() for d in b_days],
                "open": np.round(open_p, 2),
                "high": np.round(high_p, 2),
                "low": np.round(low_p, 2),
                "close": np.round(close, 2),
                "adj_close": np.round(close, 2),
                "volume": np.round(volume, 0),
                "turnover_inr_cr": np.round(turnover_cr, 3),
                "adjustment_factor": 1.0,
                "source_name": "SEED_REFERENCE_PRICE_MODEL",
                "value_type": "SYNTHETIC_SAMPLE_CALIBRATED",
            }
        )
        return df
