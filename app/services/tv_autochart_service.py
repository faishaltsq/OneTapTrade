from typing import Optional

from app.logger import logger


async def draw_signal_on_chart(
    symbol: str,
    decision: str,
    entry_price: Optional[float],
    stop_loss: Optional[float],
    take_profit: Optional[float],
) -> bool:
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        return False

    try:
        await tools.set_symbol(symbol)
        await tools.draw_clear()
    except Exception as e:
        logger.debug(f"TV autochart: clear failed: {e}")

    if decision.upper() == "BUY":
        entry_color = "#00FF00"
        sl_color = "#FF4444"
        tp_color = "#4488FF"
    elif decision.upper() == "SELL":
        entry_color = "#FF0000"
        sl_color = "#FF4444"
        tp_color = "#4488FF"
    else:
        return False

    try:
        if entry_price is not None and entry_price > 0:
            await tools.draw_horizontal_line(entry_price, f"Entry {decision}", entry_color)
    except Exception as e:
        logger.debug(f"TV autochart: draw entry failed: {e}")

    try:
        if stop_loss is not None and stop_loss > 0:
            await tools.draw_horizontal_line(stop_loss, "SL", sl_color)
    except Exception as e:
        logger.debug(f"TV autochart: draw SL failed: {e}")

    try:
        if take_profit is not None and take_profit > 0:
            await tools.draw_horizontal_line(take_profit, "TP1", tp_color)
    except Exception as e:
        logger.debug(f"TV autochart: draw TP failed: {e}")

    logger.info(f"TV autochart: drew {decision} levels for {symbol}")
    return True


async def draw_breakeven_update(symbol: str, new_sl: float, side: str) -> bool:
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        return False

    try:
        await tools.draw_text(new_sl, "SL->BE", "#FFAA00")
        logger.info(f"TV autochart: breakeven annotation at {new_sl} on {symbol}")
        return True
    except Exception as e:
        logger.debug(f"TV autochart: breakeven draw failed: {e}")
        return False
