import asyncio
from typing import Optional

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from app.config import settings
from app.logger import logger
from app.telegram_bot.message_templates import build_main_menu_keyboard, format_signal_message

async def capture_tv_screenshot() -> Optional[bytes]:
    try:
        from app.tv_connector import get_tv_tools

        tools = get_tv_tools()
        if tools is None:
            return None
        return await tools.capture_screenshot("chart")
    except Exception as e:
        logger.debug(f"TV screenshot capture failed: {e}")
        return None


_application: Optional[Application] = None
_pending_decisions: dict = {}
_decision_symbols: dict[str, str] = {}
_trading_loop_ref = None
_bot_stop_event: Optional[asyncio.Event] = None
_bot_initialized = False
_bot_started = False
_polling_started = False
_bot_stopping = False


async def _error_handler(update: object, context) -> None:
    logger.error(f"Telegram error: {context.error}")
    if update and hasattr(update, "effective_chat"):
        logger.error(f"  chat_id: {update.effective_chat.id if update.effective_chat else 'N/A'}")


def init_telegram_bot(trading_loop=None) -> bool:
    global _application, _trading_loop_ref, _bot_stop_event
    global _bot_initialized, _bot_started, _polling_started, _bot_stopping

    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured — bot unavailable")
        return False

    try:
        _application = Application.builder().token(settings.telegram_bot_token).build()

        _application.add_error_handler(_error_handler)

        from telegram.ext import MessageHandler, filters

        from app.telegram_bot.commands import get_command_handlers, unknown_command
        from app.telegram_bot.callbacks import get_callback_handlers

        for handler in get_command_handlers():
            _application.add_handler(handler)

        for handler in get_callback_handlers():
            _application.add_handler(handler)

        _application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

        _trading_loop_ref = trading_loop
        _bot_stop_event = None
        _bot_initialized = False
        _bot_started = False
        _polling_started = False
        _bot_stopping = False

        logger.info("Telegram bot initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Telegram bot: {e}")
        return False


def get_bot_application() -> Optional[Application]:
    return _application


def get_trading_loop():
    return _trading_loop_ref


async def _set_bot_commands() -> None:
    if _application is None or _application.bot is None:
        return

    try:
        await _application.bot.set_my_commands(
            [
                BotCommand("menu", "Show control menu"),
                BotCommand("help", "Show command list"),
                BotCommand("status", "Show bot status"),
                BotCommand("positions", "Show open positions"),
                BotCommand("last_signal", "Show latest AI signal"),
                BotCommand("pause", "Stop new trades"),
                BotCommand("resume", "Resume new trades"),
                BotCommand("settings", "Show current settings"),
                BotCommand("chart", "Capture TradingView chart"),
            ]
        )
    except Exception as e:
        logger.warning(f"Failed to set Telegram command menu: {e}")


async def run_bot() -> None:
    global _bot_stop_event, _bot_initialized, _bot_started, _polling_started

    if _application is None:
        logger.warning("Bot application not initialized, cannot run")
        return

    if not settings.telegram_allowed_chat_id:
        logger.warning("No allowed chat_id configured")

    app = _application
    _bot_stop_event = asyncio.Event()

    try:
        logger.info("Starting Telegram bot polling...")
        await app.initialize()
        _bot_initialized = True

        await _set_bot_commands()

        await app.start()
        _bot_started = True

        if app.updater is None:
            raise RuntimeError("Telegram updater unavailable")

        await app.updater.start_polling(drop_pending_updates=True)
        _polling_started = True
        logger.info("Telegram bot polling started")

        await _bot_stop_event.wait()
        logger.info("Telegram bot polling stopped")
    except asyncio.CancelledError:
        logger.info("Telegram bot polling task cancelled")
        raise
    except Exception as e:
        logger.exception(f"Telegram bot polling failed: {e}")


async def _shutdown_application(app: Application) -> None:
    global _bot_initialized, _bot_started, _polling_started, _bot_stopping

    if _bot_stopping:
        return

    _bot_stopping = True
    try:
        if _polling_started and app.updater is not None:
            await app.updater.stop()
            _polling_started = False
        if _bot_started:
            await app.stop()
            _bot_started = False
        if _bot_initialized:
            await app.shutdown()
            _bot_initialized = False
    finally:
        _bot_stopping = False


async def stop_bot() -> None:
    global _application, _bot_stop_event
    if _application is None:
        return

    logger.info("Stopping Telegram bot...")
    try:
        app = _application
        if _bot_stop_event is not None:
            _bot_stop_event.set()
        await _shutdown_application(app)
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
    finally:
        _application = None
        _bot_stop_event = None
        logger.info("Telegram bot stopped")


