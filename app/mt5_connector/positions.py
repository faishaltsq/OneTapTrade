from datetime import datetime, time
from typing import List, Optional

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    _MT5_AVAILABLE = False

from app.config import settings
from app.logger import logger


def get_open_positions(symbol: Optional[str] = None) -> List[dict]:
    try:
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None or len(positions) == 0:
            return []
        return [p._asdict() for p in positions]
    except Exception as e:
        logger.error(f"get_open_positions exception: {e}")
        return []


def get_open_positions_count(symbol: Optional[str] = None) -> int:
    try:
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None:
            return 0
        return len(positions)
    except Exception as e:
        logger.error(f"get_open_positions_count exception: {e}")
        return 0


def has_open_position(symbol: Optional[str] = None) -> bool:
    sym = symbol or settings.default_symbol
    try:
        positions = mt5.positions_get(symbol=sym)
        if positions is None or len(positions) == 0:
            return False
        return True
    except Exception as e:
        logger.error(f"has_open_position exception for {sym}: {e}")
        return False


def get_today_realized_pnl(symbol: Optional[str] = None) -> float:
    try:
        start = datetime.combine(datetime.now().date(), time.min)
        end = datetime.now()
        deals = mt5.history_deals_get(start, end)
        if deals is None:
            return 0.0

        total = 0.0
        for deal in deals:
            deal_symbol = getattr(deal, "symbol", None)
            if symbol and deal_symbol != symbol:
                continue

            profit = getattr(deal, "profit", 0.0) or 0.0
            swap = getattr(deal, "swap", 0.0) or 0.0
            commission = getattr(deal, "commission", 0.0) or 0.0
            total += profit + swap + commission

        return round(total, 2)
    except Exception as e:
        logger.error(f"get_today_realized_pnl exception: {e}")
        return 0.0
