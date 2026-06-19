from typing import Optional

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    _MT5_AVAILABLE = False

from app.config import settings
from app.logger import logger

_ORDER_TYPE_MAP = None


def _get_order_type_map():
    global _ORDER_TYPE_MAP
    if _ORDER_TYPE_MAP is not None:
        return _ORDER_TYPE_MAP
    if mt5 is None:
        return {}
    _ORDER_TYPE_MAP = {
        "BUY": mt5.ORDER_TYPE_BUY,
        "SELL": mt5.ORDER_TYPE_SELL,
        "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
        "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
        "BUY_STOP": mt5.ORDER_TYPE_BUY_STOP,
        "SELL_STOP": mt5.ORDER_TYPE_SELL_STOP,
    }
    return _ORDER_TYPE_MAP


def build_order_request(
    symbol: str,
    order_type: str,
    lot: float,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    comment: str = "AI_Trade",
    is_limit: bool = False,
    price: Optional[float] = None,
) -> dict:
    if is_limit:
        if order_type == "BUY":
            action = mt5.TRADE_ACTION_PENDING
            type_ = mt5.ORDER_TYPE_BUY_LIMIT
        elif order_type == "SELL":
            action = mt5.TRADE_ACTION_PENDING
            type_ = mt5.ORDER_TYPE_SELL_LIMIT
        else:
            logger.error(f"Invalid order_type for limit: {order_type}")
            return {}
    else:
        if order_type == "BUY":
            action = mt5.TRADE_ACTION_DEAL
            type_ = mt5.ORDER_TYPE_BUY
        elif order_type == "SELL":
            action = mt5.TRADE_ACTION_DEAL
            type_ = mt5.ORDER_TYPE_SELL
        else:
            logger.error(f"Invalid order_type for market: {order_type}")
            return {}

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.error(f"Cannot get tick data for {symbol}")
        return {}

    request = {
        "action": action,
        "symbol": symbol,
        "volume": lot,
        "type": type_,
        "price": price or (tick.ask if order_type == "BUY" else tick.bid),
        "sl": sl or 0.0,
        "tp": tp or 0.0,
        "deviation": 100,
        "magic": 999,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
        }

    return request


def check_order(request: dict) -> Optional[dict]:
    try:
        result = mt5.order_check(request)
        if result is None:
            logger.error("order_check returned None")
            return None
        return result._asdict()
    except Exception as e:
        logger.error(f"check_order exception: {e}")
        return None


def send_order(request: dict) -> Optional[dict]:
    try:
        result = mt5.order_send(request)
        if result is None:
            logger.error("order_send returned None")
            return None
        retcode = result.retcode
        success_retcodes = {mt5.TRADE_RETCODE_DONE}
        placed_retcode = getattr(mt5, "TRADE_RETCODE_PLACED", None)
        if placed_retcode is not None:
            success_retcodes.add(placed_retcode)
        if retcode not in success_retcodes:
            logger.error(f"Order send failed. retcode={retcode}, comment={result.comment}")
        else:
            logger.info(f"Order executed/placed. ticket={result.order}")
        return result._asdict()
    except Exception as e:
        logger.error(f"send_order exception: {e}")
        return None


def modify_position_sl_tp(position: dict, sl: float, tp: float) -> dict:
    try:
        ticket = position.get("ticket")
        symbol = position.get("symbol")
        if not ticket or not symbol:
            return {"success": False, "error": "Missing ticket or symbol"}

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": symbol,
            "sl": sl,
            "tp": tp or 0.0,
            "magic": 999,
            "comment": "AI_Breakeven",
        }

        result = mt5.order_send(request)
        if result is None:
            return {"success": False, "error": "order_send returned None", "request": request}

        result_dict = result._asdict()
        success = result.retcode == mt5.TRADE_RETCODE_DONE
        if not success:
            logger.error(f"SLTP modification failed for {symbol} ticket={ticket}: retcode={result.retcode}, comment={result.comment}")
        return {"success": success, "request": request, "result": result_dict}
    except Exception as e:
        logger.error(f"modify_position_sl_tp exception: {e}")
        return {"success": False, "error": str(e)}


def close_all_positions(symbol: Optional[str] = None) -> bool:
    try:
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None or len(positions) == 0:
            label = symbol or "all pairs"
            logger.info(f"No open positions to close for {label}")
            return True

        success_all = True
        for pos in positions:
            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                logger.error(f"Cannot get tick for {pos.symbol}, skipping close")
                success_all = False
                continue

            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            close_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": close_price,
                "deviation": 100,
                "magic": 999,
                "comment": "AI_Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }

            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Failed to close position {pos.ticket} for {pos.symbol}")
                success_all = False
            else:
                logger.info(f"Closed position {pos.ticket} for {pos.symbol}")

        return success_all
    except Exception as e:
        logger.error(f"close_all_positions exception for {sym}: {e}")
        return False
