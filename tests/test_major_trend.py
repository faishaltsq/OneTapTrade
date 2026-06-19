import pandas as pd


def _d1_df(open_price: float, high: float, low: float, close: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"time": "2026-06-18", "open": 100.0, "high": 105.0, "low": 95.0, "close": 101.0},
            {"time": "2026-06-19", "open": open_price, "high": high, "low": low, "close": close},
        ]
    )


def test_d1_bullish_candle_returns_buy_only():
    from app.analysis.major_trend import build_major_trend_section

    result = build_major_trend_section(_d1_df(100.0, 112.0, 98.0, 110.0))

    assert result["bias"] == "D1_BULLISH"
    assert result["allowed_directions"] == ["BUY"]


def test_d1_bearish_candle_returns_sell_only():
    from app.analysis.major_trend import build_major_trend_section

    result = build_major_trend_section(_d1_df(110.0, 112.0, 98.0, 100.0))

    assert result["bias"] == "D1_BEARISH"
    assert result["allowed_directions"] == ["SELL"]


def test_d1_small_body_returns_ranging():
    from app.analysis.major_trend import build_major_trend_section

    result = build_major_trend_section(_d1_df(100.0, 110.0, 90.0, 101.0))

    assert result["bias"] == "D1_RANGING"
    assert result["allowed_directions"] == []


def test_ranging_breakout_retest_confirmed_from_smc_context():
    from app.analysis.major_trend import build_major_trend_section

    smc = {"breakout_retest": {"confirmed": True, "direction": "BUY"}}

    result = build_major_trend_section(_d1_df(100.0, 110.0, 90.0, 101.0), smc=smc)

    assert result["bias"] == "D1_RANGING"
    assert result["breakout_retest_confirmed"] is True
    assert result["allowed_directions"] == ["BUY"]
