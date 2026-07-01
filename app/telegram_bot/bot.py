import asyncio
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.logger import logger

BOT_COMMANDS = [
    {"command": "scan", "description": "Scan all configured pairs for day-trade setups"},
    {"command": "analyze", "description": "Alias for /scan"},
    {"command": "status", "description": "Show server and TradingView status"},
    {"command": "last_signal", "description": "Show latest TradingView signal"},
    {"command": "history", "description": "Show last 5 scan summaries"},
    {"command": "today", "description": "Show today's broadcasted setup recap"},
    {"command": "help", "description": "Show command list"},
]

CALLBACK_COMMANDS = {
    "cmd:scan": "/scan",
    "cmd:status": "/status",
    "cmd:last_signal": "/last_signal",
    "cmd:analyze": "/scan",
    "cmd:history": "/history",
    "cmd:today": "/today",
    "cmd:help": "/help",
}

SIGNAL_HEADER_RE = re.compile(r"^\s*⚪\s+(?P<symbol>\S+)\s+[—-]\s+(?P<action>BUY|SELL|WAIT)\b", re.MULTILINE)


def _telegram_url(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


def _allowed_chat(chat_id: Any) -> bool:
    return str(chat_id) in {str(settings.telegram_allowed_chat_id), str(settings.telegram_admin_chat_id or "")}


async def set_bot_commands() -> bool:
    if not settings.telegram_enabled:
        return False

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(_telegram_url("setMyCommands"), json={"commands": BOT_COMMANDS})
            response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to set Telegram bot commands: {e}")
        return False


def _telegram_text(text: str) -> str:
    return html.escape(text)


def menu_reply_markup() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Scan", "callback_data": "cmd:scan"},
                {"text": "Status", "callback_data": "cmd:status"},
            ],
            [
                {"text": "Last Signal", "callback_data": "cmd:last_signal"},
                {"text": "Help / Menu", "callback_data": "cmd:help"},
            ],
        ]
    }


def scan_loading_text(command_text: str, app_state) -> str:
    latest_signal = getattr(app_state, "latest_tradingview_signal", None)
    symbols, timeframe = _parse_analyze_args(command_text, latest_signal)
    return (
        "Scanning pairs...\n"
        f"Pairs: {len(symbols)}\n"
        f"Timeframe: {timeframe}\n"
        "TradingView scan, AI analysis, broadcast jalan."
    )


async def send_message(text: str, chat_id: str | None = None, reply_markup=None, parse_mode: str | None = "HTML") -> bool:
    if not settings.telegram_enabled:
        logger.warning("Telegram token or chat_id not configured; signal kept locally only")
        return False

    payload = {
        "chat_id": chat_id or settings.telegram_allowed_chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(_telegram_url("sendMessage"), json=payload)
            response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


async def send_photo(
    photo_path: str,
    caption: str | None = None,
    chat_id: str | None = None,
    parse_mode: str | None = "HTML",
    reply_markup=None,
) -> bool:
    if not settings.telegram_enabled:
        logger.warning("Telegram token or chat_id not configured; signal kept locally only")
        return False

    path = Path(photo_path)
    if not path.exists():
        logger.error(f"Telegram photo not found: {photo_path}")
        return False

    data = {"chat_id": chat_id or settings.telegram_allowed_chat_id}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if caption:
        data["caption"] = caption[:1024]
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup)

    try:
        with path.open("rb") as file_obj:
            files = {"photo": (path.name, file_obj, "image/png")}
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(_telegram_url("sendPhoto"), data=data, files=files)
                response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram photo: {e}")
        return False


async def send_chat_action(action: str = "typing", chat_id: str | None = None) -> bool:
    if not settings.telegram_enabled:
        return False

    payload = {"chat_id": chat_id or settings.telegram_allowed_chat_id, "action": action}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(_telegram_url("sendChatAction"), json=payload)
            response.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"Failed to send Telegram chat action: {e}")
        return False


