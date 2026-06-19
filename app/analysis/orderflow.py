from typing import Optional

import numpy as np
import pandas as pd


def calc_tick_imbalance(df: pd.DataFrame, period_minutes: int = 1) -> pd.Series:
    if df is None or len(df) == 0:
        return pd.Series(dtype=float)

    df = df.copy()
    df["time"] = pd.to_datetime(df["time"])
    df.set_index("time", inplace=True)

    close_ser = df["close"].astype(float)
    open_ser = df["open"].astype(float)
    is_up = (close_ser > open_ser).astype(int)
    is_down = (close_ser < open_ser).astype(int)

    period_str = f"{period_minutes}T"
    up_count = is_up.resample(period_str).sum()
    down_count = is_down.resample(period_str).sum()
    total = up_count + down_count

    imbalance = pd.Series(np.where(total > 0, (up_count - down_count) / total, 0.0), index=total.index)
    return imbalance


def calc_delta_proxy(df: pd.DataFrame) -> dict:
    result = {
        "cumulative_delta": 0.0,
        "latest_period_delta": 0.0,
        "delta_signal": "NEUTRAL",
    }

    if df is None or len(df) == 0:
        return result

    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    volume = df.get("tick_volume", pd.Series(1, index=df.index)).astype(float)

    direction = np.where(close > open_, 1, np.where(close < open_, -1, 0))
    delta = direction * volume

    result["cumulative_delta"] = float(delta.sum())

    recent = delta.iloc[-min(5, len(delta)):]
    result["latest_period_delta"] = float(recent.sum())

    if result["latest_period_delta"] > 0:
        result["delta_signal"] = "BUYING"
    elif result["latest_period_delta"] < 0:
        result["delta_signal"] = "SELLING"

    return result


def analyze_spread(df: pd.DataFrame) -> dict:
    result = {
        "status": "NORMAL",
        "current_spread_points": 0,
        "avg_spread_points": 0.0,
        "max_spread_points": 0,
    }

    if df is None or len(df) == 0 or "spread" not in df.columns:
        return result

    spread = df["spread"].astype(float).dropna()
    if len(spread) == 0:
        return result

    current = int(spread.iloc[-1])
    avg = float(spread.mean())
    max_spread = int(spread.max())

    result["current_spread_points"] = current
    result["avg_spread_points"] = round(avg, 2)
    result["max_spread_points"] = max_spread

    if avg > 0:
        ratio = current / avg
        if ratio > 3.0:
            result["status"] = "VERY_WIDE"
        elif ratio > 1.8:
            result["status"] = "WIDE"

    return result


def dom_imbalance_proxy(depth_data: Optional[list]) -> dict:
    result = {
        "bid_volume": 0.0,
        "ask_volume": 0.0,
        "imbalance_ratio": 0.0,
        "signal": "NO_DATA",
    }

    if not depth_data or len(depth_data) == 0:
        return result

    total_bid_vol = 0.0
    total_ask_vol = 0.0

    for level in depth_data:
        if isinstance(level, dict):
            vol = float(level.get("volume", 0))
            if level.get("type") == 0 or level.get("type") == "bid":
                total_bid_vol += vol
            elif level.get("type") == 1 or level.get("type") == "ask":
                total_ask_vol += vol

    total = total_bid_vol + total_ask_vol
    result["bid_volume"] = round(total_bid_vol, 2)
    result["ask_volume"] = round(total_ask_vol, 2)

    if total > 0:
        result["imbalance_ratio"] = round(total_bid_vol / total_ask_vol if total_ask_vol > 0 else total_bid_vol, 4)

    if result["imbalance_ratio"] > 2.0:
        result["signal"] = "BID_HEAVY"
    elif result["imbalance_ratio"] < 0.5:
        result["signal"] = "ASK_HEAVY"
    elif total > 0:
        result["signal"] = "BALANCED"

    return result
