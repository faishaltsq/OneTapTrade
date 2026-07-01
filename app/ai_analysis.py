import json
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

SIGNAL_FORMAT = """⚪ {PAIR} — {BUY / SELL / WAIT}

Setup Type:
{BUY_MARKET / SELL_MARKET / BUY_LIMIT / SELL_LIMIT / BUY_STOP / SELL_STOP / WAIT / NO_SETUP}

Day Trade:
{YES / NO}

Bias:
{Bullish / Bearish / Neutral}

Confidence:
{0-100}%

Risk Reward:
{1:x or N/A}

Entry:
{market price / limit zone / stop trigger price / WAIT - no trade}

Stop Loss:
{numeric price or N/A}

Take Profit:
TP1: {numeric price or N/A}
TP2: {numeric price or N/A}

AI Reason:
{1-2 concise Indonesian sentences}

Invalidation:
{clear invalidation rule or N/A}

Risk Reminder:
Gunakan lot sesuai manajemen risiko. Ini bukan financial advice."""

DAYTRADE_PLAYBOOK = """AI DAY-TRADE SETUP SCANNER RULES:

Your job: reject weak setups. Do not create signals where none exist.
You are a setup scanner, not a prediction engine.

TRADING STYLE: Day trade only.
Use M15, M30, H1 for entry context. Use H1 and H4 for intraday bias. D1 only as broad context.

ALLOWED SETUP_TYPES:
BUY_MARKET — price at valid bullish trigger, not late, structure supports continuation.
SELL_MARKET — price at valid bearish trigger, not late, structure supports continuation.
BUY_LIMIT — bullish bias but price should retrace into demand/OB/support/discount/retest first.
SELL_LIMIT — bearish bias but price should retrace into supply/OB/resistance/premium/retest first.
BUY_STOP — bullish breakout setup. Entry above trigger. SL below failed breakout. Avoid fakeout ranges.
SELL_STOP — bearish breakdown setup. Entry below trigger. SL above failed breakdown. Avoid fakeout ranges.
WAIT — setup may form later but entry not ready. Entry: WAIT - no trade. SL/TP: N/A.
NO_SETUP — unclear, choppy, risky, insufficient data. Entry: WAIT - no trade. SL/TP: N/A.

ENTRY QUALITY:
- MARKET: use ONLY if price is already in valid area. Never chase price.
- LIMIT: place around demand/OB/support/discount (BUY) or supply/OB/resistance/premium (SELL). No random orders.
- STOP: place beyond breakout/breakdown trigger. Stop loss beyond failed structure. Avoid high-noise ranges.

DAY TRADE RULES:
- TP1 must target nearest realistic intraday structure, liquidity, support, or resistance.
- TP2 must target next intraday structure or liquidity area.
- Do NOT use swing-trade or multi-day targets.
- SL must sit beyond structural invalidation, not arbitrary distance.
- Confidence >= {min_confidence}%. RR >= 1:{min_rr}. Otherwise NO_SETUP or WAIT.
- If setup needs many days: NO_SETUP.
- If price far from ideal entry: WAIT or LIMIT retest. Do NOT chase MARKET.
- If breakout risky or likely fakeout: WAIT.

WHAT TO AVOID:
NO swing-trade assumptions. NO long holding periods. NO overnight targets.
NO forced signals. NO chasing. NO weak breakouts.
NO entries inside choppy range. NO setups with unclear invalidation.
NO poor risk-reward. NO entry too close to opposite HTF S/R.
NO fake precision when data insufficient.
Do NOT buy directly into nearby bearish HTF resistance.
Do NOT sell directly into nearby bullish HTF support.

METHODS TO USE:
EMA 50/200 for trend. SMC: BOS, CHoCH, OB, supply/demand, FVG, premium/discount.
HTF SNR from H4/D only. Liquidity sweep/rejection context.
OHLCV summary and indicator_values when present.

Be selective. A good NO_SETUP or WAIT is better than a weak signal."""