async def answer_callback_query(callback_query_id: str, text: str | None = None) -> bool:
    if not settings.telegram_enabled:
        return False

    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(_telegram_url("answerCallbackQuery"), json=payload)
            response.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"Failed to answer Telegram callback: {e}")
        return False


def _format_signal(signal: dict[str, Any] | None) -> str:
    if not signal:
        return "Belum ada signal TradingView yang diterima."

    lines = [
        "<b>Last TradingView Signal</b>",
        f"<b>Symbol:</b> {html.escape(str(signal.get('symbol', '-')))}",
        f"<b>Action:</b> {html.escape(str(signal.get('action', '-')))}",
    ]
    for label, key in (
        ("Price", "price"),
        ("Timeframe", "timeframe"),
        ("Strategy", "strategy"),
        ("Message", "message"),
        ("Received", "received_at"),
    ):
        value = signal.get(key)
        if value not in (None, ""):
            lines.append(f"<b>{label}:</b> {html.escape(str(value))}")
    return "\n".join(lines)


def _help_message() -> str:
    lines = ["<b>OneTapTrade Commands</b>"]
    lines.extend(f"/{cmd['command']} - {html.escape(cmd['description'])}" for cmd in BOT_COMMANDS)
    lines.append("/menu - Show command list")
    return "\n".join(lines)


async def _status_message(app_state) -> str:
    try:
        from app.tradingview_mcp import run_tv_command

        status = await run_tv_command("status")
    except Exception as e:
        status = {"success": False, "error": str(e)}

    latest_signal = getattr(app_state, "latest_tradingview_signal", None)
    if status.get("success"):
        tv_line = (
            f"connected | {status.get('chart_symbol', 'unknown')} "
            f"TF {status.get('chart_resolution', 'unknown')}"
        )
    else:
        tv_line = f"not connected | {status.get('error', 'unknown error')}"

    return (
        "<b>OneTapTrade Status</b>\n"
        f"<b>Telegram:</b> connected\n"
        f"<b>TradingView:</b> {html.escape(tv_line)}\n"
        f"<b>Auto Signal:</b> {html.escape('enabled' if settings.auto_signal_enabled else 'disabled')}\n"
        f"<b>Last Signal:</b> {html.escape(str((latest_signal or {}).get('action', 'none')))}"
    )


async def _analysis_message(app_state) -> str:
    latest_signal = getattr(app_state, "latest_tradingview_signal", None)
    try:
        from app.ai_analysis import analyze_chart_context, formatted_signal_message
        from app.tradingview_mcp import get_chart_context

        context = await get_chart_context(
            include_screenshot=True,
            include_indicators=True,
            symbol=(latest_signal or {}).get("symbol"),
            timeframe=(latest_signal or {}).get("timeframe"),
        )
        if not context.get("success"):
            return f"TradingView belum siap: <code>{html.escape(str(context.get('status') or context))}</code>"

        analysis = await analyze_chart_context(context, latest_signal)
        return formatted_signal_message(context, latest_signal, analysis)
    except Exception as e:
        logger.error(f"Telegram analysis command failed: {e}")
        return f"Analysis gagal: <code>{html.escape(str(e))}</code>"


def _parse_analyze_args(text: str, latest_signal: dict[str, Any] | None = None) -> tuple[list[str], str]:
    parts = text.strip().split()[1:]
    timeframe = str((latest_signal or {}).get("timeframe") or settings.default_timeframe)
    symbols: list[str] = []

    for part in parts:
        for token in [value.strip() for value in part.split(",") if value.strip()]:
            lowered = token.lower()
            if lowered.startswith("tf=") or lowered.startswith("timeframe="):
                timeframe = token.split("=", 1)[1]
            elif lowered == "all":
                symbols.extend(settings.symbols)
            else:
                symbols.append(token)

    if not symbols:
        symbols = settings.symbols
    return list(dict.fromkeys(symbols)), timeframe


