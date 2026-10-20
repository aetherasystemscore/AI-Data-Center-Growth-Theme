"""Technical analysis and market liquidity filter module."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def compute_technical_indicators(
    df: pd.DataFrame,
    benchmark_df: pd.DataFrame | None = None,
    min_daily_turnover_cr: float = 2.0,
) -> dict[str, Any]:
    """Compute moving averages, multi-horizon returns, RSI(14), ATR(14), volatility, max drawdown, and liquidity checks."""
    if df is None or df.empty or "close" not in df.columns:
        return {
            "latest_close": None,
            "dma_20": None,
            "dma_50": None,
            "dma_200": None,
            "return_1m_pct": None,
            "return_3m_pct": None,
            "return_6m_pct": None,
            "return_12m_pct": None,
            "rsi_14": None,
            "atr_14": None,
            "annualised_vol_pct": None,
            "max_drawdown_pct": None,
            "rel_strength_6m_vs_benchmark_pct": None,
            "volume_breakout_ratio": None,
            "avg_daily_turnover_20d_cr": None,
            "passes_liquidity_filter": False,
            "trend_regime": "INSUFFICIENT_HISTORY",
        }

    work = df.sort_values("trade_date").reset_index(drop=True)
    close = work["close"].astype(float)
    high = work["high"].astype(float) if "high" in work.columns else close
    low = work["low"].astype(float) if "low" in work.columns else close
    vol = work["volume"].astype(float) if "volume" in work.columns else pd.Series(np.zeros(len(work)))
    turnover = (
        work["turnover_inr_cr"].astype(float)
        if "turnover_inr_cr" in work.columns
        else (close * vol) / 1e7
    )

    n = len(close)
    latest_close = float(close.iloc[-1])

    dma_20 = float(close.tail(20).mean()) if n >= 20 else None
    dma_50 = float(close.tail(50).mean()) if n >= 50 else None
    dma_200 = float(close.tail(200).mean()) if n >= 200 else None

    def _horizon_ret(bars: int) -> float | None:
        if n > bars and close.iloc[-1 - bars] > 0:
            return round(((latest_close / float(close.iloc[-1 - bars])) - 1.0) * 100.0, 2)
        return None

    ret_1m = _horizon_ret(21)
    ret_3m = _horizon_ret(63)
    ret_6m = _horizon_ret(126)
    ret_12m = _horizon_ret(252)

    # RSI(14)
    rsi_14: float | None = None
    if n >= 15:
        delta = close.diff()
        gain = delta.clip(lower=0.0).rolling(14).mean()
        loss = (-delta.clip(upper=0.0)).rolling(14).mean()
        last_gain = float(gain.iloc[-1])
        last_loss = float(loss.iloc[-1])
        if last_loss == 0:
            rsi_14 = 100.0
        else:
            rs = last_gain / last_loss
            rsi_14 = round(100.0 - (100.0 / (1.0 + rs)), 2)

    # ATR(14)
    atr_14: float | None = None
    if n >= 15:
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                (high - low).abs(),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr_14 = round(float(tr.rolling(14).mean().iloc[-1]), 2)

    # Annualised volatility & max drawdown
    daily_rets = close.pct_change().dropna()
    ann_vol: float | None = None
    if len(daily_rets) >= 20:
        ann_vol = round(float(daily_rets.std(ddof=1) * np.sqrt(252) * 100.0), 2)

    running_max = close.cummax()
    drawdowns = (close / running_max) - 1.0
    max_dd = round(float(drawdowns.min() * 100.0), 2) if n >= 2 else 0.0

    # Relative strength vs benchmark over 6M (126 trading days)
    rel_strength_6m: float | None = None
    if benchmark_df is not None and not benchmark_df.empty and ret_6m is not None:
        b_sorted = benchmark_df.sort_values("trade_date").reset_index(drop=True)
        if len(b_sorted) > 126 and float(b_sorted["close"].iloc[-127]) > 0:
            b_ret_6m = ((float(b_sorted["close"].iloc[-1]) / float(b_sorted["close"].iloc[-127])) - 1.0) * 100.0
            rel_strength_6m = round(ret_6m - b_ret_6m, 2)

    # Volume breakout ratio (last 5-day avg volume vs 50-day avg volume)
    vol_breakout: float | None = None
    if n >= 50 and float(vol.tail(50).mean()) > 0:
        vol_breakout = round(float(vol.tail(5).mean() / vol.tail(50).mean()), 2)

    avg_turnover_20d = round(float(turnover.tail(min(20, n)).mean()), 2)
    passes_liquidity = avg_turnover_20d >= min_daily_turnover_cr

    trend_regime = "NEUTRAL"
    if dma_50 is not None and dma_200 is not None:
        if latest_close > dma_50 > dma_200:
            trend_regime = "STRONG_UPTREND"
        elif latest_close < dma_50 < dma_200:
            trend_regime = "DOWNTREND"
        elif latest_close > dma_200:
            trend_regime = "CONSOLIDATING_ABOVE_200DMA"
        else:
            trend_regime = "BELOW_200DMA"

    return {
        "latest_close": round(latest_close, 2),
        "dma_20": round(dma_20, 2) if dma_20 is not None else None,
        "dma_50": round(dma_50, 2) if dma_50 is not None else None,
        "dma_200": round(dma_200, 2) if dma_200 is not None else None,
        "return_1m_pct": ret_1m,
        "return_3m_pct": ret_3m,
        "return_6m_pct": ret_6m,
        "return_12m_pct": ret_12m,
        "rsi_14": rsi_14,
        "atr_14": atr_14,
        "annualised_vol_pct": ann_vol,
        "max_drawdown_pct": max_dd,
        "rel_strength_6m_vs_benchmark_pct": rel_strength_6m,
        "volume_breakout_ratio": vol_breakout,
        "avg_daily_turnover_20d_cr": avg_turnover_20d,
        "passes_liquidity_filter": passes_liquidity,
        "trend_regime": trend_regime,
    }
