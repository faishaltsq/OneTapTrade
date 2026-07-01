import json
import re
import time
from typing import Any

from app.config import settings
from app.tradingview_mcp import run_tv_command

HEADER_RE = re.compile(r"^\s*⚪\s+(?P<symbol>\S+)\s+[—-]\s+(?P<action>BUY|SELL|WAIT)\b", re.MULTILINE)
LINE_RE = re.compile(r"^(?P<label>Entry|SL|TP1|TP2):\s*(?P<value>.+)$", re.IGNORECASE | re.MULTILINE)
NUMBER_RE = re.compile(r"(?<![\d.,])-?\d+(?:[.,]\d+)?")


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


def _numbers_from_text(text: str) -> list[float]:
    values: list[float] = []
    for match in NUMBER_RE.findall(text):
        value = _float_value(match)
        if value is not None:
            values.append(value)
    return values


def _line_values(message: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in LINE_RE.finditer(message or ""):
        values[match.group("label").upper()] = match.group("value").strip()
    return values


def _current_price_from_context(context: dict[str, Any] | None) -> float | None:
    context = context or {}
    quote = context.get("quote") or {}
    return _float_value(quote.get("last") or quote.get("close"))


def _latest_bar_time(context: dict[str, Any] | None) -> int:
    context = context or {}
    bars_payload = context.get("ohlcv_bars") or {}
    bars = bars_payload.get("bars") if isinstance(bars_payload, dict) else []
    if isinstance(bars, list) and bars:
        latest_time = _float_value((bars[-1] or {}).get("time") if isinstance(bars[-1], dict) else None)
        if latest_time is not None:
            return int(latest_time)
    return int(time.time())


def _timeframe_seconds(context: dict[str, Any] | None) -> int:
    context = context or {}
    state = context.get("state") or {}
    status = context.get("status") or {}
    resolution = str(state.get("resolution") or status.get("chart_resolution") or settings.default_timeframe).upper()
    if resolution in {"D", "1D"}:
        return 86400
    if resolution in {"W", "1W"}:
        return 604800
    if resolution in {"M", "1M"}:
        return 2592000
    value = _float_value(resolution)
    return int(value * 60) if value else 3600


def parse_prediction_levels(message: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    header = HEADER_RE.search(message or "")
    if not header:
        return None

    action = header.group("action")
    if action not in {"BUY", "SELL"}:
        return None

    lines = _line_values(message)
    entry_line = lines.get("ENTRY", "")
    if entry_line.upper().startswith("WAIT"):
        return None

    entry_numbers = _numbers_from_text(entry_line)
    current_price = _current_price_from_context(context)
    if len(entry_numbers) >= 2 and ("-" in entry_line or "to" in entry_line.lower()):
        entry = (entry_numbers[0] + entry_numbers[1]) / 2
    elif entry_numbers:
        entry = entry_numbers[0]
    else:
        entry = current_price

    sl_numbers = _numbers_from_text(lines.get("SL", ""))
    tp1_numbers = _numbers_from_text(lines.get("TP1", ""))
    tp2_numbers = _numbers_from_text(lines.get("TP2", ""))
    sl = sl_numbers[0] if sl_numbers else None
    tp1 = tp1_numbers[0] if tp1_numbers else None
    tp2 = tp2_numbers[0] if tp2_numbers else None

    if entry is None or sl is None or tp1 is None:
        return None
    target = tp2 if tp2 is not None else tp1

    if action == "BUY" and not (sl < entry < target):
        return None
    if action == "SELL" and not (sl > entry > target):
        return None

    return {
        "symbol": header.group("symbol"),
        "action": action,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "target": target,
        "entry_type": "LIMIT" if "LIMIT" in entry_line.upper() else "MARKET",
    }


async def _draw_shape(shape: str, start_time: int, price: float, end_time: int | None = None, price2: float | None = None, text: str | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    args = [
        "draw",
        "shape",
        "--type",
        shape,
        "--time",
        str(start_time),
        "--price",
        str(price),
    ]
    if end_time is not None and price2 is not None:
        args.extend(["--time2", str(end_time), "--price2", str(price2)])
    if text:
        args.extend(["--text", text])
    if overrides:
        args.extend(["--overrides", json.dumps(overrides)])
    return await run_tv_command(*args)


async def draw_prediction(message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    if not settings.prediction_drawing_enabled:
        return {"success": False, "enabled": False, "reason": "Prediction drawing disabled"}

    levels = parse_prediction_levels(message, context)
    if not levels:
        return {"success": False, "enabled": True, "reason": "No drawable BUY/SELL setup"}

    start_time = _latest_bar_time(context)
    end_time = start_time + max(1, settings.prediction_drawing_bars_ahead) * _timeframe_seconds(context)
    action = levels["action"]
    entry = levels["entry"]
    sl = levels["sl"]
    target = levels["target"]
    tp1 = levels["tp1"]
    tp2 = levels.get("tp2")

    if action == "BUY":
        reward_low, reward_high = entry, target
        risk_low, risk_high = sl, entry
        label = f"LONG {levels['symbol']} {levels['entry_type']}"
    else:
        reward_low, reward_high = target, entry
        risk_low, risk_high = entry, sl
        label = f"SHORT {levels['symbol']} {levels['entry_type']}"

    commands = [
        await _draw_shape("rectangle", start_time, reward_low, end_time, reward_high, overrides={"color": "#16a34a", "backgroundColor": "rgba(22, 163, 74, 0.16)", "linewidth": 1}),
        await _draw_shape("rectangle", start_time, risk_low, end_time, risk_high, overrides={"color": "#dc2626", "backgroundColor": "rgba(220, 38, 38, 0.16)", "linewidth": 1}),
        await _draw_shape("horizontal_line", start_time, entry, text="Entry", overrides={"linecolor": "#2563eb", "linewidth": 2}),
        await _draw_shape("horizontal_line", start_time, sl, text="SL", overrides={"linecolor": "#dc2626", "linewidth": 2}),
        await _draw_shape("horizontal_line", start_time, tp1, text="TP1", overrides={"linecolor": "#16a34a", "linewidth": 2}),
        await _draw_shape("text", start_time, entry, text=label, overrides={"color": "#111827", "textColor": "#111827"}),
    ]
    if tp2 is not None:
        commands.append(await _draw_shape("horizontal_line", start_time, tp2, text="TP2", overrides={"linecolor": "#22c55e", "linewidth": 2}))

    return {
        "success": any(command.get("success") for command in commands),
        "enabled": True,
        "levels": levels,
        "commands": commands,
    }
