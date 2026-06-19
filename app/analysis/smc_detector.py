import pandas as pd
import numpy as np
from typing import Optional
from app.logger import logger


def detect_swing_points(df: pd.DataFrame, timeframe_label: str, lookback: int = 3) -> dict:
    if df is None or len(df) < lookback * 2 + 1:
        return {"highs": [], "lows": [], "timeframe": timeframe_label}

    highs = []
    lows = []
    n = len(df)

    for i in range(lookback, n - lookback):
        window_highs = df["high"].iloc[i - lookback : i + lookback + 1]
        window_lows = df["low"].iloc[i - lookback : i + lookback + 1]

        if df["high"].iloc[i] == window_highs.max():
            highs.append({
                "price": round(float(df["high"].iloc[i]), 5),
                "index": int(i),
                "time": str(df["time"].iloc[i]) if "time" in df.columns else None,
            })

        if df["low"].iloc[i] == window_lows.min():
            lows.append({
                "price": round(float(df["low"].iloc[i]), 5),
                "index": int(i),
                "time": str(df["time"].iloc[i]) if "time" in df.columns else None,
            })

    return {"highs": highs, "lows": lows, "timeframe": timeframe_label}


def detect_order_blocks(df: pd.DataFrame, timeframe_label: str) -> dict:
    supply = []
    demand = []

    if df is None or len(df) < 4:
        return {"supply": supply, "demand": demand, "timeframe": timeframe_label}

    n = len(df)

    for i in range(3, n - 1):
        c0 = df.iloc[i - 3]
        c1 = df.iloc[i - 2]
        c2 = df.iloc[i - 1]
        c3 = df.iloc[i]

        # Bullish OB: last bearish candle before strong bullish impulse
        if c2["close"] < c2["open"] and c3["close"] > c3["open"]:
            impulse = abs(c3["close"] - c3["open"])
            avg_body = df["close"].iloc[max(0, i - 10):i].diff().abs().mean()
            if impulse > avg_body * 1.5:
                demand.append({
                    "high": round(float(c2["high"]), 5),
                    "low": round(float(c2["low"]), 5),
                    "index": int(i - 1),
                    "time": str(df["time"].iloc[i - 1]) if "time" in df.columns else None,
                })

        # Bearish OB: last bullish candle before strong bearish impulse
        if c2["close"] > c2["open"] and c3["close"] < c3["open"]:
            impulse = abs(c3["close"] - c3["open"])
            avg_body = df["close"].iloc[max(0, i - 10):i].diff().abs().mean()
            if impulse > avg_body * 1.5:
                supply.append({
                    "high": round(float(c2["high"]), 5),
                    "low": round(float(c2["low"]), 5),
                    "index": int(i - 1),
                    "time": str(df["time"].iloc[i - 1]) if "time" in df.columns else None,
                })

    return {"supply": supply, "demand": demand, "timeframe": timeframe_label}


def detect_fvg(df: pd.DataFrame) -> list:
    fvgs = []

    if df is None or len(df) < 3:
        return fvgs

    n = len(df)

    for i in range(2, n):
        c0 = df.iloc[i - 2]
        c1 = df.iloc[i - 1]
        c2 = df.iloc[i]

        # Bullish FVG: candle[i-2].high < candle[i].low (gap up)
        if c0["high"] < c2["low"]:
            fvgs.append({
                "top": round(float(c2["low"]), 5),
                "bottom": round(float(c0["high"]), 5),
                "direction": "bullish",
                "index": int(i),
                "time": str(df["time"].iloc[i]) if "time" in df.columns else None,
            })

        # Bearish FVG: candle[i-2].low > candle[i].high (gap down)
        if c0["low"] > c2["high"]:
            fvgs.append({
                "top": round(float(c0["low"]), 5),
                "bottom": round(float(c2["high"]), 5),
                "direction": "bearish",
                "index": int(i),
                "time": str(df["time"].iloc[i]) if "time" in df.columns else None,
            })

    return fvgs


def detect_choch(df: pd.DataFrame, swing_points: dict) -> dict:
    bullish_choch = []
    bearish_choch = []

    highs = swing_points.get("highs", [])
    lows = swing_points.get("lows", [])

    if len(highs) < 2 or len(lows) < 2:
        return {"bullish_choch": bullish_choch, "bearish_choch": bearish_choch}

    # Bearish CHoCH: lower high formed → potential reversal down
    for i in range(1, len(highs)):
        if highs[i]["price"] < highs[i - 1]["price"] and highs[i]["index"] > highs[i - 1]["index"]:
            bearish_choch.append({
                "price": highs[i]["price"],
                "prev_price": highs[i - 1]["price"],
                "index": highs[i]["index"],
                "time": highs[i].get("time"),
            })

    # Bullish CHoCH: higher low formed → potential reversal up
    for i in range(1, len(lows)):
        if lows[i]["price"] > lows[i - 1]["price"] and lows[i]["index"] > lows[i - 1]["index"]:
            bullish_choch.append({
                "price": lows[i]["price"],
                "prev_price": lows[i - 1]["price"],
                "index": lows[i]["index"],
                "time": lows[i].get("time"),
            })

    return {"bullish_choch": bullish_choch, "bearish_choch": bearish_choch}