def parse_signal_summary(text: str) -> dict[str, Any]:
    header_match = SIGNAL_HEADER_RE.search(text or "")
    from app.signal_drawing import parse_signal

    parsed = parse_signal(text) or {}
    return {
        "symbol": parsed.get("symbol") or (header_match.group("symbol") if header_match else None),
        "action": parsed.get("action") or (header_match.group("action") if header_match else None),
        "confidence": parsed.get("confidence"),
        "setup_type": parsed.get("setup_type"),
    }


def should_send_auto_signal(text: str, min_confidence: int, send_wait: bool = False) -> bool:
    from app.signal_drawing import parse_signal, is_broadcastable

    parsed = parse_signal(text)
    if parsed is None:
        return False
    return is_broadcastable(parsed)


def _auto_signal_on_cooldown(summary: dict[str, Any], app_state) -> bool:
    cooldown_minutes = max(0, settings.auto_signal_cooldown_minutes)
    if cooldown_minutes == 0:
        return False

    symbol = summary.get("symbol")
    action = summary.get("action")
    if not symbol or not action:
        return False

    sent_at_by_key = getattr(app_state, "auto_signal_last_sent", None)
    if sent_at_by_key is None:
        app_state.auto_signal_last_sent = {}
        sent_at_by_key = app_state.auto_signal_last_sent

    setup_type = summary.get("setup_type", "")
    key = f"{symbol}:{action}:{setup_type}" if setup_type else f"{symbol}:{action}"
    sent_at = sent_at_by_key.get(key)
    if sent_at is None:
        return False
    return datetime.now(timezone.utc) - sent_at < timedelta(minutes=cooldown_minutes)


def _mark_auto_signal_sent(summary: dict[str, Any], app_state) -> None:
    symbol = summary.get("symbol")
    action = summary.get("action")
    if not symbol or not action:
        return
    sent_at_by_key = getattr(app_state, "auto_signal_last_sent", None)
    if sent_at_by_key is None:
        app_state.auto_signal_last_sent = {}
        sent_at_by_key = app_state.auto_signal_last_sent
    setup_type = summary.get("setup_type", "")
    key = f"{symbol}:{action}:{setup_type}" if setup_type else f"{symbol}:{action}"
    sent_at_by_key[key] = datetime.now(timezone.utc)


async def build_analysis_responses(text: str, app_state) -> list[dict[str, Any]]:
    latest_signal = getattr(app_state, "latest_tradingview_signal", None)
    symbols, timeframe = _parse_analyze_args(text, latest_signal)

    from app.ai_analysis import analyze_chart_context, formatted_signal_message
    from app.signal_drawing import draw_prediction
    from app.tradingview_mcp import get_chart_context, run_tv_command

    responses: list[dict[str, Any]] = []
    for symbol in symbols:
        signal = {"symbol": symbol, "action": "WAIT", "timeframe": timeframe}
        context = await get_chart_context(
            include_screenshot=True,
            include_indicators=True,
            symbol=symbol,
            timeframe=timeframe,
        )

        if not context.get("success"):
            responses.append(
                {
                    "text": f"⚪ {symbol} — WAIT\n\nReason:\nTradingView belum siap untuk pair ini.",
                    "photo_path": None,
                }
            )
            continue

        analysis = await analyze_chart_context(context, signal)
        message = formatted_signal_message(context, signal, analysis)
        drawing = await draw_prediction(message, context)
        screenshot = context.get("screenshot") or {}
        if drawing.get("success"):
            screenshot = await run_tv_command("screenshot", "-r", "chart")
        responses.append(
            {
                "text": message,
                "photo_path": screenshot.get("file_path") if screenshot.get("success") else None,
                "drawing": drawing,
            }
        )

    return responses


async def send_analysis_command_responses(text: str, app_state, chat_id: str) -> None:
    await send_scan_command_responses(text, app_state, chat_id)


