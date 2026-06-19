from typing import List

import numpy as np
import pandas as pd


def calculate_volume_profile(df: pd.DataFrame, num_bins: int = 10) -> dict:
    result = {
        "poc": None,
        "vah": None,
        "val": None,
        "hvn": [],
        "lvn": [],
        "volume_distribution": [],
    }

    if df is None or len(df) == 0:
        return result

    if "tick_volume" not in df.columns:
        df = df.copy()
        df["tick_volume"] = 1

    low = df["low"].astype(float).min()
    high = df["high"].astype(float).max()

    if pd.isna(low) or pd.isna(high) or low == high:
        return result

    bins = np.linspace(low, high, num_bins + 1)
    price_levels = (bins[:-1] + bins[1:]) / 2.0

    df = df.copy()
    df["price_bin"] = pd.cut(
        (df["high"].astype(float) + df["low"].astype(float)) / 2.0,
        bins=bins,
        labels=False,
        include_lowest=True,
    )

    volume_by_bin = df.groupby("price_bin", observed=False)["tick_volume"].sum()

    volume_distribution: List[dict] = []
    for i in range(num_bins):
        vol = float(volume_by_bin.get(i, 0))
        volume_distribution.append(
            {"price_level": round(float(price_levels[i]), 5), "volume": vol}
        )

    result["volume_distribution"] = volume_distribution

    total_volume = sum(v["volume"] for v in volume_distribution)
    if total_volume == 0:
        return result

    sorted_bins = sorted(volume_distribution, key=lambda x: x["volume"], reverse=True)
    result["poc"] = sorted_bins[0]["price_level"]

    target_volume = total_volume * 0.70
    cumulative = 0.0
    poc_idx = next(i for i, v in enumerate(volume_distribution) if v["price_level"] == result["poc"])

    low_idx = poc_idx
    high_idx = poc_idx
    cumulative += volume_distribution[poc_idx]["volume"]

    while cumulative < target_volume:
        if high_idx < num_bins - 1 and low_idx > 0:
            if volume_distribution[high_idx + 1]["volume"] >= volume_distribution[low_idx - 1]["volume"]:
                high_idx += 1
            else:
                low_idx -= 1
        elif high_idx < num_bins - 1:
            high_idx += 1
        elif low_idx > 0:
            low_idx -= 1
        else:
            break
        cumulative += volume_distribution[high_idx if high_idx > poc_idx else low_idx]["volume"]

    result["vah"] = volume_distribution[high_idx]["price_level"]
    result["val"] = volume_distribution[low_idx]["price_level"]

    avg_volume = total_volume / num_bins
    result["hvn"] = [v["price_level"] for v in volume_distribution if v["volume"] > 1.5 * avg_volume]
    result["lvn"] = [v["price_level"] for v in volume_distribution if v["volume"] < 0.5 * avg_volume]

    return result


def price_relative_to_poc(current_price: float, vp: dict) -> str:
    poc = vp.get("poc") if vp else None
    if poc is None or current_price == poc:
        return "AT_POC"
    return "ABOVE_POC" if current_price > poc else "BELOW_POC"


def price_in_value_area(current_price: float, vp: dict) -> bool:
    if not vp:
        return False
    vah = vp.get("vah")
    val = vp.get("val")
    if vah is None or val is None:
        return False
    return val <= current_price <= vah
