import pandas as pd


BODY_RANGE_RATIO_FOR_DIRECTION = 0.25


def _empty_section() -> dict:
    return {
        "bias": "D1_RANGING",
        "candle_open": None,
        "candle_close": None,
        "range_high": None,
        "range_low": None,
        "breakout_retest_confirmed": False,
        "allowed_directions": [],
    }


def build_major_trend_section(df_d1: pd.DataFrame | None, smc: dict | None = None) -> dict:
    section = _empty_section()
    if df_d1 is None or len(df_d1) == 0:
        return section

    candle = df_d1.iloc[-1]
    open_price = float(candle.get("open"))
    high = float(candle.get("high"))
    low = float(candle.get("low"))
    close = float(candle.get("close"))
    candle_range = max(high - low, 0.0)
    body = abs(close - open_price)

    section.update(
        {
            "candle_open": open_price,
            "candle_close": close,
            "range_high": high,
            "range_low": low,
        }
    )

    if candle_range > 0 and body / candle_range >= BODY_RANGE_RATIO_FOR_DIRECTION:
        if close > open_price:
            section["bias"] = "D1_BULLISH"
            section["allowed_directions"] = ["BUY"]
            return section
        if close < open_price:
            section["bias"] = "D1_BEARISH"
            section["allowed_directions"] = ["SELL"]
            return section

    breakout_retest = (smc or {}).get("breakout_retest", {})
    confirmed = bool(breakout_retest.get("confirmed"))
    direction = str(breakout_retest.get("direction", "")).upper()
    section["breakout_retest_confirmed"] = confirmed
    if confirmed and direction in ("BUY", "SELL"):
        section["allowed_directions"] = [direction]

    return section