async def send_message(text: str, reply_markup=None) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_allowed_chat_id:
        logger.warning("Bot token or allowed chat_id not configured — cannot send message")
        return False

    if _application is None or _application.bot is None:
        logger.warning("Bot application not available — cannot send message")
        return False

    try:
        await _application.bot.send_message(
            chat_id=settings.telegram_allowed_chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


async def send_main_menu(text: str = None) -> bool:
    paused = False
    mode = settings.bot_mode
    active = "ALL"
    if _trading_loop_ref is not None:
        try:
            paused = _trading_loop_ref.is_paused()
            mode = _trading_loop_ref.status.mode
            active = _trading_loop_ref.status.active_symbol
        except Exception:
            pass

    sym_count = len(settings.symbols)
    header = text or f"<b>\U0001f916 OneTapTrade Bot</b>\n<b>Pair:</b> {active} ({sym_count} pairs) | {mode} | {'\U0001f6d1 Stop Trade' if paused else '\u25b6\ufe0f Trading Running'}"
    return await send_message(header, reply_markup=build_main_menu_keyboard(is_paused=paused, mode=mode, active_symbol=active))


async def send_trade_signal(decision, risk_result: dict, decision_id: str, market_payload: dict | None = None) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_allowed_chat_id:
        logger.warning("Cannot send trade signal — bot not configured")
        return False

    if _application is None or _application.bot is None:
        logger.warning("Bot application not available")
        return False

    try:
        symbol = risk_result.get("symbol", settings.default_symbol)
        signal_text = format_signal_message(decision, risk_result, symbol, market_payload=market_payload)

        reply_markup = None
        if settings.is_semi_auto and risk_result.get("approved"):
            keyboard = [
                [
                    InlineKeyboardButton(
                        "\u2705 Approve Trade",
                        callback_data=f"APPROVE_TRADE:{decision_id}",
                    ),
                    InlineKeyboardButton(
                        "\u274c Reject Trade",
                        callback_data=f"REJECT_TRADE:{decision_id}",
                    ),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

        _decision_symbols[decision_id] = symbol
        _pending_decisions[decision_id] = decision

        sent = await send_message(signal_text, reply_markup=reply_markup)
        if sent:
            logger.info(f"Trade signal sent for decision {decision_id}")

        try:
            screenshot = await capture_tv_screenshot()
            if screenshot and settings.telegram_allowed_chat_id:
                from io import BytesIO

                img = BytesIO(screenshot)
                img.name = "chart.png"
                await _application.bot.send_photo(
                    chat_id=settings.telegram_allowed_chat_id,
                    photo=img,
                    caption="\U0001f4ca TradingView Chart",
                )
        except Exception as e:
            logger.warning(f"Failed to send TV screenshot: {e}")

        return sent
    except Exception as e:
        logger.error(f"Failed to send trade signal: {e}")
        return False


async def notify_trade_executed(trade_result: dict) -> bool:
    ticket = trade_result.get("ticket") or trade_result.get("order")
    symbol = trade_result.get("symbol", settings.default_symbol)
    volume = trade_result.get("volume", "?")
    price = trade_result.get("price", "?")

    text = (
        "<b>\u2705 Trade Executed</b>\n\n"
        f"<b>Ticket:</b> <code>{ticket}</code>\n"
        f"<b>Symbol:</b> <code>{symbol}</code>\n"
        f"<b>Volume:</b> {volume}\n"
        f"<b>Price:</b> {price}"
    )

    return await send_message(text)


async def notify_trade_rejected(reason: str, decision=None) -> bool:
    lines = ["<b>\u274c Trade Rejected</b>\n"]
    lines.append(f"<b>Reason:</b> <i>{reason}</i>")

    if decision is not None:
        try:
            d = getattr(decision, "decision", None)
            decision_str = d.value if hasattr(d, "value") else str(d or "?")
            conf = getattr(decision, "confidence", 0.0)
            regime = getattr(decision, "market_regime", None)
            htf = getattr(decision, "higher_timeframe_bias", None)
            etf = getattr(decision, "entry_timeframe_bias", None)
            entry_plan = getattr(decision, "entry_plan", None)
            sl = getattr(entry_plan, "stop_loss", None) if entry_plan else None
            tp1 = getattr(entry_plan, "take_profit_1", None) if entry_plan else None
            rr = getattr(entry_plan, "risk_reward_to_tp1", None) if entry_plan else None

            d_emoji = "\U0001f7e2" if decision_str == "BUY" else ("\U0001f534" if decision_str == "SELL" else "\u26aa")
            lines.append(f"\n{d_emoji} <b>{decision_str}</b> | Confidence: {conf:.0%}")

            trend_parts = []
            if htf:
                htf_s = htf.value if hasattr(htf, "value") else str(htf)
                trend_parts.append(f"D1: {htf_s}")
            if etf:
                etf_s = etf.value if hasattr(etf, "value") else str(etf)
                trend_parts.append(f"M5: {etf_s}")
            if regime:
                reg_s = regime.value if hasattr(regime, "value") else str(regime)
                trend_parts.append(f"Regime: {reg_s}")
            if trend_parts:
                lines.append(f"<b>Trend:</b> {' | '.join(trend_parts)}")

            if sl:
                lines.append(f"<b>SL:</b> {sl}")
            if tp1:
                rr_str = f" (R:R {rr:.1f})" if rr else ""
                lines.append(f"<b>TP1:</b> {tp1}{rr_str}")
        except Exception:
            pass

    return await send_message("\n".join(lines))
