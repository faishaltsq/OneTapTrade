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
        "h1_alignment": "NONE",
        "d1_h1_hierarchy": "D1_RANGING — H1 bias ignored",
    }


def _detect_h1_bias(df_h1: pd.DataFrame | None) -> str:
    if df_h1 is None or len(df_h1) < 2:
        return "NONE"
    last = df_h1.iloc[-1]
    h1_close = float(last.get("close", 0))
    h1_open = float(last.get("open", 0))
    prev_close = float(df_h1.iloc[-2].get("close", 0))

    if h1_close > prev_close and h1_close > h1_open:
        return "BULLISH"
    elif h1_close < prev_close and h1_close < h1_open:
        return "BEARISH"
    return "NEUTRAL"


def build_major_trend_section(df_d1: pd.DataFrame | None, smc: dict | None = None,
                                df_h1: pd.DataFrame | None = None) -> dict:
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

    h1_bias = _detect_h1_bias(df_h1)
    section["h1_bias"] = h1_bias

    if candle_range > 0 and body / candle_range >= BODY_RANGE_RATIO_FOR_DIRECTION:
        if close > open_price:
            section["bias"] = "D1_BULLISH"
            section["allowed_directions"] = ["BUY"]
            if h1_bias == "BEARISH":
                section["h1_alignment"] = "CONTRARY"
                section["d1_h1_hierarchy"] = "D1_BULLISH but H1 BEARISH — wait for H1 pullback confirmation"
            elif h1_bias == "BULLISH":
                section["h1_alignment"] = "ALIGNED"
                section["d1_h1_hierarchy"] = "D1_BULLISH + H1 BULLISH — strong BUY confluence"
            else:
                section["h1_alignment"] = "NEUTRAL"
                section["d1_h1_hierarchy"] = "D1_BULLISH + H1 NEUTRAL — BUY allowed, watch H1 for confirmation"
            return section

        if close < open_price:
            section["bias"] = "D1_BEARISH"
            section["allowed_directions"] = ["SELL"]
            if h1_bias == "BULLISH":
                section["h1_alignment"] = "CONTRARY"
                section["d1_h1_hierarchy"] = "D1_BEARISH but H1 BULLISH — wait for H1 pullback confirmation"
            elif h1_bias == "BEARISH":
                section["h1_alignment"] = "ALIGNED"
                section["d1_h1_hierarchy"] = "D1_BEARISH + H1 BEARISH — strong SELL confluence"
            else:
                section["h1_alignment"] = "NEUTRAL"
                section["d1_h1_hierarchy"] = "D1_BEARISH + H1 NEUTRAL — SELL allowed, watch H1 for confirmation"
            return section

    section["d1_h1_hierarchy"] = f"D1_RANGING + H1 {h1_bias} — wait for D1 breakout+retest confirmation"
    section["h1_alignment"] = "RANGING"

    breakout_retest = (smc or {}).get("breakout_retest", {})
    confirmed = bool(breakout_retest.get("confirmed"))
    direction = str(breakout_retest.get("direction", "")).upper()
    section["breakout_retest_confirmed"] = confirmed
    if confirmed and direction in ("BUY", "SELL"):
        section["allowed_directions"] = [direction]
        if h1_bias == direction:
            section["h1_alignment"] = "ALIGNED"
            section["d1_h1_hierarchy"] = f"D1 breakout {direction} + H1 {h1_bias} — confluence confirmed"
        elif h1_bias and h1_bias != "NEUTRAL" and h1_bias != direction:
            section["h1_alignment"] = "CONTRARY"
            section["d1_h1_hierarchy"] = f"D1 breakout {direction} but H1 {h1_bias} — conflicting, reduce confidence"

    return section
