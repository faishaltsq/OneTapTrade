from typing import Any

import pandas as pd

from app.logger import logger


async def fetch_tv_ohlcv(tools: Any, symbol: str, timeframes: list[str]) -> dict[str, pd.DataFrame]:
    dataframes: dict[str, pd.DataFrame] = {}
    for timeframe in timeframes:
        try:
            await tools.set_timeframe(timeframe)
            ohlcv = await tools.get_ohlcv(symbol=symbol, timeframe=timeframe, summary=True)
            bars = getattr(ohlcv, "bars", None) or getattr(ohlcv, "candles", None) or []
            df = pd.DataFrame(bars)
            if not df.empty:
                if "volume" in df.columns and "tick_volume" not in df.columns:
                    df["tick_volume"] = df["volume"]
                if "time" in df.columns:
                    df["time"] = pd.to_datetime(df["time"], unit="s", errors="coerce")
            dataframes[timeframe] = df
        except Exception as exc:
            logger.warning(f"TV OHLCV fetch failed for {symbol} {timeframe}: {exc}")
            dataframes[timeframe] = pd.DataFrame()
    return dataframes


async def fetch_tv_quote(tools: Any) -> dict[str, float]:
    try:
        quote = await tools.get_quote()
        bid = float(getattr(quote, "bid", 0) or 0)
        ask = float(getattr(quote, "ask", 0) or 0)
        return {
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2 if bid and ask else float(getattr(quote, "last", 0) or 0),
            "spread_points": 0,
        }
    except Exception as exc:
        logger.warning(f"TV quote fetch failed: {exc}")
        return {"bid": 0.0, "ask": 0.0, "mid": 0.0, "spread_points": 0}


async def fetch_tv_indicators(tools: Any, study_filter: str | None = None) -> dict[str, float]:
    try:
        studies = await tools.get_study_values(study_filter=study_filter)
    except Exception as exc:
        logger.warning(f"TV study values fetch failed: {exc}")
        return {}

    values: dict[str, float] = {}
    for study in studies or []:
        name = str(getattr(study, "name", "")).lower()
        raw_values = getattr(study, "values", {}) or {}
        value = _first_numeric(raw_values)
        if value is None:
            continue
        if "rsi" in name and "14" in name:
            values["rsi_14"] = value
        elif "ema" in name and "50" in name:
            values["ema_50"] = value
        elif "ema" in name and "200" in name:
            values["ema_200"] = value
        elif "atr" in name and "14" in name:
            values["atr_14"] = value
    return values


async def fetch_tv_smc_zones(tools: Any) -> dict[str, Any]:
    try:
        boxes = await tools.get_pine_boxes(study_filter="Smart Money Concepts")
    except TypeError:
        boxes = await tools.get_pine_boxes()
    except Exception as exc:
        logger.warning(f"TV pine boxes fetch failed: {exc}")
        boxes = []

    demand = []
    supply = []
    fvg = []
    liquidity = []

    for box in boxes or []:
        zone = _box_to_zone(box)
        kind = classify_tv_box(str(getattr(box, "name", "") or getattr(box, "text", "")))
        if kind == "demand":
            demand.append(zone)
        elif kind == "supply":
            supply.append(zone)
        elif kind == "fvg":
            fvg.append({"top": zone["high"], "bottom": zone["low"], "time": zone.get("time")})
        elif kind == "liquidity":
            liquidity.append({"price": (zone["high"] + zone["low"]) / 2, "time": zone.get("time")})

    choch = {"h1": {"bullish_choch": [], "bearish_choch": []}, "m5": {"bullish_choch": [], "bearish_choch": []}}
    try:
        labels = await tools.get_pine_labels(study_filter="Smart Money Concepts")
    except TypeError:
        labels = await tools.get_pine_labels()
    except Exception:
        labels = []

    for label in labels or []:
        text = str(getattr(label, "text", "")).lower()
        if "choch" not in text:
            continue
        event = {"price": float(getattr(label, "price", 0) or 0)}
        if "bull" in text:
            choch["m5"]["bullish_choch"].append(event)
        elif "bear" in text:
            choch["m5"]["bearish_choch"].append(event)

    return {
        "order_blocks": {"demand": demand, "supply": supply},
        "fvg_zones": fvg,
        "liquidity_levels": liquidity,
        "choch": choch,
    }


async def fetch_all_tv_data(tools: Any, symbol: str, timeframes: list[str]) -> dict[str, Any]:
    return {
        "ohlcv": await fetch_tv_ohlcv(tools, symbol, timeframes),
        "quote": await fetch_tv_quote(tools),
        "indicators": await fetch_tv_indicators(tools),
        "smc": await fetch_tv_smc_zones(tools),
    }


def classify_tv_box(name: str) -> str:
    text = name.lower()
    if "demand" in text or ("bull" in text and "ob" in text):
        return "demand"
    if "supply" in text or ("bear" in text and "ob" in text):
        return "supply"
    if "fvg" in text or "fair value" in text or "gap" in text:
        return "fvg"
    if "liquid" in text or "equal" in text:
        return "liquidity"
    return "other"


def _box_to_zone(box: Any) -> dict[str, Any]:
    low = float(getattr(box, "low", getattr(box, "price_low", 0)) or 0)
    high = float(getattr(box, "high", getattr(box, "price_high", 0)) or 0)
    return {"low": min(low, high), "high": max(low, high), "time": getattr(box, "time", None)}


def _first_numeric(values: Any) -> float | None:
    if isinstance(values, dict):
        candidates = values.values()
    elif isinstance(values, list):
        candidates = values
    else:
        candidates = [values]
    for candidate in candidates:
        try:
            return float(candidate)
        except (TypeError, ValueError):
            continue
    return None
