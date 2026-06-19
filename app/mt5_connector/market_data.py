from datetime import datetime
from typing import Optional

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    _MT5_AVAILABLE = False

import pandas as pd

from app.config import settings
from app.logger import logger

_TIMEFRAME_MAP = None


def _get_timeframe_map():
    global _TIMEFRAME_MAP
    if _TIMEFRAME_MAP is not None:
        return _TIMEFRAME_MAP
    if mt5 is None:
        return {}
    _TIMEFRAME_MAP = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1,
    }
    return _TIMEFRAME_MAP


def select_symbol(symbol: Optional[str] = None) -> bool:
    sym = symbol or settings.default_symbol
    logger.debug(f"Selecting symbol: {sym}")
    try:
        if not mt5.symbol_select(sym, True):
            logger.error(f"Failed to select symbol: {sym}")
            return False
        return True
    except Exception as e:
        logger.error(f"Symbol select exception for {sym}: {e}")
        return False


def get_symbol_info(symbol: Optional[str] = None) -> Optional[dict]:
    sym = symbol or settings.default_symbol
    try:
        info = mt5.symbol_info(sym)
        if info is None:
            logger.warning(f"Symbol info not available for {sym}")
            return None
        return info._asdict()
    except Exception as e:
        logger.error(f"get_symbol_info exception for {sym}: {e}")
        return None


def get_latest_tick(symbol: Optional[str] = None) -> Optional[dict]:
    sym = symbol or settings.default_symbol
    try:
        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            logger.warning(f"Tick data not available for {sym}")
            return None
        return tick._asdict()
    except Exception as e:
        logger.error(f"get_latest_tick exception for {sym}: {e}")
        return None


def get_candles(
    symbol: Optional[str] = None,
    timeframe: str = "M15",
    count: int = 500,
) -> pd.DataFrame:
    sym = symbol or settings.default_symbol
    tf_map = _get_timeframe_map()
    tf = tf_map.get(timeframe.upper(), tf_map.get("M15"))
    try:
        rates = mt5.copy_rates_from_pos(sym, tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.warning(f"No candle data for {sym} timeframe {timeframe}")
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        columns = ["time", "open", "high", "low", "close", "tick_volume", "spread"]
        return df[columns]
    except Exception as e:
        logger.error(f"get_candles exception for {sym} {timeframe}: {e}")
        return pd.DataFrame()


def get_market_depth(symbol: Optional[str] = None) -> Optional[dict]:
    sym = symbol or settings.default_symbol
    try:
        book = mt5.market_book_get(sym)
        if book is None:
            logger.debug(f"Market depth not available for {sym}")
            return None
        return book._asdict() if hasattr(book, "_asdict") else book
    except Exception as e:
        logger.error(f"get_market_depth exception for {sym}: {e}")
        return None


def get_spread(symbol: Optional[str] = None) -> Optional[float]:
    sym = symbol or settings.default_symbol
    try:
        info = mt5.symbol_info(sym)
        if info is not None and info.spread > 0:
            return float(info.spread)
        tick = mt5.symbol_info_tick(sym)
        if tick is not None:
            return float((tick.ask - tick.bid) / mt5.symbol_info(sym).point) if mt5.symbol_info(sym) else None
        logger.warning(f"Cannot determine spread for {sym}")
        return None
    except Exception as e:
        logger.error(f"get_spread exception for {sym}: {e}")
        return None
