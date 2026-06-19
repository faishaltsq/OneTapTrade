from datetime import datetime, timedelta
from typing import Optional

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    _MT5_AVAILABLE = False

from app.logger import logger


def get_account_info() -> Optional[dict]:
    try:
        info = mt5.account_info()
        if info is None:
            logger.warning("Account info not available")
            return None
        return info._asdict()
    except Exception as e:
        logger.error(f"get_account_info exception: {e}")
        return None


def get_balance() -> Optional[float]:
    info = get_account_info()
    if info is None:
        return None
    return float(info.get("balance", 0.0))


def get_equity() -> Optional[float]:
    info = get_account_info()
    if info is None:
        return None
    return float(info.get("equity", 0.0))


def get_daily_pnl() -> Optional[float]:
    try:
        today = datetime.now()
        from_date = datetime(today.year, today.month, today.day)
        to_date = from_date + timedelta(days=1)

        deals = mt5.history_deals_get(from_date, to_date)
        if deals is None or len(deals) == 0:
            return 0.0

        pnl = sum(float(d.profit) for d in deals)
        return round(pnl, 2)
    except Exception as e:
        logger.error(f"get_daily_pnl exception: {e}")
        return None


def get_daily_drawdown_percent() -> Optional[float]:
    try:
        balance = get_balance()
        equity = get_equity()

        if balance is None or equity is None or balance <= 0:
            return None

        floating_pnl = equity - balance
        peak_equity = balance

        today = datetime.now()
        from_date = datetime(today.year, today.month, today.day)
        to_date = from_date + timedelta(days=1)

        deals = mt5.history_deals_get(from_date, to_date)
        if deals and len(deals) > 0:
            cumulative = balance
            running_peak = balance
            for d in sorted(deals, key=lambda x: x.time):
                cumulative += float(d.profit)
                if cumulative > running_peak:
                    running_peak = cumulative
            peak_equity = running_peak

        if floating_pnl > 0:
            peak_equity = max(peak_equity, equity)

        if peak_equity <= 0:
            return 0.0

        drawdown_pct = ((peak_equity - equity) / peak_equity) * 100.0
        return round(drawdown_pct, 2)
    except Exception as e:
        logger.error(f"get_daily_drawdown_percent exception: {e}")
        return None
