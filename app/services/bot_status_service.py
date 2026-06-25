import threading

from app.config import settings
from app.logger import logger

_VALID_MODES = {"SIGNAL_ONLY", "SEMI_AUTO", "AUTO_DEMO", "LIVE_AUTO"}


class BotStatusService:
    def __init__(self):
        self._lock = threading.Lock()
        self._is_paused = not settings.auto_signal_enabled
        self._mode = "SIGNAL_ONLY"
        self._active_symbol = "ALL"
        self._load_initial_status()

    def _load_initial_status(self):
        self._mode = settings.bot_mode
        try:
            from app.database.repositories import get_bot_settings

            db_settings = get_bot_settings()
            if db_settings:
                db_mode = db_settings.get("mode") or db_settings.get("bot_mode")
                if db_mode and db_mode in _VALID_MODES:
                    self._mode = db_mode
                    settings.bot_mode = db_mode

                db_profile = db_settings.get("risk_profile")
                if db_profile and db_profile in {"LOW", "MEDIUM", "HIGH"}:
                    settings.risk_profile = db_profile

                logger.info(
                    f"BotStatusService loaded from DB: mode={self._mode} profile={settings.risk_profile}"
                )
            else:
                logger.info(f"BotStatusService fresh start: mode={self._mode} profile={settings.risk_profile}")
        except Exception as e:
            logger.warning(f"Failed to load bot status from DB, using defaults: {e}")
        logger.info(f"State: paused={self._is_paused} | mode={self._mode} | symbol={self._active_symbol} | profile={settings.risk_profile}")

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._is_paused

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    @property
    def active_symbol(self) -> str:
        with self._lock:
            return self._active_symbol

    def set_symbol(self, symbol: str):
        with self._lock:
            self._active_symbol = symbol
        logger.info(f"Active symbol set to: {symbol}")

    def cycle_symbol(self) -> str:
        syms = settings.symbols
        with self._lock:
            if self._active_symbol == "ALL":
                self._active_symbol = syms[0] if syms else settings.default_symbol
            else:
                try:
                    idx = syms.index(self._active_symbol)
                    self._active_symbol = syms[(idx + 1) % len(syms)]
                except ValueError:
                    self._active_symbol = "ALL"
            return self._active_symbol

    def set_paused(self, paused: bool):
        with self._lock:
            self._is_paused = paused
        logger.info(f"Bot paused set to: {paused}")
        try:
            from app.database.repositories import set_paused as db_set_paused

            db_set_paused(paused)
        except Exception as e:
            logger.error(f"Failed to persist paused state to DB: {e}")

    def set_mode(self, mode: str):
        if mode not in _VALID_MODES:
            logger.error(f"Invalid bot mode '{mode}'. Valid modes: {_VALID_MODES}")
            raise ValueError(f"Invalid mode '{mode}'. Must be one of {_VALID_MODES}")

        with self._lock:
            self._mode = mode
        settings.bot_mode = mode
        logger.info(f"Bot mode set to: {mode}")

        try:
            from app.database.repositories import update_bot_mode

            update_bot_mode(mode)
        except Exception as e:
            logger.error(f"Failed to persist mode to DB: {e}")

    def get_status(self) -> dict:
        with self._lock:
            return {
                "mode": self._mode,
                "is_paused": self._is_paused,
                "symbol": self._active_symbol,
                "risk_per_trade_percent": settings.risk_per_trade_percent,
                "max_daily_drawdown_percent": settings.max_daily_drawdown_percent,
                "max_open_positions": settings.max_open_positions,
                "min_confidence": settings.min_confidence,
                "min_risk_reward": settings.min_risk_reward,
                "max_spread_points": settings.max_spread_points,
                "trading_loop_interval_seconds": settings.effective_loop_interval,
                "live_trading_enabled": settings.live_trading_enabled,
            }