def detect_liquidity_levels(df: pd.DataFrame, lookback: int = 5) -> list:
    levels = []

    if df is None or len(df) < lookback:
        return levels

    n = len(df)
    tolerance_pct = 0.002  # 0.2% tolerance for "equal" levels

    # Detect equal highs
    high_clusters = []
    for i in range(lookback, n - lookback):
        current_high = df["high"].iloc[i]
        cluster = [{"price": current_high, "index": i}]
        for j in range(max(0, i - lookback), min(n, i + lookback + 1)):
            if i != j:
                other_high = df["high"].iloc[j]
                if abs(other_high - current_high) / max(current_high, 0.0001) < tolerance_pct:
                    cluster.append({"price": other_high, "index": j})
        if len(cluster) >= 2:
            avg_price = sum(c["price"] for c in cluster) / len(cluster)
            high_clusters.append({
                "price": round(float(avg_price), 5),
                "count": len(cluster),
                "type": "high",
                "time": str(df["time"].iloc[i]) if "time" in df.columns else None,
            })

    # Detect equal lows
    low_clusters = []
    for i in range(lookback, n - lookback):
        current_low = df["low"].iloc[i]
        cluster = [{"price": current_low, "index": i}]
        for j in range(max(0, i - lookback), min(n, i + lookback + 1)):
            if i != j:
                other_low = df["low"].iloc[j]
                if abs(other_low - current_low) / max(current_low, 0.0001) < tolerance_pct:
                    cluster.append({"price": other_low, "index": j})
        if len(cluster) >= 2:
            avg_price = sum(c["price"] for c in cluster) / len(cluster)
            low_clusters.append({
                "price": round(float(avg_price), 5),
                "count": len(cluster),
                "type": "low",
                "time": str(df["time"].iloc[i]) if "time" in df.columns else None,
            })

    # Deduplicate and sort by count descending
    seen_prices = set()
    for cluster in high_clusters + low_clusters:
        key = f"{cluster['price']:.2f}_{cluster['type']}"
        if key not in seen_prices:
            seen_prices.add(key)
            levels.append(cluster)

    levels.sort(key=lambda x: x["count"], reverse=True)
    return levels[:20]


def build_smc_section(df_h1: Optional[pd.DataFrame], df_m5: Optional[pd.DataFrame]) -> dict:
    h1_empty = df_h1 is None or len(df_h1) == 0
    m5_empty = df_m5 is None or len(df_m5) == 0

    h1_swings = detect_swing_points(df_h1, "H1", lookback=3) if not h1_empty else {"highs": [], "lows": [], "timeframe": "H1"}
    m5_swings = detect_swing_points(df_m5, "M5", lookback=3) if not m5_empty else {"highs": [], "lows": [], "timeframe": "M5"}

    order_blocks = detect_order_blocks(df_h1, "H1") if not h1_empty else {"supply": [], "demand": [], "timeframe": "H1"}

    fvg_zones = detect_fvg(df_m5) if not m5_empty else []

    h1_choch = detect_choch(df_h1, h1_swings) if not h1_empty else {"bullish_choch": [], "bearish_choch": []}
    m5_choch = detect_choch(df_m5, m5_swings) if not m5_empty else {"bullish_choch": [], "bearish_choch": []}

    liquidity_levels = detect_liquidity_levels(df_m5, lookback=10) if not m5_empty else []

    # Keep only recent data (last 20 entries per category)
    return {
        "h1_swings": {
            "highs": h1_swings["highs"][-20:],
            "lows": h1_swings["lows"][-20:],
        },
        "m5_swings": {
            "highs": m5_swings["highs"][-20:],
            "lows": m5_swings["lows"][-20:],
        },
        "order_blocks": {
            "supply": order_blocks["supply"][-10:],
            "demand": order_blocks["demand"][-10:],
        },
        "fvg_zones": fvg_zones[-15:],
        "choch": {
            "h1": h1_choch,
            "m5": m5_choch,
        },
        "liquidity_levels": liquidity_levels[:15],
    }
