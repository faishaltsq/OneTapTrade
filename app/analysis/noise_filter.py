from typing import Optional

import pandas as pd

from app.analysis.market_structure import detect_trend
from app.analysis.regime_detector import _atr_percentile
from app.logger import logger


def _trend_direction(df: pd.DataFrame) -> str:
    if df is None or len(df) < 50:
        return "UNCLEAR"
    result = detect_trend(df)
    return result.get("direction", "UNCLEAR")


def _volume_ratio(df: pd.DataFrame) -> float:
    if df is None or len(df) < 21 or "tick_volume" not in df.columns:
        return 1.0
    volumes = df["tick_volume"].astype(float).dropna()
    if len(volumes) < 21:
        return 1.0
    avg_20 = float(volumes.iloc[-21:-1].mean())
    last = float(volumes.iloc[-1])
    if avg_20 <= 0:
        return 1.0
    return round(last / avg_20, 3)


def _check_tf_alignment(d1_dir: str, h4_dir: str, h1_dir: str, m5_dir: str, profile: str) -> tuple[bool, str]:
    if profile == "LOW":
        if d1_dir == "UNCLEAR" or h4_dir == "UNCLEAR":
            return False, f"D1={d1_dir}, H4={h4_dir} — need both clear"
        if d1_dir != h4_dir:
            return False, f"D1={d1_dir}, H4={h4_dir} conflict"
        return True, ""

    if profile == "MEDIUM":
        if d1_dir == "UNCLEAR":
            return False, f"D1={d1_dir} — need clear D1"
        strongly_opposite = (
            (d1_dir == "BULLISH" and h1_dir == "BEARISH")
            or (d1_dir == "BEARISH" and h1_dir == "BULLISH")
        )
        if strongly_opposite:
            return False, f"D1={d1_dir}, H1={h1_dir} strongly opposite"
        return True, ""

    return True, ""


def _check_atr_percentile(df_h1: pd.DataFrame, profile: str) -> tuple[bool, str, float]:
    pct = _atr_percentile(df_h1, 14) if df_h1 is not None and len(df_h1) >= 50 else 50.0

    if profile == "LOW":
        lo, hi = 20.0, 85.0
    elif profile == "MEDIUM":
        lo, hi = 15.0, 90.0
    else:
        lo, hi = 10.0, 95.0

    if pct < lo:
        return False, f"ATR percentile {pct:.1f} below {lo} (dead market)", pct
    if pct > hi:
        return False, f"ATR percentile {pct:.1f} above {hi} (chaos)", pct
    return True, "", pct


def _check_volume(df_entry: pd.DataFrame, profile: str) -> tuple[bool, str, float]:
    ratio = _volume_ratio(df_entry)

    if profile == "LOW":
        threshold = 1.2
    elif profile == "MEDIUM":
        threshold = 0.8
    else:
        threshold = 0.5

    if ratio < threshold:
        return False, f"Volume ratio {ratio:.2f} below {threshold} (thin activity)", ratio
    return True, "", ratio


def _entry_df_for_profile(df_m5: pd.DataFrame, df_h1: pd.DataFrame, df_h4: pd.DataFrame, profile: str) -> pd.DataFrame:
    if profile == "LOW":
        return df_h4
    if profile == "MEDIUM":
        return df_h1
    return df_m5


def evaluate_noise_filter(
    df_d1: Optional[pd.DataFrame],
    df_h4: Optional[pd.DataFrame],
    df_h1: Optional[pd.DataFrame],
    df_m5: Optional[pd.DataFrame],
    risk_profile: str,
) -> dict:
    profile = risk_profile.upper()

    d1_dir = _trend_direction(df_d1)
    h4_dir = _trend_direction(df_h4)
    h1_dir = _trend_direction(df_h1)
    m5_dir = _trend_direction(df_m5)

    tf_ok, tf_reason = _check_tf_alignment(d1_dir, h4_dir, h1_dir, m5_dir, profile)
    atr_ok, atr_reason, atr_pct = _check_atr_percentile(df_h1, profile)
    df_entry = _entry_df_for_profile(df_m5, df_h1, df_h4, profile)
    vol_ok, vol_reason, vol_ratio = _check_volume(df_entry, profile)

    details = {
        "tf_alignment": {"d1": d1_dir, "h4": h4_dir, "h1": h1_dir, "m5": m5_dir},
        "atr_percentile": atr_pct,
        "volume_ratio": vol_ratio,
    }

    if not tf_ok:
        logger.info(f"Noise filter block (tf_alignment): {tf_reason}")
        return {
            "passed": False,
            "blocked_by": "tf_alignment",
            "details": details,
            "hold_reason": f"TF conflict: {tf_reason}",
        }

    if not atr_ok:
        logger.info(f"Noise filter block (atr_percentile): {atr_reason}")
        return {
            "passed": False,
            "blocked_by": "atr_percentile",
            "details": details,
            "hold_reason": atr_reason,
        }

    if not vol_ok:
        logger.info(f"Noise filter block (volume): {vol_reason}")
        return {
            "passed": False,
            "blocked_by": "volume",
            "details": details,
            "hold_reason": vol_reason,
        }

    return {
        "passed": True,
        "blocked_by": None,
        "details": details,
        "hold_reason": "",
    }
