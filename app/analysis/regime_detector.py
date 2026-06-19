from typing import Optional

import numpy as np
import pandas as pd

from app.analysis.indicators import calc_atr, calc_ema


def _atr_percentile(df: pd.DataFrame, period: int = 14) -> float:
    atr = calc_atr(df, period)
    if atr is None or len(atr.dropna()) < 50:
        return 50.0
    atr_clean = atr.dropna()
    latest = float(atr_clean.iloc[-1])
    lookback = atr_clean.iloc[-50:]
    if len(lookback) == 0 or lookback.max() == lookback.min():
        return 50.0
    percentile = (latest - lookback.min()) / (lookback.max() - lookback.min()) * 100.0
    return round(float(np.clip(percentile, 0.0, 100.0)), 1)


def _ema_alignment_score(df: pd.DataFrame) -> float:
    if df is None or len(df) < 50:
        return 0.0
    close = df["close"].astype(float)
    ema_20 = calc_ema(df, 20)
    ema_50 = calc_ema(df, 50)

    if ema_20.dropna().empty or ema_50.dropna().empty:
        return 0.0

    e20 = float(ema_20.iloc[-1])
    e50 = float(ema_50.iloc[-1])
    price = float(close.iloc[-1])

    if pd.isna(e20) or pd.isna(e50):
        return 0.0

    score = 0.0
    if price > e20:
        score += 1.0
    if e20 > e50:
        score += 1.0
    if ema_20.iloc[-1] > ema_20.iloc[-5]:
        score += 0.5
    return score / 2.5


def _price_range_contraction(df: pd.DataFrame, window: int = 10, lookback: int = 30) -> float:
    if df is None or len(df) < lookback:
        return 1.0
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    recent_range = high.iloc[-window:].max() - low.iloc[-window:].min()
    prior_range = high.iloc[-lookback:-window].max() - low.iloc[-lookback:-window].min()
    if prior_range == 0:
        return 1.0
    return float(recent_range / prior_range)


def detect_market_regime(
    df_h4: Optional[pd.DataFrame],
    df_h1: Optional[pd.DataFrame],
    df_m15: Optional[pd.DataFrame],
) -> dict:
    result = {
        "regime": "UNCLEAR",
        "description": "Insufficient data for regime detection.",
        "atr_percentile": 50.0,
    }

    if df_h1 is None or len(df_h1) < 50:
        return result

    if df_h4 is None or len(df_h4) < 30:
        df_h4 = df_h1

    if df_m15 is None or len(df_m15) < 50:
        df_m15 = df_h1

    atr_pct = _atr_percentile(df_h1, 14)
    result["atr_percentile"] = atr_pct

    alignment_h4 = _ema_alignment_score(df_h4)
    alignment_h1 = _ema_alignment_score(df_h1)
    alignment_m15 = _ema_alignment_score(df_m15)
    avg_alignment = (alignment_h4 + alignment_h1 + alignment_m15) / 3.0

    contraction = _price_range_contraction(df_h1, 10, 30)

    if atr_pct > 80:
        regime = "HIGH_VOLATILITY"
        desc = "ATR in upper 20th percentile. Elevated volatility across timeframes."
    elif atr_pct < 20:
        regime = "LOW_VOLATILITY"
        desc = "ATR in lower 20th percentile. Subdued volatility."
    elif avg_alignment > 0.5:
        close = df_h1["close"].astype(float)
        ema_20 = calc_ema(df_h1, 20)
        price = float(close.iloc[-1])
        e20 = float(ema_20.iloc[-1]) if not ema_20.dropna().empty else price
        if price > e20:
            regime = "TRENDING_UP"
            desc = "Bullish alignment across timeframes. Uptrend in force."
        else:
            regime = "TRENDING_DOWN"
            desc = "Bearish alignment across timeframes. Downtrend in force."
    elif contraction < 0.5 and atr_pct > 50:
        regime = "BREAKOUT"
        desc = f"Price range contracted to {contraction:.0%} of prior. Potential breakout."
    elif contraction > 1.5 and atr_pct > 60:
        regime = "BREAKOUT"
        desc = f"Price range expanded {contraction:.0%} vs prior. Breakout in progress."
    elif avg_alignment < 0.3:
        regime = "RANGING"
        desc = "Mixed EMA alignment across timeframes. Sideways price action."
    elif atr_pct > 70 and avg_alignment > 0.3:
        regime = "REVERSAL"
        desc = "Elevated volatility with weak trend alignment. Possible reversal."
    else:
        regime = "RANGING"
        desc = "No strong signal. Price consolidating."

    result["regime"] = regime
    result["description"] = desc
    return result
