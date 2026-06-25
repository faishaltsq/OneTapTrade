import uuid
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.config import settings
from app.logger import logger
from app.mt5_connector.positions import get_today_realized_pnl
from app.telegram_bot.bot import _pending_decisions, _decision_symbols, get_trading_loop, send_main_menu, send_message
from app.telegram_bot.message_templates import build_main_menu_keyboard, build_settings_keyboard, format_settings_message


def _parse_decision_id(data: str) -> str:
    parts = data.split(":", 1)
    return parts[1] if len(parts) > 1 else ""


async def _edit_message(update: Update, text: str, reply_markup=None) -> None:
    query = update.callback_query
    if query and query.message:
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e:
            if "Message is not modified" in str(e):
                return
            logger.error(f"Failed to edit callback message: {e}")
            try:
                await query.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
            except Exception:
                pass


def _current_main_menu_keyboard():
    paused = True
    mode = settings.bot_mode
    active = "ALL"
    trading_loop = get_trading_loop()
    if trading_loop is not None:
        try:
            paused = trading_loop.is_paused()
            mode = trading_loop.status.mode
            active = trading_loop.status.active_symbol
        except Exception:
            pass
    return build_main_menu_keyboard(is_paused=paused, mode=mode, active_symbol=active)


# ── Trade approval callbacks ──────────────────────────────────────────