def _safe_value(value: Any, fallback: str = "-") -> str:
    if value in (None, ""):
        return fallback
    return str(value)


def _percent_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    text = str(value).replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _float_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(" ", "").replace("%", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    elif "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _price_precision(value: float) -> int:
    if value >= 1000:
        return 3
    if value >= 100:
        return 3
    if value >= 10:
        return 4
    return 5


def _format_price(value: float | None, reference: float | None = None) -> str:
    if value is None:
        return "N/A"
    precision = _price_precision(reference if reference is not None else value)
    return f"{value:.{precision}f}"


def _studies_from(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("studies"), list):
        return [study for study in payload["studies"] if isinstance(study, dict)]
    if isinstance(payload, list):
        return [study for study in payload if isinstance(study, dict)]
    return []


def _current_price_from_context(context: dict[str, Any], signal: dict[str, Any] | None = None) -> float | None:
    signal = signal or {}
    quote = context.get("quote") or {}
    return _float_value(signal.get("price") or signal.get("entry") or quote.get("last") or quote.get("close"))


def _numeric_values(values: Any) -> dict[str, float | str]:
    if not isinstance(values, dict):
        return {}
    result: dict[str, float | str] = {}
    for key, value in values.items():
        parsed = _float_value(value)
        result[str(key)] = parsed if parsed is not None else str(value)
    return result


def _close_prices_from_ohlcv(ohlcv_bars: Any) -> list[float]:
    bars = ohlcv_bars.get("bars") if isinstance(ohlcv_bars, dict) else ohlcv_bars
    if not isinstance(bars, list):
        return []
    closes: list[float] = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        close = _float_value(bar.get("close"))
        if close is not None:
            closes.append(close)
    return closes


def _ema_from_closes(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    ema = sum(closes[:period]) / period
    multiplier = 2 / (period + 1)
    for close in closes[period:]:
        ema = (close - ema) * multiplier + ema
    return ema


def _ema_context(indicator_values: Any, current_price: float | None, ohlcv_bars: Any = None) -> dict[str, Any]:
    ema_studies: list[dict[str, Any]] = []
    ema_50: float | None = None
    ema_200: float | None = None
    closes = _close_prices_from_ohlcv(ohlcv_bars)
    computed_ema_50 = _ema_from_closes(closes, 50)
    computed_ema_200 = _ema_from_closes(closes, 200)

    for study in _studies_from(indicator_values):
        name = str(study.get("name") or "")
        lowered = name.lower()
        if "ema" not in lowered and "exponential" not in lowered and "moving average" not in lowered:
            continue

        values = _numeric_values(study.get("values"))
        if values:
            ema_studies.append({"name": name, "values": values})

        for title, value in values.items():
            if not isinstance(value, (int, float)):
                continue
            title_key = str(title).lower().replace("_", " ")
            fallback_key = f"{name} {title}".lower().replace("_", " ")
            if "50" in title_key and ema_50 is None:
                ema_50 = float(value)
            elif "200" in title_key and ema_200 is None:
                ema_200 = float(value)
            elif "50" in fallback_key and "200" not in fallback_key and ema_50 is None:
                ema_50 = float(value)
            elif "200" in fallback_key and "50" not in fallback_key and ema_200 is None:
                ema_200 = float(value)

    if computed_ema_50 is not None:
        ema_50 = computed_ema_50
    if computed_ema_200 is not None:
        ema_200 = computed_ema_200

    bias = "unknown"
    if current_price is not None and ema_50 is not None and ema_200 is not None:
        if current_price > ema_50 > ema_200:
            bias = "bullish"
        elif current_price < ema_50 < ema_200:
            bias = "bearish"
        else:
            bias = "mixed"
    elif current_price is not None and ema_studies:
        first_value = next(
            (value for study in ema_studies for value in study["values"].values() if isinstance(value, (int, float))),
            None,
        )
        if first_value is not None:
            bias = "bullish" if current_price > float(first_value) else "bearish"

    return {
        "bias": bias,
        "ema_50": ema_50,
        "ema_200": ema_200,
        "computed_from_ohlcv": {
            "bar_count": len(closes),
            "ema_50": computed_ema_50,
            "ema_200": computed_ema_200,
        },
        "available_studies": ema_studies[:5],
    }


def _nearest_levels(levels: list[float], current_price: float | None, limit: int = 6) -> dict[str, list[float]]:
    unique_levels = sorted(set(levels))
    if current_price is None:
        return {"above": unique_levels[-limit:], "below": unique_levels[:limit]}

    above = sorted([level for level in unique_levels if level >= current_price])[:limit]
    below = sorted([level for level in unique_levels if level < current_price], reverse=True)[:limit]
    return {"above": above, "below": below}


def _nearest_zones(zones: list[dict[str, Any]], current_price: float | None, limit: int = 5) -> list[dict[str, float]]:
    parsed_zones: list[dict[str, float]] = []
    for zone in zones:
        high = _float_value(zone.get("high"))
        low = _float_value(zone.get("low"))
        if high is None or low is None:
            continue
        parsed_zones.append({"high": max(high, low), "low": min(high, low)})

    if current_price is None:
        return parsed_zones[:limit]

    return sorted(
        parsed_zones,
        key=lambda zone: 0
        if zone["low"] <= current_price <= zone["high"]
        else min(abs(zone["high"] - current_price), abs(zone["low"] - current_price)),
    )[:limit]


def _bars_from_ohlcv(ohlcv_payload: Any) -> list[dict[str, float]]:
    bars = ohlcv_payload.get("bars") if isinstance(ohlcv_payload, dict) else ohlcv_payload
    if not isinstance(bars, list):
        return []

    parsed: list[dict[str, float]] = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        high = _float_value(bar.get("high"))
        low = _float_value(bar.get("low"))
        close = _float_value(bar.get("close"))
        if high is None or low is None or close is None:
            continue
        parsed.append({"high": high, "low": low, "close": close})
    return parsed


def _level_precision(price: float) -> int:
    return _price_precision(price)


def _round_level(price: float) -> float:
    return round(price, _level_precision(price))


def _snr_candidates_from_bars(bars: list[dict[str, float]], pivot_span: int = 2) -> list[dict[str, Any]]:
    if len(bars) < pivot_span * 2 + 1:
        return []

    candidates: list[dict[str, Any]] = []
    for index in range(pivot_span, len(bars) - pivot_span):
        window = bars[index - pivot_span : index + pivot_span + 1]
        high = bars[index]["high"]
        low = bars[index]["low"]
        if high >= max(bar["high"] for bar in window):
            candidates.append({"type": "resistance", "price": high, "index": index, "source": "pivot_high"})
        if low <= min(bar["low"] for bar in window):
            candidates.append({"type": "support", "price": low, "index": index, "source": "pivot_low"})

    recent_bars = bars[-min(50, len(bars)) :]
    recent_high = max(recent_bars, key=lambda bar: bar["high"])
    recent_low = min(recent_bars, key=lambda bar: bar["low"])
    candidates.append({"type": "resistance", "price": recent_high["high"], "index": len(bars) - 1, "source": "recent_range_high"})
    candidates.append({"type": "support", "price": recent_low["low"], "index": len(bars) - 1, "source": "recent_range_low"})
    return candidates


def _cluster_snr_levels(candidates: list[dict[str, Any]], tolerance: float, bar_count: int) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (item["type"], item["price"])):
        matching_cluster = next(
            (
                cluster
                for cluster in clusters
                if cluster["type"] == candidate["type"] and abs(cluster["price"] - candidate["price"]) <= tolerance
            ),
            None,
        )
        if matching_cluster is None:
            clusters.append(
                {
                    "type": candidate["type"],
                    "price": float(candidate["price"]),
                    "touches": 1,
                    "last_index": int(candidate["index"]),
                    "sources": [candidate["source"]],
                }
            )
            continue

        touches = matching_cluster["touches"] + 1
        matching_cluster["price"] = ((matching_cluster["price"] * matching_cluster["touches"]) + candidate["price"]) / touches
        matching_cluster["touches"] = touches
        matching_cluster["last_index"] = max(matching_cluster["last_index"], int(candidate["index"]))
        if candidate["source"] not in matching_cluster["sources"]:
            matching_cluster["sources"].append(candidate["source"])

    levels: list[dict[str, Any]] = []
    for cluster in clusters:
        recency = cluster["last_index"] / max(bar_count - 1, 1)
        score = round(cluster["touches"] + recency, 2)
        levels.append(
            {
                "type": cluster["type"],
                "price": _round_level(cluster["price"]),
                "touches": cluster["touches"],
                "score": score,
                "sources": cluster["sources"][:3],
            }
        )
    return levels


def _snr_timeframe_context(timeframe_payload: dict[str, Any], current_price: float | None) -> dict[str, Any]:
    bars = _bars_from_ohlcv(timeframe_payload.get("ohlcv"))
    if not bars:
        return {
            "timeframe": timeframe_payload.get("timeframe"),
            "success": False,
            "bar_count": 0,
            "supports": [],
            "resistances": [],
        }

    price_range = max(bar["high"] for bar in bars) - min(bar["low"] for bar in bars)
    reference_price = current_price or bars[-1]["close"]
    tolerance = max(price_range * 0.015, reference_price * 0.0002)
    levels = _cluster_snr_levels(_snr_candidates_from_bars(bars), tolerance, len(bars))

    supports = [level for level in levels if level["type"] == "support"]
    resistances = [level for level in levels if level["type"] == "resistance"]
    if current_price is not None:
        supports = [level for level in supports if level["price"] <= current_price]
        resistances = [level for level in resistances if level["price"] >= current_price]
        supports = sorted(supports, key=lambda level: (abs(current_price - level["price"]), -level["score"]))[:4]
        resistances = sorted(resistances, key=lambda level: (abs(level["price"] - current_price), -level["score"]))[:4]
    else:
        supports = sorted(supports, key=lambda level: level["score"], reverse=True)[:4]
        resistances = sorted(resistances, key=lambda level: level["score"], reverse=True)[:4]

    return {
        "timeframe": timeframe_payload.get("timeframe"),
        "success": True,
        "bar_count": len(bars),
        "tolerance": _round_level(tolerance),
        "supports": supports,
        "resistances": resistances,
    }


def _high_tf_snr_context(high_tf_snr: Any, current_price: float | None) -> dict[str, Any]:
    timeframes = high_tf_snr.get("timeframes") if isinstance(high_tf_snr, dict) else []
    if not isinstance(timeframes, list):
        timeframes = []

    contexts = [
        _snr_timeframe_context(timeframe_payload, current_price)
        for timeframe_payload in timeframes
        if isinstance(timeframe_payload, dict)
    ]
    nearest_supports = [level | {"timeframe": ctx["timeframe"]} for ctx in contexts for level in ctx.get("supports", [])]
    nearest_resistances = [level | {"timeframe": ctx["timeframe"]} for ctx in contexts for level in ctx.get("resistances", [])]
    if current_price is not None:
        nearest_supports = sorted(nearest_supports, key=lambda level: (abs(current_price - level["price"]), -level["score"]))[:5]
        nearest_resistances = sorted(nearest_resistances, key=lambda level: (abs(level["price"] - current_price), -level["score"]))[:5]
    else:
        nearest_supports = sorted(nearest_supports, key=lambda level: level["score"], reverse=True)[:5]
        nearest_resistances = sorted(nearest_resistances, key=lambda level: level["score"], reverse=True)[:5]

    return {
        "enabled": bool(isinstance(high_tf_snr, dict) and high_tf_snr.get("enabled")),
        "timeframes": contexts,
        "nearest_supports": nearest_supports,
        "nearest_resistances": nearest_resistances,
    }


def extract_daytrade_indicator_context(context: dict[str, Any], signal: dict[str, Any] | None = None) -> dict[str, Any]:
    current_price = _current_price_from_context(context, signal)
    indicator_values = context.get("indicator_values")

    smc_levels: list[float] = []
    for study in _studies_from(context.get("smc_lines")):
        for level in study.get("horizontal_levels") or []:
            parsed = _float_value(level)
            if parsed is not None:
                smc_levels.append(parsed)

    smc_labels: list[dict[str, Any]] = []
    for study in _studies_from(context.get("smc_labels")):
        for label in study.get("labels") or []:
            if isinstance(label, dict):
                smc_labels.append({"text": label.get("text"), "price": _float_value(label.get("price"))})

    smc_zones: list[dict[str, Any]] = []
    for study in _studies_from(context.get("smc_boxes")):
        smc_zones.extend([zone for zone in study.get("zones") or [] if isinstance(zone, dict)])

    return {
        "current_price": current_price,
        "ema": _ema_context(indicator_values, current_price, context.get("ohlcv_bars")),
        "smc": {
            "nearest_levels": _nearest_levels(smc_levels, current_price),
            "recent_labels": smc_labels[-12:],
            "nearest_zones": _nearest_zones(smc_zones, current_price),
        },
        "high_tf_snr": _high_tf_snr_context(context.get("high_tf_snr"), current_price),
    }


def _fallback_indicator_reason(indicator_context: dict[str, Any]) -> str:
    parts: list[str] = []
    ema = indicator_context.get("ema") or {}
    ema_bias = ema.get("bias")
    if ema_bias and ema_bias != "unknown":
        ema_50 = ema.get("ema_50")
        ema_200 = ema.get("ema_200")
        if ema_50 is not None and ema_200 is not None:
            parts.append(f"EMA 50/200 bias {ema_bias} ({_format_price(ema_50)}, {_format_price(ema_200)})")
        else:
            parts.append(f"EMA chart bias {ema_bias}")

    smc = indicator_context.get("smc") or {}
    recent_labels = [label for label in smc.get("recent_labels") or [] if label.get("text")]
    if recent_labels:
        labels_text = ", ".join(
            f"{label.get('text')} @{_format_price(label.get('price'))}" for label in recent_labels[-3:]
        )
        parts.append(f"SMC recent {labels_text}")

    nearest_zones = smc.get("nearest_zones") or []
    if nearest_zones:
        zone = nearest_zones[0]
        parts.append(f"zona SMC terdekat {_format_price(zone.get('low'))}-{_format_price(zone.get('high'))}")

    high_tf_snr = indicator_context.get("high_tf_snr") or {}
    nearest_supports = high_tf_snr.get("nearest_supports") or []
    nearest_resistances = high_tf_snr.get("nearest_resistances") or []
    snr_parts: list[str] = []
    if nearest_supports:
        support = nearest_supports[0]
        snr_parts.append(f"support {support.get('timeframe')} {_format_price(support.get('price'))}")
    if nearest_resistances:
        resistance = nearest_resistances[0]
        snr_parts.append(f"resistance {resistance.get('timeframe')} {_format_price(resistance.get('price'))}")
    if snr_parts:
        parts.append(f"HTF SNR {'; '.join(snr_parts)}")

    return "; ".join(parts)


def build_chart_analysis_prompt(context: dict[str, Any], signal: dict[str, Any] | None = None) -> str:
    compact_context = {
        "signal": signal,
        "chart": {
            "status": context.get("status"),
            "state": context.get("state"),
            "quote": context.get("quote"),
            "ohlcv_summary": context.get("ohlcv_summary"),
            "indicator_values": context.get("indicator_values"),
            "daytrade_indicators": extract_daytrade_indicator_context(context, signal),
        },
    }
    compact_context["chart_timestamp"] = datetime.now(timezone.utc).isoformat()
    return (
        f"Analyze ONE TradingView pair as a DeepSeek day-trade setup scanner. "
        "You are NOT a prediction engine. Your main job is to reject weak setups. "
        "Return ONLY the exact plain-text template below. No markdown, no extra sections. "
        "Use Indonesian for AI Reason and Invalidation. "
        "Be selective and defensive. If unclear, return WAIT or NO_SETUP.\n\n"
        f"{DAYTRADE_PLAYBOOK.format(min_confidence=settings.ai_min_trade_confidence, min_rr=settings.ai_min_rr)}\n\n"
        f"TEMPLATE:\n{SIGNAL_FORMAT}\n\n"
        f"DATA:\n{json.dumps(compact_context, ensure_ascii=False, indent=2)}"
    )


def fallback_signal_message(context: dict[str, Any], signal: dict[str, Any] | None = None) -> str:
    signal = signal or {}
    state = context.get("state") or {}
    quote = context.get("quote") or {}
    summary = context.get("ohlcv_summary") or {}
    indicator_context = extract_daytrade_indicator_context(context, signal)
    indicator_reason = _fallback_indicator_reason(indicator_context)

    pair = _safe_value(signal.get("symbol") or state.get("symbol") or quote.get("symbol") or settings.default_symbol)
    action = str(signal.get("action") or signal.get("decision") or "WAIT").upper()
    if action not in {"BUY", "SELL", "WAIT"}:
        action = "WAIT"

    change_pct = _percent_float(summary.get("change_pct"))
    ema_bias = (indicator_context.get("ema") or {}).get("bias")
    if action == "BUY":
        bias = "Bullish"
    elif action == "SELL":
        bias = "Bearish"
    elif ema_bias == "bullish":
        bias = "Bullish"
    elif ema_bias == "bearish":
        bias = "Bearish"
    elif change_pct > 0.3:
        bias = "Bullish"
    elif change_pct < -0.3:
        bias = "Bearish"
    else:
        bias = "Neutral"

    confidence = signal.get("confidence")
    if confidence is None:
        confidence = 50 if action in {"BUY", "SELL"} else 35
    try:
        confidence = int(float(confidence) * 100) if float(confidence) <= 1 else int(float(confidence))
    except (TypeError, ValueError):
        confidence = 35
    confidence = max(0, min(100, confidence))

    current_price_number = _float_value(signal.get("price") or signal.get("entry") or quote.get("last") or quote.get("close"))
    chart_range = _float_value(summary.get("range"))
    if current_price_number is not None and chart_range:
        risk_distance = max(chart_range * 0.08, current_price_number * 0.001)
    elif current_price_number is not None:
        risk_distance = current_price_number * 0.001
    else:
        risk_distance = None

    order_type = str(signal.get("order_type") or signal.get("entry_type") or "MARKET").upper()
    if order_type not in {"MARKET", "LIMIT"}:
        order_type = "MARKET"

    if action == "WAIT":
        entry = "WAIT - no trade"
        sl = "N/A"
        tp1 = "N/A"
        tp2 = "N/A"
    else:
        entry_price = _float_value(signal.get("entry") or signal.get("entry_price")) or current_price_number
        entry = f"{order_type} {_format_price(entry_price, current_price_number)}"
        explicit_sl = _float_value(signal.get("stop_loss") or signal.get("sl"))
        explicit_tp1 = _float_value(signal.get("take_profit_1") or signal.get("tp1") or signal.get("take_profit"))
        explicit_tp2 = _float_value(signal.get("take_profit_2") or signal.get("tp2"))

        if explicit_sl is not None:
            sl = _format_price(explicit_sl, current_price_number)
        elif current_price_number is not None and risk_distance is not None:
            sl = _format_price(current_price_number - risk_distance if action == "BUY" else current_price_number + risk_distance, current_price_number)
        else:
            sl = "N/A"

        if explicit_tp1 is not None:
            tp1 = _format_price(explicit_tp1, current_price_number)
        elif current_price_number is not None and risk_distance is not None:
            tp1 = _format_price(current_price_number + risk_distance * 1.5 if action == "BUY" else current_price_number - risk_distance * 1.5, current_price_number)
        else:
            tp1 = "N/A"

        if explicit_tp2 is not None:
            tp2 = _format_price(explicit_tp2, current_price_number)
        elif current_price_number is not None and risk_distance is not None:
            tp2 = _format_price(current_price_number + risk_distance * 2.5 if action == "BUY" else current_price_number - risk_distance * 2.5, current_price_number)
        else:
            tp2 = "N/A"

    if action == "WAIT":
        reason = signal.get("message") or (
            f"Chart {pair} terbaca dari TradingView MCP di sekitar harga {_format_price(current_price_number, current_price_number)}; perubahan 100 bar sekitar {summary.get('change_pct', 'n/a')}. "
            "Belum ada entry yang cukup valid, jadi posisi terbaik adalah menunggu konfirmasi."
        )
        if indicator_reason:
            reason = f"{reason} Tambahan data indikator: {indicator_reason}."
        invalid = signal.get("invalid_if") or "WAIT batal jika muncul breakout/retest valid dengan struktur SL dan target yang jelas."
    else:
        reason = signal.get("message") or (
            f"Chart {pair} terbaca dari TradingView MCP; perubahan 100 bar sekitar {summary.get('change_pct', 'n/a')}. "
            "Level entry, SL, dan TP fallback dihitung dari range chart terakhir karena analisis AI tidak tersedia."
        )
        if indicator_reason:
            reason = f"{reason} Tambahan data indikator: {indicator_reason}."
        invalid = signal.get("invalid_if") or "Setup batal jika harga menembus SL atau struktur berbalik melawan bias setup."

    return (
        f"⚪ {pair} — {action}\n\n"
        f"Bias: {bias}\n"
        f"Confidence: {confidence}%\n\n"
        f"Entry: {entry}\n"
        f"SL: {sl}\n"
        f"TP1: {tp1}\n"
        f"TP2: {tp2}\n\n"
        f"Reason:\n{reason}\n\n"
        f"Invalid jika:\n{invalid}\n\n"
        "Risk:\nGunakan lot sesuai manajemen risiko."
    )


def formatted_signal_message(
    context: dict[str, Any],
    signal: dict[str, Any] | None = None,
    ai_analysis: dict[str, Any] | None = None,
) -> str:
    if ai_analysis and ai_analysis.get("success") and ai_analysis.get("analysis"):
        return str(ai_analysis["analysis"]).strip()
    return fallback_signal_message(context, signal)


async def analyze_chart_context(context: dict[str, Any], signal: dict[str, Any] | None = None) -> dict[str, Any]:
    if not settings.ai_enabled:
        return {"success": False, "configured": False, "analysis": None}

    url = settings.ai_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.ai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an AI day-trade setup scanner for OneTapTrade. "
                    "Analyze one pair at a time. Decide if a valid day-trade setup exists. "
                    "Be selective. Do not force signals. Do not make swing-trade setups. "
                    "Do not invent data. If unclear, return WAIT or NO_SETUP. "
                    "A good NO_SETUP is better than a weak BUY or SELL. "
                    "You never execute trades. Follow the output format exactly."
                ),
            },
            {"role": "user", "content": build_chart_analysis_prompt(context, signal)},
        ],
        "temperature": 0.2,
        "max_tokens": 700,
    }
    headers = {"Authorization": f"Bearer {settings.ai_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return {
            "success": True,
            "configured": True,
            "model": settings.ai_model,
            "analysis": content,
        }
    except Exception as e:
        return {
            "success": False,
            "configured": True,
            "model": settings.ai_model,
            "analysis": None,
            "error": str(e),
        }
