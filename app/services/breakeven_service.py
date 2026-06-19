from app.logger import logger

BREAKEVEN_TRIGGER_PROGRESS = 0.30
POSITION_TYPE_BUY = 0
POSITION_TYPE_SELL = 1


def calculate_breakeven_stop(position: dict, tick: dict) -> float | None:
    entry = position.get("price_open")
    current_sl = position.get("sl") or 0.0
    tp = position.get("tp") or 0.0
    position_type = position.get("type")

    if not entry or not tp:
        return None

    if position_type == POSITION_TYPE_BUY:
        if current_sl >= entry:
            return None
        if tp <= entry:
            return None
        threshold = entry + ((tp - entry) * BREAKEVEN_TRIGGER_PROGRESS)
        bid = tick.get("bid") if tick else None
        if bid is not None and bid >= threshold:
            return entry
        return None

    if position_type == POSITION_TYPE_SELL:
        if current_sl and current_sl <= entry:
            return None
        if tp >= entry:
            return None
        threshold = entry - ((entry - tp) * BREAKEVEN_TRIGGER_PROGRESS)
        ask = tick.get("ask") if tick else None
        if ask is not None and ask <= threshold:
            return entry
        return None

    return None


def manage_breakeven_stops(symbol: str | None = None) -> dict:
    summary = {"checked": 0, "modified": 0, "skipped": 0, "failed": 0}

    try:
        from app.mt5_connector.connection import is_mt5_connected
        from app.mt5_connector.execution import modify_position_sl_tp
        from app.mt5_connector.market_data import get_latest_tick
        from app.mt5_connector.positions import get_open_positions

        if not is_mt5_connected():
            summary["error"] = "MT5 not connected"
            return summary

        positions = get_open_positions(symbol)
        for position in positions:
            summary["checked"] += 1
            sym = position.get("symbol")
            tick = get_latest_tick(sym)
            if not tick:
                summary["skipped"] += 1
                logger.warning(f"Breakeven skipped: no tick for {sym}")
                continue

            new_sl = calculate_breakeven_stop(position, tick)
            if new_sl is None:
                summary["skipped"] += 1
                continue

            result = modify_position_sl_tp(position, sl=new_sl, tp=position.get("tp") or 0.0)
            if result.get("success"):
                summary["modified"] += 1
                logger.info(f"Breakeven SL moved: {sym} ticket={position.get('ticket')} sl={new_sl}")
            else:
                summary["failed"] += 1
                logger.error(f"Breakeven SL move failed: {sym} ticket={position.get('ticket')} {result.get('error', '')}")

        return summary
    except Exception as e:
        logger.error(f"manage_breakeven_stops exception: {e}")
        summary["error"] = str(e)
        return summary