async def send_scan_command_responses(text: str, app_state, admin_chat_id: str) -> None:
    from app.signal_drawing import parse_signal, is_broadcastable, channel_caption

    admin_id = str(admin_chat_id)
    await send_chat_action("typing", chat_id=admin_id)
    await send_message(
        _telegram_text(scan_loading_text(text, app_state)),
        chat_id=admin_id,
        reply_markup=menu_reply_markup(),
    )

    responses = await build_analysis_responses(text, app_state)
    latest_signal = getattr(app_state, "latest_tradingview_signal", None)
    _, timeframe = _parse_analyze_args(text, latest_signal)

    setup_pairs: list[str] = []
    broadcasted_setup_details: list[dict[str, Any]] = []
    no_setup_pairs: list[str] = []
    low_confidence_pairs: list[str] = []
    cooldown_pairs: list[str] = []
    error_pairs: list[str] = []
    broadcast_count = 0

    for response_payload in responses:
        analysis_text = response_payload.get("text") or ""
        parsed = parse_signal(analysis_text)

        if parsed is None:
            error_pairs.append("parse-error")
            continue

        symbol = parsed.get("symbol", "?")
        if not is_broadcastable(parsed):
            confidence = parsed.get("confidence")
            if confidence is not None and confidence < settings.auto_signal_min_confidence:
                low_confidence_pairs.append(symbol)
            else:
                no_setup_pairs.append(symbol)
            continue

        summary = parse_signal_summary(analysis_text)
        if _auto_signal_on_cooldown(summary, app_state):
            cooldown_pairs.append(f"{symbol}:{parsed.get('setup_type')}")
            continue

        if settings.auto_signal_max_broadcast_per_scan > 0 and broadcast_count >= settings.auto_signal_max_broadcast_per_scan:
            cooldown_pairs.append(f"{symbol}:{parsed.get('setup_type')} (max broadcast reached)")
            continue

        photo_path = response_payload.get("photo_path")
        missing_screenshot = not photo_path and settings.auto_signal_require_screenshot
        if missing_screenshot:
            no_setup_pairs.append(symbol)
            continue

        caption = channel_caption(parsed)
        channel_sent = False
        if settings.channel_enabled:
            if len(caption) > 1000:
                short_caption = caption[:997] + "..."
            else:
                short_caption = caption
            if photo_path:
                channel_sent = await send_photo(
                    str(photo_path),
                    short_caption,
                    chat_id=settings.telegram_channel_id,
                    parse_mode=None,
                )
            else:
                channel_sent = await send_message(short_caption, chat_id=settings.telegram_channel_id, parse_mode=None)
            if channel_sent and len(caption) > 1000:
                await send_message(caption, chat_id=settings.telegram_channel_id, parse_mode=None)

        if photo_path:
            sent_admin = await send_photo(
                str(photo_path),
                _telegram_text(analysis_text),
                chat_id=admin_id,
                reply_markup=menu_reply_markup(),
            )
        else:
            sent_admin = await send_message(
                _telegram_text(analysis_text),
                chat_id=admin_id,
                reply_markup=menu_reply_markup(),
            )

        if channel_sent:
            _mark_auto_signal_sent(summary, app_state)
            setup_pairs.append(f"{symbol} {parsed.get('setup_type')}")
            broadcasted_setup_details.append({
                "symbol": parsed.get("symbol"),
                "action": parsed.get("action"),
                "setup_type": parsed.get("setup_type"),
                "entry": parsed.get("entry"),
                "stop_loss": parsed.get("stop_loss"),
                "tp1": parsed.get("tp1"),
                "tp2": parsed.get("tp2"),
                "bias": parsed.get("bias"),
                "confidence": parsed.get("confidence"),
                "risk_reward": parsed.get("risk_reward"),
                "reason": parsed.get("reason"),
                "invalidation": parsed.get("invalidation"),
                "channel_sent": True,
            })
            broadcast_count += 1

    total = len(responses)
    summary_lines = [
        "AI DAY-TRADE MULTI-PAIR SCAN SUMMARY",
        "",
        f"Timeframe: {timeframe}",
        f"Scanned: {total} pairs",
        f"Broadcasted Setups: {broadcast_count}",
    ]
    if setup_pairs:
        summary_lines.append(f"Setup Pairs: {', '.join(setup_pairs)}")
    else:
        summary_lines.append("Setup Pairs: -")
    summary_lines.append(f"No Valid Setup: {len(no_setup_pairs)}")
    if no_setup_pairs:
        summary_lines.append(f"No-Setup Pairs: {', '.join(no_setup_pairs)}")
    if low_confidence_pairs:
        summary_lines.append(f"Low Confidence: {', '.join(low_confidence_pairs)}")
    if cooldown_pairs:
        summary_lines.append(f"Skipped by Cooldown: {', '.join(cooldown_pairs)}")
    if error_pairs:
        summary_lines.append(f"Errors: {len(error_pairs)}")
    summary_lines.append("")
    if broadcast_count > 0:
        summary_lines.append("Result: Setup day trade valid sudah dikirim ke channel.")
    else:
        summary_lines.append("Result: Tidak ada setup day trade valid. Tidak ada broadcast ke channel.")

    if broadcast_count == 0 and not settings.auto_signal_send_no_setup_summary:
        return

    await send_message(
        _telegram_text("\n".join(summary_lines)),
        chat_id=admin_id,
        reply_markup=menu_reply_markup(),
    )

    _log_scan_history(
        timeframe=timeframe,
        total_pairs=total,
        setup_pairs=broadcasted_setup_details,
        no_setup_pairs=no_setup_pairs,
        low_confidence_pairs=low_confidence_pairs,
        cooldown_pairs=cooldown_pairs,
        error_pairs=error_pairs,
    )


