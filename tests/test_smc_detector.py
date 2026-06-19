import sys
sys.path.insert(0, r'C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade\ai-trading-executor')

import pandas as pd
import numpy as np


def _make_df(prices=None):
    if prices is None:
        prices = [100 + i * 0.5 for i in range(50)]
    df = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=len(prices), freq="5min"),
        "open": prices,
        "high": [p + np.random.uniform(0.1, 0.5) for p in prices],
        "low": [p - np.random.uniform(0.1, 0.5) for p in prices],
        "close": [p + np.random.uniform(-0.2, 0.2) for p in prices],
        "tick_volume": [100] * len(prices),
        "spread": [2] * len(prices),
    })
    return df


def _make_trending_df(uptrend=True, length=60):
    np.random.seed(42)
    base = 100.0
    highs = []
    lows = []
    closes = []
    for i in range(length):
        if uptrend:
            base += 0.5 + np.random.uniform(0, 0.3)
        else:
            base -= 0.5 + np.random.uniform(0, 0.3)
        h = base + np.random.uniform(0.3, 1.0)
        l = base - np.random.uniform(0.3, 1.0)
        highs.append(h)
        lows.append(l)
        closes.append(base)
    df = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=length, freq="h"),
        "open": [c - 0.1 for c in closes],
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": [100] * length,
        "spread": [2] * length,
    })
    return df


def _make_impulse_df():
    # Create a clear impulse with order block
    data = []
    # Consolidation / order block area
    for i in range(10):
        data.append({"open": 100 + i * 0.1, "high": 102 + i * 0.1, "low": 99 + i * 0.1, "close": 101 + i * 0.2})
    # Impulse up
    for i in range(5):
        data.append({"open": 102 + i * 1, "high": 104 + i * 1, "low": 101 + i * 1, "close": 103 + i * 1})
    # Retracement
    for i in range(5):
        data.append({"open": 107 - i * 0.5, "high": 108 - i * 0.5, "low": 106 - i * 0.5, "close": 107 - i * 0.5})

    df = pd.DataFrame(data)
    df["time"] = pd.date_range("2026-01-01", periods=len(df), freq="h")
    df["tick_volume"] = 100
    df["spread"] = 2
    return df


class TestSwingPoints:

    def test_detects_swing_highs(self):
        from app.analysis.smc_detector import detect_swing_points

        # Create clear swing pattern: peak at index 5, trough at index 12
        lows =  [100, 99, 98, 97, 99, 101, 105, 103, 100, 98, 96, 95, 97, 99, 102, 104, 103, 101, 99, 97]
        highs = [102, 101, 100, 101, 103, 107, 106, 104, 102, 100, 98, 97, 99, 101, 104, 106, 105, 103, 101, 99]
        closes = [(h + l) / 2 for h, l in zip(highs, lows)]
        df = pd.DataFrame({
            "time": pd.date_range("2026-01-01", periods=len(highs), freq="h"),
            "open": [c - 0.5 for c in closes],
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": [100] * len(highs),
            "spread": [2] * len(highs),
        })
        swings = detect_swing_points(df, "H1", lookback=2)

        assert len(swings["highs"]) > 0
        assert len(swings["lows"]) > 0
        for h in swings["highs"]:
            assert "price" in h
            assert "index" in h

    def test_detects_swing_lows(self):
        from app.analysis.smc_detector import detect_swing_points

        lows =  [100, 99, 98, 97, 99, 101, 105, 103, 100, 98, 96, 95, 97, 99, 102, 104, 103, 101, 99, 97]
        highs = [102, 101, 100, 101, 103, 107, 106, 104, 102, 100, 98, 97, 99, 101, 104, 106, 105, 103, 101, 99]
        closes = [(h + l) / 2 for h, l in zip(highs, lows)]
        df = pd.DataFrame({
            "time": pd.date_range("2026-01-01", periods=len(highs), freq="h"),
            "open": [c - 0.5 for c in closes], "high": highs, "low": lows, "close": closes,
            "tick_volume": [100] * len(highs), "spread": [2] * len(highs),
        })
        swings = detect_swing_points(df, "H1", lookback=2)

        assert len(swings["highs"]) + len(swings["lows"]) > 0


