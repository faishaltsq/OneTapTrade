import uuid
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.logger import logger


def execute_trade(
    ai_decision,
    risk_result: dict,
    symbol_info: dict,
    account_balance: float,
    current_bid: float,
    current_ask: float,
    market_payload: dict | None = None,
) -> dict:
    sym = risk_result.get("symbol", settings.default_symbol)

    entry_plan = getattr(ai_decision, "entry_plan", None)
    stop_loss = getattr(entry_plan, "stop_loss", None) if entry_plan else None
    take_profit = getattr(entry_plan, "take_profit_1", None) if entry_plan else None
    entry_type = getattr(entry_plan, "entry_type", None) if entry_plan else None
    preferred_entry = getattr(entry_plan, "preferred_entry_price", None) if entry_plan else None

    is_limit = False
    if entry_type and hasattr(entry_type, "value"):
        is_limit = entry_type.value in ("LIMIT", "STOP")

    decision_str = getattr(ai_decision, "decision", "HOLD")
    if hasattr(decision_str, "value"):
        decision_str = decision_str.value

    if decision_str == "HOLD":
        return {"success": False, "error": "Cannot execute HOLD decision"}

    is_buy = decision_str == "BUY"
    digits = int(symbol_info.get("digits", 5)) if symbol_info else 5

    def _normalize_price(value):
        return round(float(value), digits) if value is not None else None

    market_entry_price = current_ask if is_buy else current_bid
    entry_price = preferred_entry if is_limit and preferred_entry else market_entry_price
    entry_price = _normalize_price(entry_price)
    stop_loss = _normalize_price(stop_loss)
    take_profit = _normalize_price(take_profit)
    if not stop_loss or not entry_price:
        return {"success": False, "error": "Missing stop loss or entry price"}

    sl_distance = abs(entry_price - stop_loss)
    point = symbol_info.get("point", 0.01) if symbol_info else 0.01
    sl_points = sl_distance / point if point > 0 else sl_distance * 100

    logger.info(
        f"Step 1: Calculating lot size — balance={account_balance}, SL_dist={sl_points:.1f}pts"
    )

    try:
        from app.risk.position_sizing import calculate_lot_size

        sizing = calculate_lot_size(account_balance, sl_points, symbol_info)
    except Exception as e:
        logger.error(f"Lot size calculation failed: {e}")
        return {"success": False, "error": f"Lot size calculation failed: {e}"}

    if not sizing.get("is_valid"):
        reason = sizing.get("reason", "Unknown")
        logger.warning(f"Step 2: Lot size invalid — {reason}")
        return {"success": False, "error": f"Position sizing failed: {reason}"}

    lot = sizing["lot"]
    logger.info(f"Step 2: Lot size calculated — {lot}")

    trade_stops_level = symbol_info.get("trade_stops_level", 0) if symbol_info else 0
    point = symbol_info.get("point", 0.01) if symbol_info else 0.01

    MIN_STOP_POINTS = 100
    effective_stop_points = max(trade_stops_level, MIN_STOP_POINTS)
    min_stop_distance = effective_stop_points * point
    if stop_loss and entry_price:
        current_price = current_ask if is_buy else current_bid
        ref_price = entry_price if entry_price else current_price

        if is_buy:
            sl_min = ref_price - min_stop_distance
            if stop_loss > sl_min:
                original_sl = stop_loss
                stop_loss = _normalize_price(sl_min)
                logger.warning(f"BUY SL {original_sl} too close to {ref_price}, adjusted to {stop_loss} (min {effective_stop_points} pts)")
            tp_min = ref_price + min_stop_distance
            if take_profit and take_profit < tp_min:
                original_tp = take_profit
                take_profit = _normalize_price(tp_min)
                logger.warning(f"BUY TP {original_tp} too close to {ref_price}, adjusted to {take_profit}")
        else:
            sl_max = ref_price + min_stop_distance
            if stop_loss < sl_max:
                original_sl = stop_loss
                stop_loss = _normalize_price(sl_max)
                logger.warning(f"SELL SL {original_sl} too close to {ref_price}, adjusted to {stop_loss} (min {effective_stop_points} pts)")
            tp_max = ref_price - min_stop_distance
            if take_profit and take_profit > tp_max:
                original_tp = take_profit
                take_profit = _normalize_price(tp_max)
                logger.warning(f"SELL TP {original_tp} too close to {ref_price}, adjusted to {take_profit}")

    # SMC SL Protection: push SL behind nearest SMC level + spread buffer
    if stop_loss and entry_price and market_payload:
        try:
            smc = market_payload.get("smc", {})
            spread_points = int(abs(current_ask - current_bid) / point) if point > 0 else 0
            spread_buffer = spread_points * point * 0.5
            adjusted_sl = _protect_sl_with_smc(
                stop_loss, entry_price, is_buy, smc, point, spread_buffer
            )
            if adjusted_sl is not None and adjusted_sl != stop_loss:
                logger.info(f"SMC SL protection: {stop_loss} -> {adjusted_sl}")
                stop_loss = _normalize_price(adjusted_sl)
        except Exception as e:
            logger.debug(f"SMC SL protection skipped: {e}")

    logger.info("Step 3-5: Building and checking order...")
    try:
        from app.mt5_connector.execution import build_order_request, check_order, send_order
        from app.mt5_connector.market_data import get_latest_tick
    except Exception as e:
        logger.error(f"Failed to import execution module: {e}")
        return {"success": False, "error": f"Import failed: {e}"}

    import MetaTrader5 as mt5

    order_request = None
    check_result = None
    max_retries = 5
    widen_factor = 1.5

    for attempt in range(max_retries):
        if attempt > 0:
            tick = get_latest_tick(sym)
            if tick:
                current_bid = tick.get("bid", current_bid)
                current_ask = tick.get("ask", current_ask)
            market_entry_price = current_ask if is_buy else current_bid
            entry_price = preferred_entry if is_limit and preferred_entry else market_entry_price
            entry_price = _normalize_price(entry_price)

        order_request = build_order_request(
            symbol=sym,
            order_type=decision_str,
            lot=lot,
            sl=stop_loss,
            tp=take_profit,
            comment="AI_Trade",
            is_limit=is_limit,
            price=entry_price,
        )

        if not order_request:
            return {"success": False, "error": "Empty order request returned"}

        logger.info(f"Step 6: Checking order (attempt {attempt + 1}/{max_retries})...")
        logger.info(f"  entry={entry_price}, SL={stop_loss}, TP={take_profit}, bid={current_bid}, ask={current_ask}")
        check_result = check_order(order_request)
        if check_result is None:
            logger.error("Order check failed — returned None")
            return {"success": False, "error": "Order check failed — returned None"}

        retcode_check = check_result.get("retcode", -1)
        comment_check = check_result.get("comment", "")

        if retcode_check == 0:
            logger.info(f"Order check passed on attempt {attempt + 1}")
            break

        logger.warning(f"Order check attempt {attempt + 1}: retcode={retcode_check}, comment={comment_check}")

        if attempt >= max_retries - 1:
            logger.error(f"Order check exhausted after {max_retries} attempts")
            return {
                "success": False,
                "error": f"Order check failed after {max_retries} attempts (retcode={retcode_check}): {comment_check}",
                "check_result": check_result,
            }

        if retcode_check == 10016 and stop_loss:
            ref_price = entry_price if entry_price else (current_ask if is_buy else current_bid)
            current_sl_dist = abs(stop_loss - ref_price)
            new_sl_dist = max(current_sl_dist * widen_factor, current_sl_dist + (effective_stop_points * point * 2))
            logger.warning(f"Invalid stops, widening SL/TP: distance {current_sl_dist:.6f} → {new_sl_dist:.6f}")

            if is_buy:
                stop_loss = _normalize_price(ref_price - new_sl_dist)
                if take_profit:
                    current_tp_dist = abs(take_profit - ref_price)
                    take_profit = _normalize_price(ref_price + max(current_tp_dist * widen_factor, new_sl_dist))
            else:
                stop_loss = _normalize_price(ref_price + new_sl_dist)
                if take_profit:
                    current_tp_dist = abs(take_profit - ref_price)
                    take_profit = _normalize_price(ref_price - max(current_tp_dist * widen_factor, new_sl_dist))

        elif retcode_check == 10015:
            logger.warning("Invalid price, will retry with refreshed tick data...")

        elif retcode_check == 10027:
            logger.error("AutoTrading disabled by client — cannot retry")
            return {
                "success": False,
                "error": "AutoTrading disabled in MT5. Enable Algo Trading button in MT5 toolbar.",
                "check_result": check_result,
            }

        else:
            logger.error(f"Order check failed with non-retryable retcode={retcode_check}: {comment_check}")
            return {
                "success": False,
                "error": f"Order check failed (retcode={retcode_check}): {comment_check}",
                "check_result": check_result,
            }

    # If we exhausted retries without success
    if check_result and check_result.get("retcode", -1) != 0:
        comment = check_result.get("comment", "Unknown error")
        return {
            "success": False,
            "error": f"Order check failed after {max_retries} attempts: {comment}",
            "check_result": check_result,
        }

    logger.info("Step 7: Sending order...")
    order_result = send_order(order_request)
    if order_result is None:
        logger.error("Order send failed — returned None")
        return {"success": False, "error": "Order send failed — returned None"}

    retcode_send = order_result.get("retcode", -1)
    import MetaTrader5 as mt5

    if retcode_send != mt5.TRADE_RETCODE_DONE:
        comment = order_result.get("comment", "Unknown error")
        logger.error(f"Order send failed: retcode={retcode_send}, comment={comment}")
        return {
            "success": False,
            "error": f"Order send failed (retcode={retcode_send}): {comment}",
            "order_result": order_result,
        }

    ticket = order_result.get("order")
    order_price = order_result.get("price", entry_price)
    logger.info(f"Trade executed: ticket={ticket}, price={order_price}, lot={lot}")

    logger.info("Step 9: Saving trade to DB...")
    trade_row = None
    try:
        from app.database.repositories import save_trade

        trade_id = str(uuid.uuid4())
        trade_data = {
            "id": trade_id,
            "symbol": sym,
            "mt5_ticket": ticket,
            "side": decision_str,
            "lot": lot,
            "entry_price": order_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
        trade_row = save_trade(trade_data)
        if trade_row:
            logger.info(f"Trade saved to DB: {trade_id}")
        else:
            logger.warning("Trade save returned None (DB unavailable)")
    except Exception as e:
        logger.error(f"Failed to save trade: {e}")

    trade_id_final = trade_row.get("id") if trade_row else str(uuid.uuid4())

    logger.info("Step 10: Logging bot event...")
    try:
        from app.database.repositories import log_bot_event

        log_bot_event(
            event_type="trade_executed",
            message=f"Trade executed: {decision_str} {sym} ticket={ticket} lot={lot} price={order_price}",
            payload={
                "ticket": ticket,
                "symbol": sym,
                "decision": decision_str,
                "lot": lot,
                "entry_price": order_price,
                "trade_id": trade_id_final,
            },
        )
    except Exception as e:
        logger.error(f"Failed to log bot event: {e}")

    return {
        "success": True,
        "symbol": sym,
        "ticket": ticket,
        "trade_id": trade_id_final,
        "lot": lot,
        "volume": lot,
        "entry_price": order_price,
        "price": order_price,
        "details": (
            f"{decision_str} {lot} lot {sym} @ {order_price} | "
            f"SL: {stop_loss} | TP: {take_profit}"
        ),
    }


def close_all_trades(symbol: Optional[str] = None) -> dict:
    sym = symbol or settings.default_symbol
    logger.info(f"Closing all trades for {sym}...")

    try:
        from app.mt5_connector.connection import is_mt5_connected
        from app.mt5_connector.execution import close_all_positions as mt5_close_all
        from app.mt5_connector.market_data import get_latest_tick

        if not is_mt5_connected():
            return {"success": False, "closed_count": 0, "details": "MT5 not connected"}

        from app.database.repositories import get_open_trades, update_trade_status

        open_trades = get_open_trades(sym)
        logger.info(f"Found {len(open_trades)} open trades in DB for {sym}")

        success = mt5_close_all(sym)

        tick = get_latest_tick(sym)
        close_price = None
        if tick:
            bid = tick.get("bid")
            ask = tick.get("ask")
            if bid and ask:
                close_price = round((bid + ask) / 2.0, 5)

        closed_count = 0
        for trade in open_trades:
            trade_id = trade.get("id")
            if not trade_id:
                continue
            try:
                update_trade_status(
                    trade_id=trade_id,
                    status="CLOSED",
                    close_price=close_price,
                )
                closed_count += 1
            except Exception as e:
                logger.error(f"Failed to update trade status for {trade_id}: {e}")

        logger.info(
            f"close_all_trades complete: mt5_success={success}, db_updated={closed_count}"
        )

        return {
            "success": success,
            "closed_count": max(closed_count, len(open_trades)),
            "details": f"Closed positions for {sym}. MT5 success: {success}, DB updates: {closed_count}",
        }

    except Exception as e:
        logger.exception(f"Error in close_all_trades: {e}")
        return {"success": False, "closed_count": 0, "details": str(e)}


def _protect_sl_with_smc(
    stop_loss: float,
    entry_price: float,
    is_buy: bool,
    smc: dict,
    point: float,
    spread_buffer: float,
) -> float | None:
    try:
        order_blocks = smc.get("order_blocks", {})
        h1_swings = smc.get("h1_swings", {})
        m5_swings = smc.get("m5_swings", {})
        liquidity = smc.get("liquidity_levels", [])

        buffer = spread_buffer + (point * 10)

        if is_buy:
            # For BUY: SL should be BELOW entry. Protect by pushing below demand blocks.
            # Find nearest demand block or swing low below entry
            protective_levels = []

            for ob in order_blocks.get("demand", []):
                ob_low = ob.get("low", 0)
                if ob_low < entry_price:
                    protective_levels.append(("demand_ob", ob_low))

            for swing in h1_swings.get("lows", []):
                sw_price = swing.get("price", 0)
                if sw_price < entry_price:
                    protective_levels.append(("h1_swing_low", sw_price))

            for swing in m5_swings.get("lows", []):
                sw_price = swing.get("price", 0)
                if sw_price < entry_price:
                    protective_levels.append(("m5_swing_low", sw_price))

            # Find level closest to entry but still below it
            # SL must be at least buffer below this level
            if protective_levels:
                protective_levels.sort(key=lambda x: x[1], reverse=True)
                nearest_name, nearest_price = protective_levels[0]
                protected_sl = nearest_price - buffer
                if stop_loss > protected_sl:
                    logger.info(f"SMC: BUY SL {stop_loss} exposed, protected below {nearest_name} at {nearest_price} -> {protected_sl}")
                    return round(protected_sl, 5)
        else:
            # For SELL: SL should be ABOVE entry. Protect by pushing above supply blocks.
            protective_levels = []

            for ob in order_blocks.get("supply", []):
                ob_high = ob.get("high", 0)
                if ob_high > entry_price:
                    protective_levels.append(("supply_ob", ob_high))

            for swing in h1_swings.get("highs", []):
                sw_price = swing.get("price", 0)
                if sw_price > entry_price:
                    protective_levels.append(("h1_swing_high", sw_price))

            for swing in m5_swings.get("highs", []):
                sw_price = swing.get("price", 0)
                if sw_price > entry_price:
                    protective_levels.append(("m5_swing_high", sw_price))

            if protective_levels:
                protective_levels.sort(key=lambda x: x[1])
                nearest_name, nearest_price = protective_levels[0]
                protected_sl = nearest_price + buffer
                if stop_loss < protected_sl:
                    logger.info(f"SMC: SELL SL {stop_loss} exposed, protected above {nearest_name} at {nearest_price} -> {protected_sl}")
                    return round(protected_sl, 5)

        return stop_loss
    except Exception as e:
        logger.debug(f"_protect_sl_with_smc error: {e}")
        return None
