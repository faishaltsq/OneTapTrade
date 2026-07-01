import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.logger import logger

router = APIRouter(prefix="/tradingview")


def _first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_signal(payload: dict[str, Any]) -> dict[str, Any]:
    action = _first_value(payload, "action", "side", "signal", "order_action", "strategy_action")
    if isinstance(action, str):
        action = action.upper()

    return {
        "source": "TRADINGVIEW",
        "symbol": _first_value(payload, "symbol", "ticker", "pair") or settings.default_symbol,
        "action": action or "ALERT",
        "price": _first_value(payload, "price", "close", "entry", "entry_price"),
        "timeframe": _first_value(payload, "timeframe", "interval", "tf"),
        "strategy": _first_value(payload, "strategy", "strategy_name", "name"),
        "message": _first_value(payload, "message", "text", "comment"),
        "stop_loss": _first_value(payload, "stop_loss", "sl"),
        "take_profit": _first_value(payload, "take_profit", "tp", "take_profit_1", "tp1"),
        "raw": payload,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


async def _read_payload(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {}

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {"message": raw.decode("utf-8", errors="replace")}

    if isinstance(parsed, dict):
        return parsed
    return {"message": parsed}


@router.post("/webhook")
async def tradingview_webhook(request: Request):
    payload = await _read_payload(request)

    expected_secret = settings.tradingview_webhook_secret
    provided_secret = (
        request.headers.get("X-Webhook-Secret")
        or request.query_params.get("secret")
        or payload.get("secret")
    )
    if expected_secret and provided_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    signal = _normalize_signal(payload)
    request.app.state.latest_tradingview_signal = signal

    chart_context = None
    ai_analysis = None
    screenshot_path = None
    if settings.capture_chart_on_signal or settings.ai_analysis_on_signal:
        try:
            from app.tradingview_mcp import get_chart_context

            chart_context = await get_chart_context(
                include_screenshot=settings.capture_chart_on_signal,
                include_indicators=settings.ai_analysis_on_signal,
                symbol=str(signal.get("symbol")) if signal.get("symbol") else None,
                timeframe=str(signal.get("timeframe")) if signal.get("timeframe") else None,
            )
            screenshot = chart_context.get("screenshot") if chart_context else None
            if isinstance(screenshot, dict) and screenshot.get("success"):
                screenshot_path = screenshot.get("file_path")
        except Exception as e:
            logger.warning(f"Failed to fetch TradingView MCP chart context: {e}")

    if settings.ai_analysis_on_signal and chart_context:
        try:
            from app.ai_analysis import analyze_chart_context

            ai_analysis = await analyze_chart_context(chart_context, signal)
        except Exception as e:
            ai_analysis = {"success": False, "error": str(e)}
            logger.warning(f"Failed to run AI chart analysis: {e}")

    telegram_sent = False
    try:
        from app.ai_analysis import formatted_signal_message

        telegram_message = formatted_signal_message(chart_context or {}, signal, ai_analysis)
    except Exception:
        telegram_message = f"⚪ {signal['symbol']} — {signal['action']}\n\nReason:\nTradingView signal diterima."
    try:
        from app.telegram_bot.bot import send_message, send_photo

        if screenshot_path:
            telegram_sent = await send_photo(screenshot_path, telegram_message, parse_mode=None)
        else:
            telegram_sent = await send_message(telegram_message, parse_mode=None)
    except Exception as e:
        logger.warning(f"Failed to forward TradingView signal to Telegram: {e}")

    logger.info(f"TradingView signal received: {signal['action']} {signal['symbol']}")
    return {
        "status": "received",
        "signal": signal,
        "telegram_sent": telegram_sent,
        "screenshot_path": screenshot_path,
        "chart_context_success": chart_context.get("success") if chart_context else None,
        "ai_analysis": ai_analysis,
    }


@router.get("/last-signal")
async def last_tradingview_signal(request: Request):
    signal = getattr(request.app.state, "latest_tradingview_signal", None)
    return {"signal": signal}