async def run_auto_signal_loop(app_state, stop_event: asyncio.Event) -> None:
    if not settings.auto_signal_enabled:
        logger.info("Auto signal disabled")
        return
    if not settings.telegram_enabled:
        logger.info("Auto signal disabled because Telegram is not configured")
        return
    if not settings.ai_enabled:
        logger.warning("Auto signal requires AI_API_KEY; loop not started")
        return

    interval_seconds = max(60, settings.auto_signal_interval_minutes * 60)
    timeframe = settings.auto_signal_timeframe or settings.default_timeframe
    command_text = f"/analyze all tf={timeframe}"
    logger.info(
        "Auto signal loop started: "
        f"symbols={settings.symbols} timeframe={timeframe} interval={interval_seconds}s"
    )

    while not stop_event.is_set():
        try:
            admin_id = settings.admin_chat_id or settings.telegram_allowed_chat_id
            await send_scan_command_responses(command_text, app_state, str(admin_id))
        except Exception as e:
            logger.warning(f"Auto signal scan failed: {e}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue

    logger.info("Auto signal loop stopped")


SCAN_COMMANDS = {"/scan", "/analyze", "/analysis"}


def build_today_setups_summary() -> str:
    path = _scan_history_path()
    if not path.exists():
        return "Belum ada setup valid yang dibroadcast hari ini."

    history = json.loads(path.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).date().isoformat()

    setups: list[dict[str, Any]] = []
    for entry in history:
        ts = entry.get("timestamp", "")
        if not ts.startswith(today):
            continue
        for bs in entry.get("broadcasted_setups", []):
            if isinstance(bs, str):
                setups.append({"legacy": True, "text": bs})
            elif isinstance(bs, dict) and bs.get("channel_sent"):
                setups.append(bs)

    if not setups:
        return "Belum ada setup valid yang dibroadcast hari ini."

    buy_count = sum(1 for s in setups if s.get("action") == "BUY")
    sell_count = sum(1 for s in setups if s.get("action") == "SELL")
    setup_types = [s.get("setup_type", "") for s in setups if isinstance(s.get("setup_type"), str)]
    most_common_type = max(set(setup_types), key=setup_types.count) if setup_types else "-"
    confidences = [s["confidence"] for s in setups if isinstance(s.get("confidence"), (int, float))]
    avg_conf = round(sum(confidences) / len(confidences)) if confidences else 0

    lines = [
        "AI DAY-TRADE SETUP RECAP \u2014 TODAY",
        "",
        f"Date: {today}",
        f"Total Setups: {len(setups)}",
        "",
    ]

    for i, s in enumerate(setups, 1):
        if s.get("legacy"):
            lines.append(f"{i}. {html.escape(s.get('text', '?'))}")
            lines.append("   Detail: not available from old history.")
        else:
            lines.append(f"{i}. {html.escape(str(s.get('symbol', '?')))} \u2014 {html.escape(str(s.get('action', '?')))}")
            lines.append(f"   Setup Type: {html.escape(str(s.get('setup_type', '-')))}")
            entry_val = s.get("entry")
            entry_str = f"{entry_val}" if entry_val is not None else "N/A"
            sl_val = s.get("stop_loss")
            sl_str = f"{sl_val}" if sl_val is not None else "N/A"
            tp1_val = s.get("tp1")
            tp1_str = f"{tp1_val}" if tp1_val is not None else "N/A"
            tp2_val = s.get("tp2")
            tp2_str = f"{tp2_val}" if tp2_val is not None else "N/A"
            lines.append(f"   Entry: {html.escape(entry_str)}")
            lines.append(f"   SL: {html.escape(sl_str)}")
            lines.append(f"   TP1: {html.escape(tp1_str)}   TP2: {html.escape(tp2_str)}")
            lines.append(f"   Bias: {html.escape(str(s.get('bias', '-')))}")
            conf = s.get("confidence")
            lines.append(f"   Confidence: {conf}%")
            rr = s.get("risk_reward")
            lines.append(f"   RR: 1:{rr if rr is not None else 'N/A'}")
            reason = s.get("reason", "")
            if reason:
                lines.append(f"   Reason: {html.escape(str(reason)[:120])}")
        lines.append("")

    if len(lines) > 80:
        short_lines = [
            "AI DAY-TRADE SETUP RECAP \u2014 TODAY",
            "",
            f"Date: {today} | Total: {len(setups)}",
            "",
        ]
        for i, s in enumerate(setups, 1):
            if s.get("legacy"):
                short_lines.append(f"{i}. {html.escape(s.get('text', '?'))}")
            else:
                conf = s.get("confidence")
                short_lines.append(
                    f"{i}. {html.escape(str(s.get('symbol', '?')))} {s.get('setup_type', '-')} | "
                    f"Conf: {conf}%"
                )
        lines = short_lines + [""]

    lines.append(f"Total: {len(setups)} | BUY: {buy_count} | SELL: {sell_count}")
    lines.append(f"Top Setup: {most_common_type}")
    if confidences:
        lines.append(f"Avg Confidence: {avg_conf}%")

    return "\n".join(lines)


def _scan_history_path() -> Path:
    path = Path("data/scan_history.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _log_scan_history(
    timeframe: str,
    total_pairs: int,
    setup_pairs: list[str],
    no_setup_pairs: list[str],
    low_confidence_pairs: list[str],
    cooldown_pairs: list[str],
    error_pairs: list[str],
) -> None:
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timeframe": timeframe,
            "scanned_pairs": total_pairs,
            "broadcasted_setups": setup_pairs,
            "no_setup_pairs": no_setup_pairs,
            "low_confidence_pairs": low_confidence_pairs,
            "cooldown_pairs": cooldown_pairs,
            "error_pairs": error_pairs,
        }
        path = _scan_history_path()
        history: list[dict[str, Any]] = []
        if path.exists():
            history = json.loads(path.read_text(encoding="utf-8"))
        history.append(entry)
        if len(history) > 200:
            history = history[-200:]
        path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to log scan history: {e}")


