from typing import Optional

import numpy as np
import pandas as pd


def detect_support_resistance(
    df: pd.DataFrame, window: int = 10, n_levels: int = 3
) -> dict:
    result = {"support": [], "resistance": []}
    if df is None or len(df) < window:
        return result

    close = df["close"].astype(float).values
    n = len(close)

    support_levels = []
    resistance_levels = []
    for i in range(window, n - window):
        slice_ = close[i - window : i + window + 1]
        center = close[i]
        if center == slice_.min():
            support_levels.append((i, center))
        if center == slice_.max():
            resistance_levels.append((i, center))

    support_levels.sort(key=lambda x: x[0], reverse=True)
    resistance_levels.sort(key=lambda x: x[0], reverse=True)

    result["support"] = [float(level) for _, level in support_levels[:n_levels]]
    result["resistance"] = [float(level) for _, level in resistance_levels[:n_levels]]
    return result


def detect_trend(df: pd.DataFrame, bias_tf_df: Optional[pd.DataFrame] = None) -> dict:
    result = {
        "direction": "UNCLEAR",
        "strength": 0.0,
        "ema_20": None,
        "ema_50": None,
    }

    if df is None or len(df) < 50:
        return result

    close = df["close"].astype(float)
    price = close.iloc[-1]

    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()

    latest_ema_20 = float(ema_20.iloc[-1])
    latest_ema_50 = float(ema_50.iloc[-1])

    if pd.isna(latest_ema_20) or pd.isna(latest_ema_50):
        return result

    result["ema_20"] = latest_ema_20
    result["ema_50"] = latest_ema_50

    if price > latest_ema_20 > latest_ema_50:
        direction = "BULLISH"
    elif price < latest_ema_20 < latest_ema_50:
        direction = "BEARISH"
    else:
        direction = "UNCLEAR"

    result["direction"] = direction

    ema_slope_20 = (ema_20.iloc[-1] - ema_20.iloc[-6]) / abs(ema_20.iloc[-6]) if abs(ema_20.iloc[-6]) > 0 else 0.0
    ema_slope_50 = (ema_50.iloc[-1] - ema_50.iloc[-6]) / abs(ema_50.iloc[-6]) if abs(ema_50.iloc[-6]) > 0 else 0.0

    separation = abs(latest_ema_20 - latest_ema_50) / latest_ema_50 if latest_ema_50 > 0 else 0.0
    slope_factor = min(abs(ema_slope_20) * 50 + abs(ema_slope_50) * 30, 0.5)
    strength = min(separation * 5 + slope_factor, 1.0)

    if direction == "UNCLEAR":
        strength *= 0.3

    result["strength"] = round(strength, 4)
    return result


def detect_market_structure(df: pd.DataFrame) -> dict:
    result = {
        "regime": "UNCLEAR",
    }

    if df is None or len(df) < 50:
        return result

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    price = close.iloc[-1]

    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()

    latest_ema_20 = float(ema_20.iloc[-1])
    latest_ema_50 = float(ema_50.iloc[-1])

    if pd.isna(latest_ema_20) or pd.isna(latest_ema_50):
        return result

    lookback = min(20, len(df) - 1)
    highest = high.iloc[-lookback:].max()
    lowest = low.iloc[-lookback:].min()
    price_range = highest - lowest

    if price_range == 0:
        return result

    price_position = (price - lowest) / price_range

    true_range = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_14 = true_range.ewm(alpha=1 / 14, adjust=False).mean()
    latest_atr = float(atr_14.iloc[-1])
    avg_atr_50 = float(atr_14.iloc[-50:].mean()) if len(atr_14) >= 50 else latest_atr

    if pd.isna(latest_atr) or pd.isna(avg_atr_50) or avg_atr_50 == 0:
        return result

    atr_ratio = latest_atr / avg_atr_50

    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)

    atr_series = true_range.ewm(alpha=1 / 14, adjust=False).mean()
    plus_di = 100.0 * (plus_dm.ewm(alpha=1 / 14, adjust=False).mean() / atr_series.replace(0, np.nan))
    minus_di = 100.0 * (-minus_dm.ewm(alpha=1 / 14, adjust=False).mean() / atr_series.replace(0, np.nan))

    latest_plus_di = float(plus_di.iloc[-1])
    latest_minus_di = float(minus_di.iloc[-1])

    if pd.isna(latest_plus_di) or pd.isna(latest_minus_di):
        return result

    dx = abs(latest_plus_di - latest_minus_di) / (latest_plus_di + latest_minus_di) if (latest_plus_di + latest_minus_di) > 0 else 0.0

    if atr_ratio > 1.5:
        regime = "BREAKOUT"
    elif dx > 0.2 and price > latest_ema_20 and latest_ema_20 > latest_ema_50:
        regime = "TRENDING_UP"
    elif dx > 0.2 and price < latest_ema_20 and latest_ema_20 < latest_ema_50:
        regime = "TRENDING_DOWN"
    elif dx < 0.1:
        regime = "RANGING"
    elif price > latest_ema_20 > latest_ema_50:
        regime = "TRENDING_UP"
    elif price < latest_ema_20 < latest_ema_50:
        regime = "TRENDING_DOWN"
    else:
        regime = "RANGING"

    result["regime"] = regime
    return result
