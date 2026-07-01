import json
import re
import time
from typing import Any

from app.config import settings
from app.tradingview_mcp import run_tv_command

HEADER_RE = re.compile(r"^\s*⚪\s+(?P<symbol>\S+)\s+[\u2014\u2013\u2012\xad\u002d-—–]\s+(?P<action>BUY|SELL|WAIT)\b", re.MULTILINE)
LINE_RE = re.compile(r"^(?P<label>[A-Z][^:]+):\s*(?P<value>.+)$", re.MULTILINE)
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
        key = match.group("label").strip().upper()
        values[key] = match.group("value").strip()
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


def parse_signal(message: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    header = HEADER_RE.search(message or "")
    if not header:
        return None

    action = header.group("action")
    lines = _line_values(message)

    setup_type = str(lines.get("SETUP TYPE") or "").upper()
    day_trade = str(lines.get("DAY TRADE") or "").strip().upper()
    bias = str(lines.get("BIAS") or "").strip()
    confidence_raw = _float_value(lines.get("CONFIDENCE", ""))
    rr_raw = lines.get("RISK REWARD", "N/A")
    entry_line = str(lines.get("ENTRY") or "").strip()
    sl_line = str(lines.get("STOP LOSS") or "").strip()
    tp_line = str(lines.get("TAKE PROFIT") or "").strip()

    confidence = int(confidence_raw) if confidence_raw is not None else None

    rr_value: float | None = None
    rr_numeric = rr_raw.replace("1:", "").strip()
    rr_value = _float_value(rr_numeric)

    sl_numbers = _numbers_from_text(sl_line)
    sl = sl_numbers[0] if sl_numbers else None

    tp1: float | None = None
    tp2: float | None = None
    standalone_tp1 = _float_value(lines.get("TP1", ""))
    standalone_tp2 = _float_value(lines.get("TP2", ""))
    if standalone_tp1 is not None:
        tp1 = standalone_tp1
    if standalone_tp2 is not None:
        tp2 = standalone_tp2
    if tp1 is None or tp2 is None:
        tp_line = str(lines.get("TAKE PROFIT") or "").strip()
        for tpl in tp_line.split("\n"):
            tp_text = tpl.strip()
            if "TP1:" in tp_text.upper() and tp1 is None:
                tp1_nums = _numbers_from_text(tp_text.split("TP1:")[-1] if "TP1:" in tp_text.upper() else tp_text)
                tp1 = tp1_nums[0] if tp1_nums else None
            elif "TP2:" in tp_text.upper() and tp2 is None:
                tp2_nums = _numbers_from_text(tp_text.split("TP2:")[-1] if "TP2:" in tp_text.upper() else tp_text)
                tp2 = tp2_nums[0] if tp2_nums else None
            elif tp1 is None:
                tp1_nums = _numbers_from_text(tp_text)
                tp1 = tp1_nums[0] if tp1_nums else None

    entry_numbers = _numbers_from_text(entry_line)
    current_price = _current_price_from_context(context)
    if entry_line.upper().startswith("WAIT"):
        entry = None
        entry_type = "WAIT"
    elif "LIMIT" in entry_line.upper():
        entry = sum(entry_numbers) / len(entry_numbers) if entry_numbers else None
        entry_type = "LIMIT"
    elif "STOP" in entry_line.upper():
        entry = entry_numbers[0] if entry_numbers else None
        entry_type = "STOP"
    elif "MARKET" in entry_line.upper():
        entry = entry_numbers[0] if entry_numbers else current_price
        entry_type = "MARKET"
    else:
        entry = entry_numbers[0] if entry_numbers else current_price
        entry_type = "MARKET"

    reason = str(lines.get("AI REASON") or "").strip()
    invalidation = str(lines.get("INVALIDATION") or "").strip()

    return {
        "symbol": header.group("symbol"),
        "action": action,
        "setup_type": setup_type or f"{action}_MARKET",
        "day_trade": day_trade == "YES",
        "bias": bias,
        "confidence": confidence,
        "risk_reward": rr_value,
        "entry": entry,
        "entry_type": entry_type,
        "stop_loss": sl,
        "tp1": tp1,
        "tp2": tp2,
        "reason": reason,
        "invalidation": invalidation,
    }


def is_broadcastable(parsed: dict[str, Any]) -> bool:
    if parsed.get("action") not in {"BUY", "SELL"}:
        return False
    setup = parsed.get("setup_type", "")
    valid_setups = {"BUY_MARKET", "SELL_MARKET", "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP"}
    if setup not in valid_setups:
        return False
    if not parsed.get("day_trade"):
        return False
    confidence = parsed.get("confidence")
    if confidence is None or confidence < settings.auto_signal_min_confidence:
        return False
    rr = parsed.get("risk_reward")
    if rr is None or rr < settings.auto_signal_min_rr:
        return False
    if parsed.get("entry") is None:
        return False
    if parsed.get("stop_loss") is None:
        return False
    if parsed.get("tp1") is None:
        return False
    if not parsed.get("reason"):
        return False
    if not parsed.get("invalidation") or parsed.get("invalidation") in {"N/A", ""}:
        return False
    return True


def channel_caption(parsed: dict[str, Any]) -> str:
    tp1 = parsed.get("tp1")
    tp2 = parsed.get("tp2")
    tp_text = ""
    if tp1 is not None:
        tp_text += f"{tp1}"
    if tp2 is not None:
        tp_text += f"\nTP2: {tp2}" if tp_text else f"TP2: {tp2}"

    entry = parsed.get("entry")
    sl = parsed.get("stop_loss")
    entry_str = f"{entry}" if entry is not None else "N/A"
    sl_str = f"{sl}" if sl is not None else "N/A"

    return (
        f"AI DAY TRADE SETUP \u2014 {parsed.get('symbol', '-')}\n\n"
        f"Setup Type:\n{parsed.get('setup_type', '-')}\n\n"
        f"Entry:\n{entry_str}\n\n"
        f"Stop Loss:\n{sl_str}\n\n"
        f"Take Profit:\n"
        f"TP1: {tp1 if tp1 is not None else 'N/A'}\n"
        f"TP2: {tp2 if tp2 is not None else 'N/A'}\n\n"
        f"Market Bias:\n{parsed.get('bias', '-')}\n\n"
        f"Confidence:\n{parsed.get('confidence', '-')}%\n\n"
        f"Risk Reward:\n1:{parsed.get('risk_reward', 'N/A')}\n\n"
        f"AI Reason:\n{parsed.get('reason', '-')}\n\n"
        f"Invalidation:\n{parsed.get('invalidation', '-')}\n\n"
        f"Risk Reminder:\nGunakan lot sesuai manajemen risiko. Ini bukan financial advice."
    )


def parse_prediction_levels(message: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    parsed = parse_signal(message, context)
    if parsed is None:
        return None
    if parsed["action"] not in {"BUY", "SELL"}:
        return None
    if parsed["entry"] is None or parsed["stop_loss"] is None or parsed["tp1"] is None:
        return None
    entry = parsed["entry"]
    sl = parsed["stop_loss"]
    tp1 = parsed["tp1"]
    tp2 = parsed.get("tp2")
    target = tp2 if tp2 is not None else tp1

    if parsed["action"] == "BUY" and not (sl < entry < target):
        return None
    if parsed["action"] == "SELL" and not (sl > entry > target):
        return None

    return {
        "symbol": parsed["symbol"],
        "action": parsed["action"],
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "target": target,
        "entry_type": parsed.get("entry_type", "MARKET"),
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