async def handle_command_text(text: str, app_state) -> str:
    command = text.strip().split()[0].split("@")[0].lower()

    if command == "/status":
        return await _status_message(app_state)
    if command == "/last_signal":
        return _format_signal(getattr(app_state, "latest_tradingview_signal", None))
    if command == "/history":
        path = _scan_history_path()
        if not path.exists():
            return "Belum ada scan history."
        history = json.loads(path.read_text(encoding="utf-8"))[-5:]
        lines = ["<b>Last 5 Scan History</b>", ""]
        for entry in reversed(history):
            ts = entry.get("timestamp", "?")[:16].replace("T", " ")
            lines.append(
                f"Time: {html.escape(ts)} | TF: {html.escape(str(entry.get('timeframe', '?')))} | "
                f"Scanned: {entry.get('scanned_pairs', 0)} | Broadcast: {len(entry.get('broadcasted_setups', []))}"
            )
        return "\n".join(lines)
    if command in SCAN_COMMANDS:
        responses = await build_analysis_responses(text, app_state)
        return "\n\n".join(response["text"] or "" for response in responses)
    if command in ("/help", "/menu"):
        return _help_message()
    if command in ("/today", "/setups_today", "/recap_today"):
        return build_today_setups_summary()

    return "Command tidak dikenal. Ketik /help."


