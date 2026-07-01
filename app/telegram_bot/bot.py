import asyncio
import html
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.logger import logger

BOT_COMMANDS = [
    {"command": "status", "description": "Show server and TradingView status"},
    {"command": "last_signal", "description": "Show latest TradingView signal"},
    {"command": "analyze", "description": "Analyze configured pairs"},
    {"command": "help", "description": "Show command list"},
]

SIGNAL_HEADER_RE = re.compile(r"^\s*⚪\s+(?P<symbol>\S+)\s+[—-]\s+(?P<action>BUY|SELL|WAIT)\b", re.MULTILINE)
CONFIDENCE_RE = re.compile(r"^Confidence:\s*(?P<confidence>\d+(?:\.\d+)?)\s*%", re.IGNORECASE | re.MULTILINE)


def _telegram_url(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


def _allowed_chat(chat_id: Any) -> bool:
    return str(chat_id) == str(settings.telegram_allowed_chat_id)


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


async def send_photo(photo_path: str, caption: str | None = None, chat_id: str | None = None, parse_mode: str | None = "HTML") -> bool:
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
    confidence_match = CONFIDENCE_RE.search(text or "")

    confidence = None
    if confidence_match:
        try:
            confidence = int(float(confidence_match.group("confidence")))
        except ValueError:
            confidence = None

    return {
        "symbol": header_match.group("symbol") if header_match else None,
        "action": header_match.group("action") if header_match else None,
        "confidence": confidence,
    }


def should_send_auto_signal(text: str, min_confidence: int, send_wait: bool = False) -> bool:
    summary = parse_signal_summary(text)
    action = summary.get("action")
    confidence = summary.get("confidence")

    if action == "WAIT":
        return send_wait
    if action not in {"BUY", "SELL"}:
        return False
    if confidence is None:
        return False
    return confidence >= min_confidence


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

    key = f"{symbol}:{action}"
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
    sent_at_by_key[f"{symbol}:{action}"] = datetime.now(timezone.utc)


async def build_analysis_responses(text: str, app_state) -> list[dict[str, str | None]]:
    latest_signal = getattr(app_state, "latest_tradingview_signal", None)
    symbols, timeframe = _parse_analyze_args(text, latest_signal)

    from app.ai_analysis import analyze_chart_context, formatted_signal_message
    from app.tradingview_mcp import get_chart_context

    responses: list[dict[str, str | None]] = []
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
        screenshot = context.get("screenshot") or {}
        responses.append(
            {
                "text": formatted_signal_message(context, signal, analysis),
                "photo_path": screenshot.get("file_path") if screenshot.get("success") else None,
            }
        )

    return responses


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
            responses = await build_analysis_responses(command_text, app_state)
            for response_payload in responses:
                analysis_text = response_payload.get("text") or ""
                if not should_send_auto_signal(
                    analysis_text,
                    min_confidence=settings.auto_signal_min_confidence,
                    send_wait=settings.auto_signal_send_wait,
                ):
                    continue

                summary = parse_signal_summary(analysis_text)
                if _auto_signal_on_cooldown(summary, app_state):
                    continue

                photo_path = response_payload.get("photo_path")
                if photo_path:
                    sent = await send_photo(str(photo_path), _telegram_text(analysis_text))
                else:
                    sent = await send_message(_telegram_text(analysis_text))
                if sent:
                    _mark_auto_signal_sent(summary, app_state)
        except Exception as e:
            logger.warning(f"Auto signal scan failed: {e}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue

    logger.info("Auto signal loop stopped")


async def handle_command_text(text: str, app_state) -> str:
    command = text.strip().split()[0].split("@")[0].lower()

    if command == "/status":
        return await _status_message(app_state)
    if command == "/last_signal":
        return _format_signal(getattr(app_state, "latest_tradingview_signal", None))
    if command in ("/analyze", "/analysis"):
        responses = await build_analysis_responses(text, app_state)
        return "\n\n".join(response["text"] or "" for response in responses)
    if command in ("/help", "/menu"):
        lines = ["<b>OneTapTrade Commands</b>"]
        lines.extend(f"/{cmd['command']} - {html.escape(cmd['description'])}" for cmd in BOT_COMMANDS)
        lines.append("/menu - Show command list")
        return "\n".join(lines)

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
                    params={"timeout": 30, "offset": offset, "allowed_updates": '["message"]'},
                )
                response.raise_for_status()
                updates = response.json().get("result", [])
            except Exception as e:
                logger.warning(f"Telegram polling error: {e}")
                await asyncio.sleep(5)
                continue

            for update in updates:
                offset = update.get("update_id", 0) + 1
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
                if command in ("/analyze", "/analysis"):
                    responses = await build_analysis_responses(text, app_state)
                    for response_payload in responses:
                        analysis_text = response_payload.get("text") or ""
                        photo_path = response_payload.get("photo_path")
                        if photo_path:
                            await send_photo(str(photo_path), _telegram_text(analysis_text), chat_id=str(chat_id))
                        else:
                            await send_message(_telegram_text(analysis_text), chat_id=str(chat_id))
                    continue

                reply = await handle_command_text(text, app_state)
                await send_message(reply, chat_id=str(chat_id))

    logger.info("Telegram command polling stopped")
