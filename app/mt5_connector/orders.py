from typing import List, Optional

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    _MT5_AVAILABLE = False

from app.logger import logger


def _pending_order_side(order) -> str:
    try:
        order_type = int(order.get("type", 0))
        if mt5 is not None:
            if order_type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP):
                return "BUY"
            if order_type in (mt5.ORDER_TYPE_SELL_LIMIT, mt5.ORDER_TYPE_SELL_STOP):
                return "SELL"
    except Exception:
        pass
    return ""


def get_pending_orders(symbol: Optional[str] = None) -> List[dict]:
    try:
        if mt5 is None:
            return []
        orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
        if orders is None or len(orders) == 0:
            return []
        return [o._asdict() for o in orders]
    except Exception as e:
        logger.error(f"get_pending_orders exception: {e}")
        return []


def get_pending_orders_count(symbol: Optional[str] = None) -> int:
    try:
        if mt5 is None:
            return 0
        orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
        if orders is None:
            return 0
        return len(orders)
    except Exception as e:
        logger.error(f"get_pending_orders_count exception: {e}")
        return 0


def cancel_pending_order(ticket: int) -> bool:
    try:
        if mt5 is None:
            return False
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
        }
        result = mt5.order_send(request)
        if result is None:
            logger.error(f"cancel_pending_order returned None for ticket={ticket}")
            return False
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Pending order {ticket} cancelled")
            return True
        logger.error(f"cancel_pending_order failed: ticket={ticket}, retcode={result.retcode}, comment={result.comment}")
        return False
    except Exception as e:
        logger.error(f"cancel_pending_order exception: {e}")
        return False


def cancel_pending_orders_for_symbol(symbol: str, new_direction: str) -> dict:
    summary = {"symbol": symbol, "cancelled": 0, "errors": 0, "kept": 0}
    try:
        orders = get_pending_orders(symbol)
        new_dir = str(new_direction).upper()
        for order in orders:
            ticket = order.get("ticket")
            side = _pending_order_side(order)
            if side and side != new_dir:
                if cancel_pending_order(ticket):
                    summary["cancelled"] += 1
                else:
                    summary["errors"] += 1
            else:
                summary["kept"] += 1
        if summary["cancelled"] > 0:
            logger.info(f"Cancelled {summary['cancelled']} opposite pending orders for {symbol}")
    except Exception as e:
        logger.error(f"cancel_pending_orders_for_symbol exception: {e}")
        summary["errors"] += 1
    return summary