async def approve_trade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        logger.warning(f"Unauthorized callback from chat_id: {chat_id}")
        return

    decision_id = _parse_decision_id(query.data)
    if not decision_id or decision_id not in _pending_decisions:
        await _edit_message(update, "<b>\u26a0\ufe0f Decision expired or not found.</b>")
        await query.answer("Decision not found", show_alert=True)
        return

    decision = _pending_decisions[decision_id]
    await query.answer("Evaluating trade...")

    decision_str = getattr(decision, "decision", "HOLD")
    if hasattr(decision_str, "value"):
        decision_str = decision_str.value

    try:
        from app.mt5_connector.market_data import get_latest_tick, get_spread, get_symbol_info
        from app.mt5_connector.account import get_balance, get_daily_drawdown_percent
        from app.mt5_connector.positions import get_open_positions_count
        from app.mt5_connector.orders import get_pending_orders_count

        symbol = _decision_symbols.get(decision_id, settings.default_symbol)
        tick = get_latest_tick(symbol)
        if tick is None:
            await _edit_message(update, "<b>\u274c Cannot fetch market data. MT5 may be disconnected.</b>")
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return

        current_bid = tick.get("bid", 0.0)
        current_ask = tick.get("ask", 0.0)
        spread_points = get_spread(symbol) or 0
        open_positions_count = get_open_positions_count(None)
        open_positions_count_symbol = get_open_positions_count(symbol)
        open_orders_count_symbol = open_positions_count_symbol + get_pending_orders_count(symbol)
        daily_drawdown_percent = get_daily_drawdown_percent() or 0.0

        sym_info = get_symbol_info(symbol)

        market_context = {
            "symbol": symbol,
            "current_bid": current_bid,
            "current_ask": current_ask,
            "spread_points": spread_points,
            "open_positions_count": open_positions_count,
            "open_positions_count_symbol": open_positions_count_symbol,
            "open_orders_count_symbol": open_orders_count_symbol,
            "has_open_position": open_positions_count_symbol > 0,
            "daily_drawdown_percent": daily_drawdown_percent,
            "mode": settings.bot_mode,
            "point": sym_info.get("point", 0.01) if sym_info else 0.01,
        }

        from app.risk.risk_manager import evaluate_decision

        risk_result = evaluate_decision(decision, market_context)

        from app.database.repositories import save_risk_check

        save_risk_check(
            ai_decision_id=decision_id,
            approved=risk_result.get("approved", False),
            reason=risk_result.get("reason", "Unknown"),
            checks=risk_result.get("checks", {}),
        )

        if not risk_result.get("approved"):
            reason = risk_result.get("reason", "Risk check failed")
            await _edit_message(update, f"<b>\u274c APPROVED but rejected by risk:</b>\n<i>{reason}</i>")
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return

        entry_plan = getattr(decision, "entry_plan", None)
        stop_loss = getattr(entry_plan, "stop_loss", None) if entry_plan else None
        tp1 = getattr(entry_plan, "take_profit_1", None) if entry_plan else None
        entry_type = getattr(entry_plan, "entry_type", None) if entry_plan else None
        entry_price = getattr(entry_plan, "preferred_entry_price", None) if entry_plan else None
        is_limit = False
        if entry_type and hasattr(entry_type, "value"):
            is_limit = entry_type.value in ("LIMIT", "STOP")

        from app.risk.position_sizing import calculate_lot_size

        balance = get_balance()
        if balance is None:
            await _edit_message(update, "<b>\u274c Cannot fetch account balance.</b>")
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return

        sym_info = get_symbol_info(symbol)
        if sym_info is None:
            await _edit_message(update, "<b>\u274c Cannot fetch symbol info.</b>")
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return

        sl_distance = abs(entry_price - stop_loss) if entry_price and stop_loss else 0.0
        sl_points = sl_distance / sym_info.get("point", 0.01) if sym_info.get("point", 0) else sl_distance * 100

        sizing = calculate_lot_size(balance, sl_points, sym_info)
        if not sizing.get("is_valid"):
            await _edit_message(update, f"<b>\u274c Position sizing failed:</b> <i>{sizing.get('reason', 'Unknown')}</i>")
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return

        lot = sizing["lot"]

        from app.mt5_connector.execution import build_order_request, check_order, send_order

        order_request = build_order_request(
            symbol=symbol,
            order_type=decision_str,
            lot=lot,
            sl=stop_loss,
            tp=tp1,
            comment="AI_Approved_Telegram",
            is_limit=is_limit,
            price=entry_price if is_limit else None,
        )

        if not order_request:
            await _edit_message(update, "<b>\u274c Failed to build order request.</b>")
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return

        check_result = check_order(order_request)
        if check_result is None:
            await _edit_message(update, "<b>\u274c Order check failed — returned None.</b>")
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return

        retcode_check = check_result.get("retcode", -1)
        if retcode_check != 0:
            comment = check_result.get("comment", "Unknown error")
            await _edit_message(update, f"<b>\u274c Order check failed (retcode={retcode_check}):</b> <i>{comment}</i>")
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return

        order_result = send_order(order_request)
        if order_result is None:
            await _edit_message(update, "<b>\u274c Order send failed. Check logs.</b>")
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return

        retcode = order_result.get("retcode", -1)
        if retcode != 10009:
            comment = order_result.get("comment", "Unknown error")
            await _edit_message(update, f"<b>\u274c Order failed (retcode={retcode}):</b> <i>{comment}</i>")
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return

        ticket = order_result.get("order")
        order_price = order_result.get("price") or entry_price

        from app.database.repositories import save_trade

        trade_id = str(uuid.uuid4())
        trade_data = {
            "id": trade_id,
            "ai_decision_id": decision_id,
            "symbol": symbol,
            "side": decision_str,
            "lot": lot,
            "entry_price": order_price,
            "stop_loss": stop_loss,
            "take_profit": tp1,
            "mt5_ticket": ticket,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
        save_trade(trade_data)

        from app.database.repositories import log_bot_event

        log_bot_event(
            event_type="trade_executed",
            message=f"User approved trade {decision_str} {symbol} ticket={ticket}",
            payload={"ticket": ticket, "decision_id": decision_id, "lot": lot},
        )

        await _edit_message(
            update,
            f"<b>\u2705 APPROVED — Executing...</b>\n\n"
            f"<b>Ticket:</b> <code>{ticket}</code>\n"
            f"<b>{decision_str}</b> {lot} lot {symbol} @ {order_price}\n"
            f"<b>SL:</b> {stop_loss} | <b>TP:</b> {tp1}",
        )

        _pending_decisions.pop(decision_id, None)
        logger.info(f"Trade executed via Telegram approval: {decision_str} {symbol} ticket={ticket}")

    except Exception as e:
        logger.exception(f"Error in approve_trade_callback: {e}")
        await _edit_message(update, f"<b>\u274c Error executing trade:</b> <i>{str(e)}</i>")
        _pending_decisions.pop(decision_id, None)


async def reject_trade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    decision_id = _parse_decision_id(query.data)
    if not decision_id:
        await query.answer("Invalid decision", show_alert=True)
        return

    await query.answer("Trade rejected")
    _pending_decisions.pop(decision_id, None)

    from app.database.repositories import log_bot_event

    log_bot_event(
        event_type="trade_rejected",
        message=f"User rejected trade decision {decision_id}",
        payload={"decision_id": decision_id},
    )

    logger.info(f"Trade rejected by user: decision_id={decision_id}")
    await _edit_message(update, "<b>\u274c REJECTED by user</b>\n\n<i>This trade will not be executed.</i>")


async def close_all_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    await query.answer("Closing all positions...")

    from app.mt5_connector.connection import is_mt5_connected
    from app.mt5_connector.execution import close_all_positions
    from app.mt5_connector.positions import get_open_positions

    if not is_mt5_connected():
        await _edit_message(update, "<b>\u274c MT5 not connected. Cannot close positions.</b>")
        return

    symbol = settings.default_symbol
    positions_before = get_open_positions(symbol)
    count_before = len(positions_before) if positions_before else 0

    success = close_all_positions(symbol)

    if success:
        from app.database.repositories import log_bot_event

        log_bot_event(
            event_type="close_all_positions",
            message=f"User closed all {count_before} positions for {symbol}",
            payload={"symbol": symbol, "count": count_before},
        )
        await _edit_message(update, f"<b>\u2705 Closed {count_before} position(s) for {symbol}</b>")
    else:
        await _edit_message(update, f"<b>\u26a0\ufe0f Some positions may not have closed for {symbol}. Check MT5.</b>")


# ── Menu callbacks ─────────────────────────────────────────────────────

async def menu_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    await query.answer()
    from app.mt5_connector.connection import is_mt5_connected
    from app.mt5_connector.account import get_balance, get_equity, get_daily_drawdown_percent
    from app.mt5_connector.positions import get_open_positions_count

    mt5_ok = is_mt5_connected()
    paused = False
    mode = settings.bot_mode
    trading_loop = get_trading_loop()
    if trading_loop is not None:
        try:
            paused = trading_loop.is_paused()
            mode = trading_loop.status.mode
        except Exception:
            pass

    lines = ["<b>\U0001f4ca Bot Status</b>\n"]
    lines.append(f"<b>Mode:</b> {mode} | {'\U0001f6d1 Stopped' if paused else '\u25b6\ufe0f Trading Running'}")
    lines.append(f"<b>Symbol:</b> {settings.default_symbol}")
    if mt5_ok:
        balance = get_balance()
        equity = get_equity()
        dd = get_daily_drawdown_percent()
        positions = get_open_positions_count(None)
        lines.append(f"<b>Balance:</b> ${balance:,.2f}" if balance else "<b>Balance:</b> N/A")
        lines.append(f"<b>Equity:</b> ${equity:,.2f}" if equity else "<b>Equity:</b> N/A")
        lines.append(f"<b>Daily DD:</b> {dd:.2f}%" if dd else "<b>Daily DD:</b> N/A")
        lines.append(f"<b>Open Positions:</b> {positions}")
    else:
        lines.append("\n\u26a0\ufe0f <b>MT5 not connected</b>")

    await _edit_message(update, "\n".join(lines), reply_markup=build_main_menu_keyboard(is_paused=paused, mode=mode))


async def menu_positions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    await query.answer()
    from app.mt5_connector.connection import is_mt5_connected
    from app.mt5_connector.positions import get_open_positions

    if not is_mt5_connected():
        await _edit_message(update, "<b>\u26a0\ufe0f MT5 not connected</b>", reply_markup=_current_main_menu_keyboard())
        return

    positions = get_open_positions(None)
    realized_pnl = get_today_realized_pnl(None)
    from app.telegram_bot.message_templates import format_positions_message

    text = format_positions_message(positions, "ALL", realized_pnl=realized_pnl)
    await _edit_message(update, text, reply_markup=_current_main_menu_keyboard())


async def menu_last_signal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    await query.answer()
    from app.database.repositories import get_latest_decision

    latest = get_latest_decision(settings.default_symbol)
    if latest is None:
        await _edit_message(update, "<b>\u2139\ufe0f No AI decisions found.</b>", reply_markup=_current_main_menu_keyboard())
        return

    decision_str = latest.get("decision", "N/A")
    confidence = latest.get("confidence", 0.0)
    created_at = latest.get("created_at", "")
    d_emoji = "\U0001f7e2" if decision_str == "BUY" else ("\U0001f534" if decision_str == "SELL" else "\u26aa")

    text = (
        f"<b>\U0001f4e1 Latest Signal</b>\n\n"
        f"{d_emoji} <b>{decision_str}</b> | {confidence:.0%}\n"
        f"<b>Time:</b> <i>{created_at}</i>"
    )
    await _edit_message(update, text, reply_markup=_current_main_menu_keyboard())


async def menu_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    await query.answer()
    await _edit_message(update, format_settings_message(), reply_markup=build_settings_keyboard())


async def menu_toggle_pause_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    trading_loop = get_trading_loop()
    if trading_loop is not None:
        try:
            current = trading_loop.is_paused()
            trading_loop.set_paused(not current)
            await query.answer("Stop Trade active" if not current else "Resume Trade active")
        except Exception:
            await query.answer("Failed", show_alert=True)
            return

    from app.database.repositories import set_paused as db_set_paused

    if trading_loop is not None:
        db_set_paused(trading_loop.is_paused())

    await send_main_menu()


async def _menu_set_mode(update: Update, mode: str) -> None:
    query = update.callback_query
    settings.bot_mode = mode
    trading_loop = get_trading_loop()
    if trading_loop is not None:
        try:
            trading_loop.set_mode(mode)
        except Exception:
            pass

    from app.database.repositories import update_bot_mode

    update_bot_mode(mode)
    labels = {"SIGNAL_ONLY": "Signal Only", "SEMI_AUTO": "Semi-Auto", "AUTO_DEMO": "Auto Demo"}
    await query.answer(f"Mode: {labels.get(mode, mode)}")
    await send_main_menu()


async def menu_mode_signal_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _menu_set_mode(update, "SIGNAL_ONLY")


async def menu_mode_semi_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _menu_set_mode(update, "SEMI_AUTO")


async def menu_mode_auto_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _menu_set_mode(update, "AUTO_DEMO")


async def menu_close_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    await query.answer()
    from app.mt5_connector.connection import is_mt5_connected
    from app.mt5_connector.positions import get_open_positions

    if not is_mt5_connected():
        await _edit_message(update, "<b>\u26a0\ufe0f MT5 not connected</b>", reply_markup=_current_main_menu_keyboard())
        return

    positions = get_open_positions(settings.default_symbol)
    if not positions:
        await _edit_message(update, f"<b>\u2139\ufe0f No open positions for {settings.default_symbol}</b>", reply_markup=_current_main_menu_keyboard())
        return

    keyboard = [[InlineKeyboardButton("\u26a0\ufe0f Confirm Close All", callback_data="CLOSE_ALL_CONFIRM")]]
    await _edit_message(
        update,
        f"<b>\u26a0\ufe0f Close all {len(positions)} position(s) for {settings.default_symbol}?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def menu_pending_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    await query.answer()
    from app.mt5_connector.connection import is_mt5_connected
    from app.mt5_connector.orders import get_pending_orders
    from app.telegram_bot.message_templates import format_pending_orders_message

    if not is_mt5_connected():
        await _edit_message(update, "<b>\u26a0\ufe0f MT5 not connected</b>", reply_markup=_current_main_menu_keyboard())
        return

    orders = get_pending_orders(None)
    text = format_pending_orders_message(orders)
    await _edit_message(update, text, reply_markup=_current_main_menu_keyboard())


async def menu_close_pending_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    await query.answer()
    from app.mt5_connector.connection import is_mt5_connected
    from app.mt5_connector.orders import get_pending_orders

    if not is_mt5_connected():
        await _edit_message(update, "<b>\u26a0\ufe0f MT5 not connected</b>", reply_markup=_current_main_menu_keyboard())
        return

    orders = get_pending_orders(None)
    if not orders:
        await _edit_message(update, "<b>\u2139\ufe0f No pending orders to close.</b>", reply_markup=_current_main_menu_keyboard())
        return

    keyboard = [[InlineKeyboardButton("\u26a0\ufe0f Confirm Close All Pending", callback_data="CLOSE_PENDING_CONFIRM")]]
    await _edit_message(
        update,
        f"<b>\u26a0\ufe0f Close all {len(orders)} pending order(s)?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def close_pending_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    await query.answer("Cancelling all pending orders...")
    from app.mt5_connector.connection import is_mt5_connected
    from app.mt5_connector.orders import cancel_all_pending_orders

    if not is_mt5_connected():
        await _edit_message(update, "<b>\u26a0\ufe0f MT5 not connected</b>", reply_markup=_current_main_menu_keyboard())
        return

    result = cancel_all_pending_orders(None)
    text = (
        f"<b>\u2705 Pending Orders Closed</b>\n\n"
        f"<b>Cancelled:</b> {result['cancelled']}\n"
        f"<b>Errors:</b> {result['errors']}\n"
        f"<b>Total:</b> {result['total']}"
    )
    await _edit_message(update, text, reply_markup=_current_main_menu_keyboard())


async def menu_risk_callback(update: Update, profile: str) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    settings.risk_profile = profile
    try:
        from app.database.repositories import update_bot_settings

        update_bot_settings({"risk_profile": profile})
    except Exception as e:
        logger.error(f"Failed to persist risk profile {profile}: {e}")
    labels = {"LOW": "Low Risk", "MEDIUM": "Medium Risk", "HIGH": "High Risk"}
    await query.answer(f"Profile: {labels.get(profile, profile)}")
    await _edit_message(update, format_settings_message(), reply_markup=build_settings_keyboard())


async def menu_risk_trade_callback(update: Update, percent: float) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    allowed = {0.25, 0.5, 1.0}
    if percent not in allowed:
        await query.answer("Invalid risk", show_alert=True)
        return

    settings.risk_per_trade_percent = percent
    try:
        from app.database.repositories import update_bot_settings

        update_bot_settings({"risk_per_trade_percent": percent})
    except Exception as e:
        logger.error(f"Failed to persist risk per trade {percent}: {e}")

    await query.answer(f"Risk/trade: {percent:g}%")
    await _edit_message(update, format_settings_message(), reply_markup=build_settings_keyboard())


async def menu_risk_trade_025_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await menu_risk_trade_callback(update, 0.25)


async def menu_risk_trade_050_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await menu_risk_trade_callback(update, 0.5)


async def menu_risk_trade_100_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await menu_risk_trade_callback(update, 1.0)


async def menu_chart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    from app.tv_connector import is_tv_available
    from app.telegram_bot.bot import capture_tv_screenshot, _application

    if not is_tv_available():
        await _edit_message(update, "\u26a0\ufe0f TradingView not connected.")
        await query.answer()
        return

    await _edit_message(update, "\U0001f4ca Capturing chart...")
    await query.answer()

    try:
        screenshot = await capture_tv_screenshot()
        if screenshot:
            from io import BytesIO

            img = BytesIO(screenshot)
            img.name = "chart.png"
            await _application.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=img,
                caption="\U0001f4ca TradingView Chart",
            )
        else:
            await _edit_message(update, "\u26a0\ufe0f Failed to capture chart.")
    except Exception as e:
        logger.warning(f"Send chart failed: {e}")
        await _edit_message(update, "\u26a0\ufe0f Error capturing chart.")


async def menu_analyze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    trading_loop = get_trading_loop()
    if trading_loop is None:
        await _edit_message(update, "\u26a0\ufe0f Trading loop not running.")
        await query.answer()
        return

    await _edit_message(update, "\U0001f50d Analyzing market across all pairs...")
    await query.answer()

    try:
        import asyncio
        from app.telegram_bot.bot import send_trade_signal

        symbols = settings.symbols
        for symbol in symbols:
            try:
                result = await trading_loop._run_symbol(symbol)
                ai_decision = result.get("ai_decision")
                risk_result = result.get("risk_result", {})
                decision_id = result.get("decision_id", str(uuid.uuid4()))

                if ai_decision is not None:
                    await send_trade_signal(ai_decision, risk_result, decision_id, result.get("market_payload"))
                else:
                    await send_message(f"\u26aa {symbol}: No signal generated.")
            except Exception as e:
                logger.error(f"Analyze failed for {symbol}: {e}")
                await send_message(f"\u26a0\ufe0f {symbol}: Analysis error — {e}")

        await send_main_menu()
    except Exception as e:
        logger.error(f"Analyze market failed: {e}")
        await _edit_message(update, f"\u26a0\ufe0f Analysis error: {e}")


async def menu_back_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    await send_main_menu()


async def menu_risk_low_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await menu_risk_callback(update, "LOW")


async def menu_risk_medium_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await menu_risk_callback(update, "MEDIUM")


async def menu_risk_high_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await menu_risk_callback(update, "HIGH")


async def _menu_set_strategy(update: Update, mode: str) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    settings.strategy_mode = mode
    try:
        from app.database.repositories import update_bot_settings

        update_bot_settings({"strategy_mode": mode})
    except Exception as e:
        logger.error(f"Failed to persist strategy mode {mode}: {e}")
    labels = {"SMC_AI": "SMC + AI", "AI_ONLY": "AI Only"}
    await query.answer(f"Strategy: {labels.get(mode, mode)}")
    await _edit_message(update, format_settings_message(), reply_markup=build_settings_keyboard())


async def menu_strategy_smc_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _menu_set_strategy(update, "SMC_AI")


async def menu_strategy_ai_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _menu_set_strategy(update, "AI_ONLY")


async def menu_symbol_all_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    trading_loop = get_trading_loop()
    if trading_loop is not None:
        trading_loop.status.set_symbol("ALL")
    await query.answer("Viewing: All pairs")
    await send_main_menu()


async def menu_symbol_next_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    new_sym = "ALL"
    trading_loop = get_trading_loop()
    if trading_loop is not None:
        new_sym = trading_loop.status.cycle_symbol()
    await query.answer(f"Viewing: {new_sym}")
    await send_main_menu()


# ── Handler registration ──────────────────────────────────────────────

def get_callback_handlers() -> list:
    return [
        CallbackQueryHandler(approve_trade_callback, pattern=r"^APPROVE_TRADE:"),
        CallbackQueryHandler(reject_trade_callback, pattern=r"^REJECT_TRADE:"),
        CallbackQueryHandler(close_all_confirm_callback, pattern=r"^CLOSE_ALL_CONFIRM$"),
        CallbackQueryHandler(menu_status_callback, pattern=r"^MENU_STATUS$"),
        CallbackQueryHandler(menu_positions_callback, pattern=r"^MENU_POSITIONS$"),
        CallbackQueryHandler(menu_last_signal_callback, pattern=r"^MENU_LAST_SIGNAL$"),
        CallbackQueryHandler(menu_settings_callback, pattern=r"^MENU_SETTINGS$"),
        CallbackQueryHandler(menu_toggle_pause_callback, pattern=r"^MENU_TOGGLE_PAUSE$"),
        CallbackQueryHandler(menu_mode_signal_cb, pattern=r"^MENU_MODE_SIGNAL$"),
        CallbackQueryHandler(menu_mode_semi_cb, pattern=r"^MENU_MODE_SEMI$"),
        CallbackQueryHandler(menu_mode_auto_cb, pattern=r"^MENU_MODE_AUTO$"),
        CallbackQueryHandler(menu_close_all_callback, pattern=r"^MENU_CLOSE_ALL$"),
        CallbackQueryHandler(menu_pending_callback, pattern=r"^MENU_PENDING$"),
        CallbackQueryHandler(menu_close_pending_callback, pattern=r"^MENU_CLOSE_PENDING$"),
        CallbackQueryHandler(close_pending_confirm_callback, pattern=r"^CLOSE_PENDING_CONFIRM$"),
        CallbackQueryHandler(menu_risk_low_cb, pattern=r"^MENU_RISK_LOW$"),
        CallbackQueryHandler(menu_risk_medium_cb, pattern=r"^MENU_RISK_MEDIUM$"),
        CallbackQueryHandler(menu_risk_high_cb, pattern=r"^MENU_RISK_HIGH$"),
        CallbackQueryHandler(menu_strategy_smc_cb, pattern=r"^MENU_STRATEGY_SMC$"),
        CallbackQueryHandler(menu_strategy_ai_cb, pattern=r"^MENU_STRATEGY_AI$"),
        CallbackQueryHandler(menu_risk_trade_025_cb, pattern=r"^MENU_RISK_TRADE_025$"),
        CallbackQueryHandler(menu_risk_trade_050_cb, pattern=r"^MENU_RISK_TRADE_050$"),
        CallbackQueryHandler(menu_risk_trade_100_cb, pattern=r"^MENU_RISK_TRADE_100$"),
        CallbackQueryHandler(menu_back_cb, pattern=r"^MENU_BACK$"),
        CallbackQueryHandler(menu_chart_callback, pattern=r"^MENU_CHART$"),
        CallbackQueryHandler(menu_analyze_callback, pattern=r"^MENU_ANALYZE$"),
        CallbackQueryHandler(menu_symbol_all_cb, pattern=r"^MENU_SYMBOL_ALL$"),
        CallbackQueryHandler(menu_symbol_next_cb, pattern=r"^MENU_SYMBOL_NEXT$"),
    ]
