from typing import Optional

from telegram import Bot
from telegram.error import TelegramError

from app.config import settings
from app.logger import logger

_signal_bot: Optional[Bot] = None
_signal_ready: bool = False


def init_signal_bot() -> bool:
    global _signal_bot, _signal_ready

    if not settings.signal_bot_token:
        logger.info("Signal bot token not configured — signal broadcast disabled")
        return False

    if not settings.signal_channel_id:
        logger.info("Signal channel ID not configured — signal broadcast disabled")
        return False

    try:
        _signal_bot = Bot(token=settings.signal_bot_token)
        _signal_ready = True
        logger.info("Signal bot initialized — ready to broadcast")
        return True
    except Exception as e:
        logger.error(f"Signal bot init failed: {e}")
        _signal_ready = False
        return False


async def stop_signal_bot() -> None:
    global _signal_bot, _signal_ready
    _signal_ready = False
    if _signal_bot:
        try:
            await _signal_bot.close()
        except Exception:
            pass
        _signal_bot = None
    logger.info("Signal bot stopped")


async def broadcast_signal(
    text: str,
    image: Optional[bytes] = None,
    reply_markup=None,
) -> bool:
    global _signal_bot, _signal_ready

    if not _signal_ready or _signal_bot is None:
        return False

    chat_id = settings.signal_channel_id
    if not chat_id:
        return False

    try:
        if image:
            from io import BytesIO

            img = BytesIO(image)
            img.name = "signal.png"
            await _signal_bot.send_photo(
                chat_id=chat_id,
                photo=img,
                caption=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        else:
            await _signal_bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        return True
    except TelegramError as e:
        logger.warning(f"Signal broadcast failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Signal broadcast error: {e}")
        return False


def is_signal_ready() -> bool:
    return _signal_ready
