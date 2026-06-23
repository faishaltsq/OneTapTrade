from typing import Optional

from app.config import settings
from app.logger import logger

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    _MT5_AVAILABLE = False

from app.mt5_connector.orders import get_pending_orders, cancel_pending_order
from app.mt5_connector.positions import get_open_positions
from app.mt5_connector.market_data import get_candles, get_latest_tick
from app.analysis.smc_detector import build_smc_section
from app.analysis.major_trend import build_major_trend_section


def _order_side(order: dict) -> str:
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


def _score_pending_order(order: dict, side: str, current_price: float, smc_section: dict, major_trend: dict) -> float:
    entry_price = float(order.get("price_open", 0) or 0)
    if entry_price == 0:
        return 0.0

    allowed = major_trend.get("allowed_directions") or []
    if allowed and side not in allowed:
        return 0.0

    order_blocks = smc_section.get("order_blocks", {}) if isinstance(smc_section, dict) else {}
    in_zone = False

    if side == "BUY":
        for ob in order_blocks.get("demand", []) or []:
            ob_low = float(ob.get("low", 0) or 0)
            ob_high = float(ob.get("high", 0) or 0)
            if ob_low <= entry_price <= ob_high:
                in_zone = True
                break
    elif side == "SELL":
        for ob in order_blocks.get("supply", []) or []:
            ob_low = float(ob.get("low", 0) or 0)
            ob_high = float(ob.get("high", 0) or 0)
            if ob_low <= entry_price <= ob_high:
                in_zone = True
                break

    if not in_zone:
        return 0.0

    score = 0.50

    distance_pct = abs(current_price - entry_price) / max(abs(current_price), 0.0001)
    if distance_pct <= 0.005:
        score += 0.20
    elif distance_pct <= 0.015:
        score += 0.10

    if major_trend.get("bias") == "D1_BULLISH" and side == "BUY":
        score += 0.10
    if major_trend.get("bias") == "D1_BEARISH" and side == "SELL":
        score += 0.10

    return round(min(score, 1.0), 2)


def _get_smc_and_trend(symbol: str) -> tuple:
    try:
        df_d1 = get_candles(symbol, timeframe="D1", count=50)
        df_h1 = get_candles(symbol, timeframe="H1", count=100)
        df_m5 = get_candles(symbol, timeframe="M5", count=100)
        tick = get_latest_tick(symbol)

        smc_section = build_smc_section(df_h1, df_m5)
        major_trend = build_major_trend_section(df_d1, None)

        current_price = 0.0
        if tick:
            current_price = (tick.get("bid", 0) + tick.get("ask", 0)) / 2.0

        return smc_section, major_trend, current_price
    except Exception as e:
        logger.debug(f"_get_smc_and_trend failed for {symbol}: {e}")
        return {}, {}, 0.0


def enforce_pending_order_cap(symbol: str, max_orders: int = 5) -> dict:
    summary = {"symbol": symbol, "cancelled": 0, "kept": 0, "errors": 0}

    try:
        orders = get_pending_orders(symbol)
    except Exception as e:
        logger.error(f"enforce_pending_order_cap: failed to get orders for {symbol}: {e}")
        summary["errors"] += 1
        return summary

    if len(orders) <= max_orders:
        summary["kept"] = len(orders)
        return summary

    smc_section, major_trend, current_price = _get_smc_and_trend(symbol)

    scored = []
    for order in orders:
        side = _order_side(order)
        score = _score_pending_order(order, side, current_price, smc_section, major_trend)
        entry_price = float(order.get("price_open", 0) or 0)
        distance = abs(current_price - entry_price) if current_price else 0.0
        scored.append((score, -distance, order))

    scored.sort(key=lambda x: (x[0], x[1]))

    to_cancel = len(orders) - max_orders
    for score, neg_dist, order in scored[:to_cancel]:
        ticket = order.get("ticket")
        try:
            if cancel_pending_order(ticket):
                summary["cancelled"] += 1
                logger.info(f"Cap enforcement: cancelled pending order {ticket} (score={score}) for {symbol}")
            else:
                summary["errors"] += 1
        except Exception as e:
            logger.error(f"Cap enforcement: failed to cancel {ticket}: {e}")
            summary["errors"] += 1

    summary["kept"] = len(orders) - summary["cancelled"]
    logger.info(f"Pending order cap enforcement for {symbol}: {summary}")
    return summary