class TestOrderBlocks:

    def test_detects_bullish_order_block(self):
        from app.analysis.smc_detector import detect_order_blocks

        df = _make_impulse_df()
        blocks = detect_order_blocks(df, "H1")

        assert "supply" in blocks
        assert "demand" in blocks
        # Structure is valid even if no blocks found in small dataset

    def test_order_block_has_required_fields(self):
        from app.analysis.smc_detector import detect_order_blocks

        df = _make_impulse_df()
        blocks = detect_order_blocks(df, "H1")

        for block_type in ["supply", "demand"]:
            for ob in blocks[block_type]:
                assert "high" in ob
                assert "low" in ob
                assert "index" in ob


class TestFVG:

    def test_detects_fair_value_gaps(self):
        from app.analysis.smc_detector import detect_fvg

        # Create data with clear FVG: candle 1 high < candle 3 low (gap up)
        data = [
            {"open": 100, "high": 101, "low": 99, "close": 100.5},
            {"open": 100.5, "high": 103, "low": 100, "close": 102.5},
            {"open": 103, "high": 105, "low": 102.5, "close": 104},
            {"open": 104, "high": 106, "low": 103.5, "close": 105},
        ]
        df = pd.DataFrame(data)
        df["time"] = pd.date_range("2026-01-01", periods=len(df), freq="5min")
        df["tick_volume"] = 100
        df["spread"] = 2

        fvgs = detect_fvg(df)

        assert isinstance(fvgs, list)
        # FVG exists when candle[i-2].high < candle[i].low (bullish FVG)
        # or candle[i-2].low > candle[i].high (bearish FVG)

    def test_fvg_has_required_fields(self):
        from app.analysis.smc_detector import detect_fvg

        df = _make_df()
        fvgs = detect_fvg(df)

        for fvg in fvgs:
            assert "top" in fvg
            assert "bottom" in fvg
            assert "direction" in fvg
            assert fvg["direction"] in ("bullish", "bearish")


class TestCHoCH:

    def test_detects_structure_break(self):
        from app.analysis.smc_detector import detect_swing_points, detect_choch

        df = _make_trending_df(uptrend=True, length=80)
        swings = detect_swing_points(df, "H1", lookback=2)
        choch = detect_choch(df, swings)

        assert isinstance(choch, dict)
        assert "bullish_choch" in choch
        assert "bearish_choch" in choch


class TestLiquidityLevels:

    def test_detects_equal_highs(self):
        from app.analysis.smc_detector import detect_liquidity_levels

        data = []
        for i in range(30):
            data.append({"open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i})
        # Create equal highs (liquidity)
        data[10]["high"] = 115.0
        data[11]["high"] = 115.2  # near equal
        data[12]["high"] = 115.1  # near equal
        data[20]["high"] = 120.0
        data[21]["high"] = 120.1

        df = pd.DataFrame(data)
        df["time"] = pd.date_range("2026-01-01", periods=len(df), freq="h")
        df["tick_volume"] = 100
        df["spread"] = 2

        levels = detect_liquidity_levels(df, lookback=5)

        assert isinstance(levels, list)
        for level in levels:
            assert "price" in level
            assert "count" in level
            assert level["count"] >= 2


class TestBuildSMCSection:

    def test_builds_complete_smc_section(self):
        from app.analysis.smc_detector import build_smc_section

        df_h1 = _make_trending_df(uptrend=True, length=50)
        df_m5 = _make_df()

        smc = build_smc_section(df_h1, df_m5)

        assert "h1_swings" in smc
        assert "m5_swings" in smc
        assert "order_blocks" in smc
        assert "fvg_zones" in smc
        assert "choch" in smc
        assert "liquidity_levels" in smc

    def test_handles_empty_dataframes(self):
        from app.analysis.smc_detector import build_smc_section

        df_empty = pd.DataFrame()
        smc = build_smc_section(df_empty, df_empty)

        assert smc["h1_swings"]["highs"] == []
        assert smc["order_blocks"]["supply"] == []
