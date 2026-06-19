import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes

from app.config import settings
from app.logger import logger
from app.telegram_bot.bot import get_trading_loop, send_main_menu
from app.telegram_bot.message_templates import (
    build_settings_keyboard,
    format_positions_message,
    format_settings_message,
    format_status_message,
    format_welcome_message,
)
from app.mt5_connector.connection import is_mt5_connected
from app.mt5_connector.account import get_balance, get_equity, get_daily_pnl, get_daily_drawdown_percent
from app.mt5_connector.positions import get_open_positions, get_open_positions_count, get_today_realized_pnl


def _check_allowed(update: Update) -> bool:
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    allowed = settings.telegram_allowed_chat_id
    if not allowed:
        logger.warning("No allowed_chat_id configured — accepting all")
        return True
    if chat_id != allowed:
        logger.warning(f"BLOCKED: chat_id={chat_id} != allowed={allowed}")
        return False
    logger.debug(f"ALLOWED: chat_id={chat_id}")
    return True


def _active_symbol() -> str:
    trading_loop = get_trading_loop()
    if trading_loop is not None:
        try:
            return trading_loop.status.active_symbol
        except Exception:
            pass
    return settings.default_symbol


async def _reply(update: Update, text: str) -> None:
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return
    await send_main_menu()


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return
    await send_main_menu()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    await _reply(
        update,
        "<b>OneTapTrade Commands</b>\n\n"
        "<code>/menu</code> - tampilkan tombol kontrol\n"
        "<code>/status</code> - status bot dan akun\n"
        "<code>/positions</code> - posisi terbuka\n"
        "<code>/last_signal</code> - sinyal AI terakhir\n"
        "<code>/pause</code> - pause trading loop\n"
        "<code>/resume</code> - resume trading loop\n"
        "<code>/settings</code> - konfigurasi aktif\n"
        "<code>/mode_signal</code> - signal only\n"
        "<code>/mode_semi</code> - semi-auto approval\n"
        "<code>/mode_demo_auto</code> - auto demo execution",
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    mt5_ok = await asyncio.to_thread(is_mt5_connected)
    paused = False
    trading_loop = get_trading_loop()

    if trading_loop is not None:
        try:
            paused = trading_loop.is_paused()
        except Exception:
            pass

    status_data = {
        "mode": trading_loop.status.mode if trading_loop is not None else settings.bot_mode,
        "symbol": settings.default_symbol,
        "mt5_connected": mt5_ok,
        "paused": paused,
        "open_positions_count": 0,
        "equity": None,
        "balance": None,
        "daily_pnl": None,
        "daily_drawdown_percent": None,
    }

    active_symbol = settings.default_symbol
    if trading_loop is not None:
        try:
            active_symbol = trading_loop.status.active_symbol
        except Exception:
            pass
    status_data["symbol"] = active_symbol

    if mt5_ok:
        (
            status_data["equity"],
            status_data["balance"],
            status_data["daily_pnl"],
            status_data["daily_drawdown_percent"],
        ) = await asyncio.gather(
            asyncio.to_thread(get_equity),
            asyncio.to_thread(get_balance),
            asyncio.to_thread(get_daily_pnl),
            asyncio.to_thread(get_daily_drawdown_percent),
        )
        if active_symbol == "ALL":
            status_data["open_positions_count"] = await asyncio.to_thread(get_open_positions_count)
        else:
            status_data["open_positions_count"] = await asyncio.to_thread(get_open_positions_count, active_symbol)

    from app.database.repositories import get_latest_decision

    active = _active_symbol()
    latest = await asyncio.to_thread(get_latest_decision, active if active != "ALL" else None)
    if latest:
        status_data["last_signal_time"] = latest.get("created_at")

    await _reply(update, format_status_message(status_data))


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    trading_loop = get_trading_loop()
    if trading_loop is not None:
        try:
            await asyncio.to_thread(trading_loop.set_paused, True)
        except Exception as e:
            logger.error(f"Failed to pause trading loop: {e}")
            await _reply(update, "<b>\u274c Failed to pause trading loop</b>")
            return
    else:
        from app.database.repositories import set_paused

        await asyncio.to_thread(set_paused, True)
    from app.database.repositories import log_telegram_command

    await asyncio.to_thread(log_telegram_command, settings.telegram_allowed_chat_id, "/pause", result="paused")
    await _reply(update, "<b>\u23f8\ufe0f Trading loop paused.</b>")
    logger.info("Trading loop paused via Telegram command")


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    trading_loop = get_trading_loop()
    if trading_loop is not None:
        try:
            await asyncio.to_thread(trading_loop.set_paused, False)
        except Exception as e:
            logger.error(f"Failed to resume trading loop: {e}")
            await _reply(update, "<b>\u274c Failed to resume trading loop</b>")
            return
    else:
        from app.database.repositories import set_paused

        await asyncio.to_thread(set_paused, False)
    from app.database.repositories import log_telegram_command

    await asyncio.to_thread(log_telegram_command, settings.telegram_allowed_chat_id, "/resume", result="resumed")
    await _reply(update, "<b>\u25b6\ufe0f Trading loop resumed.</b>")
    logger.info("Trading loop resumed via Telegram command")


async def mode_signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    settings.bot_mode = "SIGNAL_ONLY"
    trading_loop = get_trading_loop()
    if trading_loop is not None:
        await asyncio.to_thread(trading_loop.set_mode, "SIGNAL_ONLY")
    from app.database.repositories import update_bot_mode, log_telegram_command

    if trading_loop is None:
        await asyncio.to_thread(update_bot_mode, "SIGNAL_ONLY")
    await asyncio.to_thread(log_telegram_command, settings.telegram_allowed_chat_id, "/mode_signal", result="SIGNAL_ONLY")
    await _reply(update, "<b>\U0001f4e2 Mode set to SIGNAL_ONLY.</b>\n<i>Bot will only send signals, no execution.</i>")


async def mode_semi_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    settings.bot_mode = "SEMI_AUTO"
    trading_loop = get_trading_loop()
    if trading_loop is not None:
        await asyncio.to_thread(trading_loop.set_mode, "SEMI_AUTO")
    from app.database.repositories import update_bot_mode, log_telegram_command

    if trading_loop is None:
        await asyncio.to_thread(update_bot_mode, "SEMI_AUTO")
    await asyncio.to_thread(log_telegram_command, settings.telegram_allowed_chat_id, "/mode_semi", result="SEMI_AUTO")
    await _reply(update, "<b>\U0001f50d Mode set to SEMI_AUTO.</b>\n<i>Signals require your approval before execution.</i>")


async def mode_demo_auto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    settings.bot_mode = "AUTO_DEMO"
    trading_loop = get_trading_loop()
    if trading_loop is not None:
        await asyncio.to_thread(trading_loop.set_mode, "AUTO_DEMO")
    from app.database.repositories import update_bot_mode, log_telegram_command

    if trading_loop is None:
        await asyncio.to_thread(update_bot_mode, "AUTO_DEMO")
    await asyncio.to_thread(log_telegram_command, settings.telegram_allowed_chat_id, "/mode_demo_auto", result="AUTO_DEMO")
    await _reply(update, "<b>\U0001f4f2 Mode set to AUTO_DEMO.</b>\n<i>Demo account — trades execute automatically.</i>")


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    if not await asyncio.to_thread(is_mt5_connected):
        await _reply(update, "<b>\u26a0\ufe0f MT5 not connected</b>")
        return

    symbol = _active_symbol()
    positions = await asyncio.to_thread(get_open_positions, None)
    realized_pnl = await asyncio.to_thread(get_today_realized_pnl, None)
    await _reply(update, format_positions_message(positions, symbol, realized_pnl=realized_pnl))


async def close_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    if not await asyncio.to_thread(is_mt5_connected):
        await _reply(update, "<b>\u26a0\ufe0f MT5 not connected</b>")
        return

    sym = _active_symbol()
    if sym == "ALL":
        sym = None
    positions = await asyncio.to_thread(get_open_positions, sym)
    if not positions:
        symbol_label = "all pairs" if sym is None else sym
        await _reply(update, f"<b>\u2139\ufe0f No open positions for {symbol_label}</b>")
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "\u26a0\ufe0f Confirm Close All",
                callback_data="CLOSE_ALL_CONFIRM",
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    count = len(positions)
    await _reply(
        update,
        f"<b>\u26a0\ufe0f Close all {count} position(s) for {settings.default_symbol}?</b>\n\n"
        "<i>Click the button below to confirm.</i>",
    )
    if update.message:
        await update.message.reply_text(
            f"<b>Confirm close {count} position(s)?</b>",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )


async def last_signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    from app.database.repositories import get_latest_decision

    sym = _active_symbol()
    latest = await asyncio.to_thread(get_latest_decision, sym if sym != "ALL" else None)
    if latest is None:
        await _reply(update, "<b>\u2139\ufe0f No AI decisions found in database.</b>")
        return

    decision_str = latest.get("decision", "N/A")
    confidence = latest.get("confidence", 0.0)
    symbol = latest.get("symbol", settings.default_symbol)
    created_at = latest.get("created_at", "")
    reason = latest.get("main_reason", "")

    d_emoji = "\U0001f7e2" if decision_str == "BUY" else ("\U0001f534" if decision_str == "SELL" else "\u26aa")

    text = (
        f"<b>\U0001f4e1 Latest Signal — {symbol}</b>\n\n"
        f"{d_emoji} <b>{decision_str}</b> | Confidence: {confidence:.0%}\n"
        f"<b>Time:</b> <i>{created_at}</i>"
    )
    if reason:
        text += f"\n<b>Reason:</b> <i>{reason}</i>"

    await _reply(update, text)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    if update.message:
        await update.message.reply_text(
            format_settings_message(),
            parse_mode="HTML",
            reply_markup=build_settings_keyboard(),
        )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _check_allowed(update):
        await _reply(update, "<b>\u26a0\ufe0f Unauthorized</b>")
        return

    await _reply(update, "<b>Command tidak dikenal.</b> Pakai <code>/help</code> atau <code>/menu</code>.")


def get_command_handlers() -> list:
    return [
        CommandHandler("start", start_command),
        CommandHandler("menu", menu_command),
        CommandHandler("help", help_command),
        CommandHandler("status", status_command),
        CommandHandler("pause", pause_command),
        CommandHandler("resume", resume_command),
        CommandHandler("mode_signal", mode_signal_command),
        CommandHandler("mode_semi", mode_semi_command),
        CommandHandler("mode_demo_auto", mode_demo_auto_command),
        CommandHandler("positions", positions_command),
        CommandHandler("close_all", close_all_command),
        CommandHandler("last_signal", last_signal_command),
        CommandHandler("settings", settings_command),
    ]