def validate_pending_orders_on_startup() -> dict:
    summary = {"total": 0, "cancelled": 0, "kept": 0, "errors": 0}

    try:
        orders = get_pending_orders(None)
    except Exception as e:
        logger.error(f"validate_pending_orders_on_startup: failed to get orders: {e}")
        summary["errors"] += 1
        return summary

    summary["total"] = len(orders)
    if not orders:
        return summary

    symbols_seen = set()
    for order in orders:
        symbol = order.get("symbol")
        if symbol and symbol not in symbols_seen:
            symbols_seen.add(symbol)

    for symbol in symbols_seen:
        smc_section, major_trend, _ = _get_smc_and_trend(symbol)

        for order in orders:
            if order.get("symbol") != symbol:
                continue

            ticket = order.get("ticket")
            side = _order_side(order)
            entry_price = float(order.get("price_open", 0) or 0)

            allowed = major_trend.get("allowed_directions") or []
            if allowed and side not in allowed:
                logger.warning(f"Startup validation: cancelling pending order {ticket} - wrong D1 direction ({side} vs {allowed})")
                try:
                    if cancel_pending_order(ticket):
                        summary["cancelled"] += 1
                    else:
                        summary["errors"] += 1
                except Exception as e:
                    logger.error(f"Startup validation: cancel failed for {ticket}: {e}")
                    summary["errors"] += 1
                continue

            in_zone = False
            order_blocks = smc_section.get("order_blocks", {}) if isinstance(smc_section, dict) else {}
            if side == "BUY":
                for ob in order_blocks.get("demand", []) or []:
                    ob_low = float(ob.get("low", 0) or 0)
                    ob_high = float(ob.get("high", 0) or 0)
                    if ob_low <= entry_price <= ob_high:
                        in_zone = True
                        break
            elif side == "SELL":
                for ob in order_blocks.get("supply", []) or []:
                    ob_low = float(ob.get("low", 0) or 0)
                    ob_high = float(ob.get("high", 0) or 0)
                    if ob_low <= entry_price <= ob_high:
                        in_zone = True
                        break

            if not in_zone:
                logger.warning(f"Startup validation: cancelling pending order {ticket} - entry price {entry_price} outside valid OB zone")
                try:
                    if cancel_pending_order(ticket):
                        summary["cancelled"] += 1
                    else:
                        summary["errors"] += 1
                except Exception as e:
                    logger.error(f"Startup validation: cancel failed for {ticket}: {e}")
                    summary["errors"] += 1
                continue

            summary["kept"] += 1

    logger.info(f"Startup pending order validation: {summary}")
    return summary


def validate_open_positions_on_startup() -> dict:
    summary = {"total": 0, "valid": 0, "warnings": [], "errors": 0}

    try:
        positions = get_open_positions(None)
    except Exception as e:
        logger.error(f"validate_open_positions_on_startup: failed to get positions: {e}")
        summary["errors"] += 1
        return summary

    summary["total"] = len(positions)
    if not positions:
        return summary

    symbols_seen = set()
    for pos in positions:
        symbol = pos.get("symbol")
        if symbol and symbol not in symbols_seen:
            symbols_seen.add(symbol)

    for symbol in symbols_seen:
        _, major_trend, _ = _get_smc_and_trend(symbol)

        for pos in positions:
            if pos.get("symbol") != symbol:
                continue

            ticket = pos.get("ticket")
            pos_type = int(pos.get("type", 0))
            side = "BUY" if pos_type == 0 else "SELL"
            sl = float(pos.get("sl", 0) or 0)
            tp = float(pos.get("tp", 0) or 0)

            allowed = major_trend.get("allowed_directions") or []
            if allowed and side not in allowed:
                msg = f"Position {ticket} {side} {symbol} misaligned with D1 allowed {allowed}"
                logger.warning(f"Startup validation: {msg}")
                summary["warnings"].append(msg)
                continue

            if sl == 0 or tp == 0:
                msg = f"Position {ticket} {side} {symbol} has SL={sl} or TP={tp} - review needed"
                logger.warning(f"Startup validation: {msg}")
                summary["warnings"].append(msg)
                continue

            summary["valid"] += 1

    logger.info(f"Startup open position validation: {summary}")
    return summary
