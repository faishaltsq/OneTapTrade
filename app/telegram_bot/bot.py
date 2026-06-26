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
    header = text or f"<b>\U0001f916 OneTapTrade Bot</b>\n<b>Pair:</b> {active} ({sym_count} pairs) | {mode} | {'\u23f8\ufe0f Auto Signal OFF' if paused else '\u25b6\ufe0f Auto Signal ON'}"
    return await send_message(header, reply_markup=build_main_menu_keyboard(is_paused=paused, mode=mode, active_symbol=active))


def _build_limit_recommendation(market_payload: dict | None) -> str:
    if not market_payload:
        return ""
    smc = market_payload.get("smc", {})
    major_trend = market_payload.get("major_trend", {})
    price = market_payload.get("current_price", {})
    mid = price.get("mid", 0)

    lines = []
    d1_bias = major_trend.get("bias", "")
    allowed = major_trend.get("allowed_directions", [])

    order_blocks = smc.get("order_blocks", {})
    demand = order_blocks.get("demand", []) or []
    supply = order_blocks.get("supply", []) or []

    if "BUY" in allowed and demand:
        nearest = demand[-1] if isinstance(demand[-1], dict) else {}
        low = nearest.get("low")
        high = nearest.get("high")
        if low and high and mid > 0:
            zone = f"{low} – {high}"
            lines.append(f"\u2191 <b>BUY LIMIT</b> zone: {zone}")
            if low > mid:
                lines.append(f"   Wait for retrace to demand block")
            else:
                lines.append(f"   Price inside demand zone — wait for confirmation")
            lines.append(f"   SL: below {low} | TP: next supply block")

    if "SELL" in allowed and supply:
        nearest = supply[-1] if isinstance(supply[-1], dict) else {}
        high_val = nearest.get("high")
        low_val = nearest.get("low")
        if high_val and low_val and mid > 0:
            zone = f"{low_val} – {high_val}"
            lines.append(f"\u2193 <b>SELL LIMIT</b> zone: {zone}")
            if high_val < mid:
                lines.append(f"   Wait for retrace to supply block")
            else:
                lines.append(f"   Price inside supply zone — wait for confirmation")
            lines.append(f"   SL: above {high_val} | TP: next demand block")

    if not lines:
        choch = smc.get("choch", {})
        choch_dir = choch.get("direction", "")
        if choch_dir and choch_dir != "NONE":
            direction = "Bullish" if "BULL" in str(choch_dir).upper() else "Bearish"
            lines.append(f"\u26a0 CHoCH: {direction} — potential reversal, wait for confirmation")

        liquidity = smc.get("liquidity_levels", []) or []
        if liquidity:
            liq = liquidity[0] if isinstance(liquidity[0], dict) else {}
            liq_price = liq.get("price")
            liq_type = liq.get("type", "level")
            if liq_price:
                lines.append(f"\U0001f4cd Liquidity at {liq_price} ({liq_type}) — price likely to target this")

    return "\n".join(lines) if lines else ""


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
        chat_id = settings.telegram_allowed_chat_id
        decision_str = getattr(decision, "decision", None)
        if hasattr(decision_str, "value"):
            decision_str = decision_str.value

        reply_markup = None
        if settings.is_semi_auto and risk_result.get("approved"):
            keyboard = [
                [
                    InlineKeyboardButton("\u2705 Approve Trade", callback_data=f"APPROVE_TRADE:{decision_id}"),
                    InlineKeyboardButton("\u274c Reject Trade", callback_data=f"REJECT_TRADE:{decision_id}"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

        _decision_symbols[decision_id] = symbol
        _pending_decisions[decision_id] = decision

        entry_plan = getattr(decision, "entry_plan", None)
        entry_price = getattr(entry_plan, "preferred_entry_price", None) if entry_plan else None
        stop_loss = getattr(entry_plan, "stop_loss", None) if entry_plan else None
        take_profit = getattr(entry_plan, "take_profit_1", None) if entry_plan else None

        from app.services.tv_autochart_service import draw_and_capture_multi_tf

        if decision_str in ("BUY", "SELL"):
            tfs = ["D1", "H1", "M5"]
            iface_label = {"D1": "\U0001f4ca D1 \u2014 Daily Trend", "H1": "\U0001f4ca H1 \u2014 Execution Bias", "M5": "\U0001f4ca M5 \u2014 Entry Trigger"}
        else:
            tfs = ["D1", "H1", "M5"]
            iface_label = {"D1": "\U0001f4ca D1 \u2014 Daily Trend", "H1": "\U0001f4ca H1 \u2014 Execution Bias", "M5": "\U0001f4ca M5 \u2014 Entry Trigger"}

            limit_recs = _build_limit_recommendation(market_payload)
            if limit_recs:
                signal_text += f"\n\n<b>\U0001f4cd Limit Rekomendasi (SMC+AI):</b>\n{limit_recs}"

        charts = await draw_and_capture_multi_tf(
            mt5_symbol=symbol,
            decision=decision_str or "HOLD",
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timeframes=tfs,
            market_payload=market_payload,
        )

        if not charts:
            return False

        from io import BytesIO

        for i, chart in enumerate(charts):
            img_data = chart["image"]
            tf = chart["timeframe"]
            tf_label = iface_label.get(tf, f"\U0001f4ca {tf}")

            caption = f"{tf_label}\n{signal_text}" if i == 0 else tf_label

            img = BytesIO(img_data)
            img.name = f"{symbol}_{tf}.png"
            await _application.bot.send_photo(
                chat_id=chat_id,
                photo=img,
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup if i == 0 else None,
            )

        try:
            from app.signal_bot import broadcast_signal
            m5_img = charts[-1]["image"] if charts else None
            ok = await broadcast_signal(signal_text, m5_img)
            if ok:
                logger.info(f"Signal broadcast to channel: {symbol} {decision_str}")
            else:
                logger.warning(f"Signal broadcast FAILED for {symbol}")
        except Exception as e:
            logger.warning(f"Signal broadcast error: {e}")

        logger.info(f"Trade signal with {len(charts)} charts sent for {symbol}")

        if not charts:
            try:
                from app.signal_bot import broadcast_signal
                ok = await broadcast_signal(signal_text)
                if ok:
                    logger.info(f"Signal broadcast (text-only) to channel: {symbol} {decision_str}")
            except Exception:
                pass

        return True
    except Exception as e:
        logger.error(f"Failed to send trade signal: {e}")
        return False


async def notify_trade_executed(trade_result: dict, ai_decision=None) -> bool:
    ticket = trade_result.get("ticket") or trade_result.get("order")
    symbol = trade_result.get("symbol", settings.default_symbol)
    volume = trade_result.get("volume", "?")
    price = trade_result.get("price", "?")

    lines = [
        "<b>\u2705 Trade Executed</b>",
        f"<b>Ticket:</b> <code>{ticket}</code>",
        f"<b>Symbol:</b> <code>{symbol}</code>",
        f"<b>Volume:</b> {volume}",
        f"<b>Price:</b> {price}",
    ]

    if ai_decision is not None:
        try:
            d = getattr(ai_decision, "decision", None)
            d_val = d.value if hasattr(d, "value") else str(d or "?")
            conf = getattr(ai_decision, "confidence", 0.0) or 0.0
            ep = getattr(ai_decision, "entry_plan", None)
            entry_type = getattr(ep, "entry_type", None) if ep else None
            et_val = entry_type.value if entry_type and hasattr(entry_type, "value") else str(entry_type or "")
            sl = getattr(ep, "stop_loss", None) if ep else None
            tp1 = getattr(ep, "take_profit_1", None) if ep else None
            rr = getattr(ep, "risk_reward_to_tp1", None) if ep else None
            reason = getattr(ai_decision, "main_reason", "")

            d_emoji = "\U0001f7e2" if d_val == "BUY" else "\U0001f534"
            lines.append("")
            lines.append(f"{d_emoji} <b>Setup: {d_val} {et_val}</b> | \u2705 {conf:.0%} prob")
            if sl:
                lines.append(f"SL: <code>{sl}</code>")
            if tp1:
                rr_str = f"  R:R {rr:.1f}" if rr else ""
                lines.append(f"TP1: <code>{tp1}</code>{rr_str}")
            if reason:
                lines.append(f"\U0001f4ac <i>{reason[:150]}</i>")
        except Exception:
            pass

    return await send_message("\n".join(lines))


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
