from typing import Optional

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    _MT5_AVAILABLE = False

from app.config import settings
from app.logger import logger


def _mt5_path() -> Optional[str]:
    return settings.mt5_path if settings.mt5_path else None


def initialize_mt5() -> bool:
    if mt5 is None:
        logger.error("MetaTrader5 package not installed")
        return False
    logger.info("Initializing MT5 terminal...")
    try:
        path = _mt5_path()
        init_kwargs = {}
        if path:
            init_kwargs["path"] = path
        initialized = mt5.initialize(**init_kwargs)
        if not initialized:
            error = mt5.last_error()
            logger.error(f"MT5 initialize failed: {error}")
            return False
        logger.info("MT5 terminal initialized successfully")
        return True
    except Exception as e:
        logger.error(f"MT5 initialize exception: {e}")
        return False


def login_mt5() -> bool:
    logger.info("Logging into MT5 account...")
    try:
        login = settings.mt5_login
        password = settings.mt5_password
        server = settings.mt5_server

        if not login or not password:
            logger.error("MT5 login or password not configured")
            return False

        authorized = mt5.login(
            login=login,
            password=password,
            server=server or "",
        )
        if not authorized:
            error = mt5.last_error()
            logger.error(f"MT5 login failed: {error}")
            return False
        logger.info("MT5 login successful")

        try:
            info = mt5.terminal_info()
            if info is not None:
                trade_allowed = getattr(info, "trade_allowed", None)
                if trade_allowed is False:
                    logger.warning("=" * 60)
                    logger.warning("MT5 AutoTrading DISABLED. Bot cannot send orders.")
                    logger.warning("Click Algo Trading button (icon ▶) in MT5 toolbar until GREEN.")
                    logger.warning("=" * 60)
                else:
                    logger.info("MT5 AutoTrading: ENABLED")
        except Exception:
            pass

        return True
    except Exception as e:
        logger.error(f"MT5 login exception: {e}")
        return False


def shutdown_mt5() -> bool:
    logger.info("Shutting down MT5 connection...")
    try:
        mt5.shutdown()
        logger.info("MT5 shutdown complete")
        return True
    except Exception as e:
        logger.error(f"MT5 shutdown exception: {e}")
        return False


def is_mt5_connected() -> bool:
    if mt5 is None:
        return False
    try:
        info = mt5.terminal_info()
        if info is None:
            return False
        return info.connected
    except Exception:
        return False


def ensure_mt5_connected() -> bool:
    if is_mt5_connected():
        return True
    logger.warning("MT5 not connected, attempting reconnect...")
    if not initialize_mt5():
        return False
    if not login_mt5():
        return False
    logger.info("MT5 reconnected successfully")
    return True
