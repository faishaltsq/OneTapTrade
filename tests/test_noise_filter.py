import sys

import numpy as np
import pandas as pd

sys.path.insert(0, r'C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade')


def _make_df(trend: str = "BULLISH", bars: int = 80, atr_pct: float = 50.0, volume_ratio: float = 1.3):
    """Build a synthetic OHLC dataframe with controllable trend/ATR/volume."""
    np.random.seed(42)
    base = 2000.0
    if trend == "BULLISH":
        closes = base + np.cumsum(np.random.uniform(0.5, 2.0, bars))
    elif trend == "BEARISH":
        closes = base + np.cumsum(np.random.uniform(-2.0, -0.5, bars))
    else:
        t = np.arange(bars)
        closes = base + 3.0 * np.sin(t / 8.0) + np.random.uniform(-0.3, 0.3, bars)

    opens = closes - np.random.uniform(-1, 1, bars)
    spread = np.where(np.arange(bars) < bars - 25, 1.0, 1.8)
    highs = np.maximum(opens, closes) + np.random.uniform(0.5, 3.0, bars) * spread
    lows = np.minimum(opens, closes) - np.random.uniform(0.5, 3.0, bars) * spread

    avg_vol = 100.0
    volumes = np.full(bars, avg_vol)
    volumes[-1] = avg_vol * volume_ratio

    df = pd.DataFrame({
        "time": pd.date_range("2025-01-01", periods=bars, freq="1h"),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": volumes,
    })
    return df


def _empty_df():
    return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume"])


def test_noise_filter_returns_dict_with_required_keys():
    from app.analysis.noise_filter import evaluate_noise_filter

    df = _make_df()
    result = evaluate_noise_filter(df, df, df, df, "MEDIUM")

    assert "passed" in result
    assert "blocked_by" in result
    assert "details" in result
    assert "hold_reason" in result


def test_swing_blocks_when_d1_h4_conflict():
    from app.analysis.noise_filter import evaluate_noise_filter

    df_bull = _make_df("BULLISH")
    df_bear = _make_df("BEARISH")
    result = evaluate_noise_filter(df_bull, df_bear, df_bull, df_bull, "LOW")

    assert result["passed"] is False
    assert result["blocked_by"] == "tf_alignment"


def test_swing_passes_when_d1_h4_aligned():
    from app.analysis.noise_filter import evaluate_noise_filter

    df = _make_df("BULLISH")
    result = evaluate_noise_filter(df, df, df, df, "LOW")

    assert result["passed"] is True
    assert result["blocked_by"] is None


def test_medium_passes_when_d1_non_unclear_and_h1_neutral():
    from app.analysis.noise_filter import evaluate_noise_filter

    df_bull = _make_df("BULLISH")
    df_unclear = _make_df("UNCLEAR")
    result = evaluate_noise_filter(df_bull, df_unclear, df_unclear, df_bull, "MEDIUM")

    assert result["passed"] is True


def test_medium_blocks_when_d1_bullish_and_h1_bearish_strong_opposite():
    from app.analysis.noise_filter import evaluate_noise_filter

    df_bull = _make_df("BULLISH")
    df_bear = _make_df("BEARISH")
    result = evaluate_noise_filter(df_bull, df_bull, df_bear, df_bear, "MEDIUM")

    assert result["passed"] is False
    assert result["blocked_by"] == "tf_alignment"


def test_high_skips_tf_alignment_gate():
    from app.analysis.noise_filter import evaluate_noise_filter

    df_bull = _make_df("BULLISH")
    df_bear = _make_df("BEARISH")
    result = evaluate_noise_filter(df_bear, df_bear, df_bull, df_bear, "HIGH")

    assert result["passed"] is True


def test_empty_dataframes_block_with_safe_reason():
    from app.analysis.noise_filter import evaluate_noise_filter

    empty = _empty_df()
    result = evaluate_noise_filter(empty, empty, empty, empty, "MEDIUM")

    assert result["passed"] is False
    assert "details" in result


def test_details_contains_atr_percentile_and_volume_ratio():
    from app.analysis.noise_filter import evaluate_noise_filter

    df = _make_df()
    result = evaluate_noise_filter(df, df, df, df, "MEDIUM")

    assert "atr_percentile" in result["details"]
    assert "volume_ratio" in result["details"]
    assert "tf_alignment" in result["details"]


def test_hold_reason_is_human_readable_string():
    from app.analysis.noise_filter import evaluate_noise_filter

    df_bull = _make_df("BULLISH")
    df_bear = _make_df("BEARISH")
    result = evaluate_noise_filter(df_bull, df_bear, df_bull, df_bull, "LOW")

    assert isinstance(result["hold_reason"], str)
    assert len(result["hold_reason"]) > 0