async def _drop_pending_updates() -> int | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(_telegram_url("getUpdates"), params={"timeout": 0})
            response.raise_for_status()
            updates = response.json().get("result", [])
        if not updates:
            return None
        return max(update.get("update_id", 0) for update in updates) + 1
    except Exception as e:
        logger.warning(f"Failed to drop pending Telegram updates: {e}")
        return None


async def handle_callback_query(callback_query: dict[str, Any], app_state) -> None:
    callback_id = callback_query.get("id")
    command_text = CALLBACK_COMMANDS.get(callback_query.get("data"))
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if not _allowed_chat(chat_id):
        logger.warning(f"Ignoring Telegram callback from unauthorized chat_id={chat_id}")
        if callback_id:
            await answer_callback_query(callback_id, "Unauthorized")
        return
    if not command_text:
        if callback_id:
            await answer_callback_query(callback_id, "Unknown command")
        await send_message("Command tidak dikenal. Ketik /help.", chat_id=str(chat_id), reply_markup=menu_reply_markup())
        return

    if callback_id:
        await answer_callback_query(callback_id, "Loading scan..." if command_text in {"/scan", "/analyze"} else None)

    if command_text in {"/scan", "/analyze"}:
        await send_analysis_command_responses(command_text, app_state, str(chat_id))
        return

    reply = await handle_command_text(command_text, app_state)
    await send_message(reply, chat_id=str(chat_id), reply_markup=menu_reply_markup())


async def run_command_polling(app_state, stop_event: asyncio.Event) -> None:
    if not settings.telegram_enabled or not settings.telegram_command_polling_enabled:
        logger.info("Telegram command polling disabled")
        return

    await set_bot_commands()
    offset = await _drop_pending_updates()
    logger.info("Telegram command polling started")

    async with httpx.AsyncClient(timeout=40) as client:
        while not stop_event.is_set():
            try:
                response = await client.get(
                    _telegram_url("getUpdates"),
                    params={"timeout": 30, "offset": offset, "allowed_updates": '["message","callback_query"]'},
                )
                response.raise_for_status()
                updates = response.json().get("result", [])
            except Exception as e:
                logger.warning(f"Telegram polling error: {e}")
                await asyncio.sleep(5)
                continue

            for update in updates:
                offset = update.get("update_id", 0) + 1
                callback_query = update.get("callback_query")
                if callback_query:
                    await handle_callback_query(callback_query, app_state)
                    continue

                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                text = message.get("text") or ""
                if not text.startswith("/"):
                    continue
                if not _allowed_chat(chat_id):
                    logger.warning(f"Ignoring Telegram command from unauthorized chat_id={chat_id}")
                    continue

                command = text.strip().split()[0].split("@")[0].lower()
                if command in SCAN_COMMANDS:
                    await send_analysis_command_responses(text, app_state, str(chat_id))
                    continue

                reply = await handle_command_text(text, app_state)
                await send_message(reply, chat_id=str(chat_id), reply_markup=menu_reply_markup())

    logger.info("Telegram command polling stopped")
