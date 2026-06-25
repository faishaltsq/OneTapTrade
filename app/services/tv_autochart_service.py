from typing import Optional

from app.logger import logger


def _map_tv_symbol(mt5_symbol: str) -> str:
    import re
    symbol = re.sub(r"\.[A-Z0-9]+$", "", mt5_symbol.upper())
    TV_SYMBOL_MAP = {
        "US100": "NAS100",
        "US500": "PEPPERSTONE:US500",
    }
    return TV_SYMBOL_MAP.get(symbol, symbol)


async def draw_and_capture_multi_tf(
    mt5_symbol: str,
    decision: str,
    entry_price: Optional[float],
    stop_loss: Optional[float],
    take_profit: Optional[float],
    timeframes: list[str] = None,
) -> list[dict]:
    import asyncio
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        return []

    tv_symbol = _map_tv_symbol(mt5_symbol)

    if timeframes is None:
        timeframes = ["H1", "M5", "M15"]

    results = []

    for tf in timeframes:
        try:
            await tools.set_symbol(tv_symbol)
            await asyncio.sleep(0.5)
            await tools.set_timeframe(tf)
            await asyncio.sleep(1.5)
            await tools.draw_clear()
        except Exception:
            pass

        if decision.upper() in ("BUY", "SELL"):
            entry_color = "#00FF00" if decision.upper() == "BUY" else "#FF0000"
            sl_color = "#FF4444"
            tp_color = "#4488FF"

            try:
                if entry_price is not None and entry_price > 0:
                    await tools.draw_horizontal_line(entry_price, f"Entry {decision}", entry_color)
                if stop_loss is not None and stop_loss > 0:
                    await tools.draw_horizontal_line(stop_loss, "SL", sl_color)
                if take_profit is not None and take_profit > 0:
                    await tools.draw_horizontal_line(take_profit, "TP1", tp_color)
            except Exception as e:
                logger.debug(f"TV draw failed for {tv_symbol} {tf}: {e}")

        try:
            screenshot = await tools.capture_screenshot("chart")
            if screenshot:
                results.append({
                    "timeframe": tf,
                    "symbol": tv_symbol,
                    "image": screenshot,
                })
        except Exception as e:
            logger.debug(f"TV capture failed for {tv_symbol} {tf}: {e}")

    try:
        await tools.draw_clear()
    except Exception:
        pass

    logger.info(f"TV multi-TF: captured {len(results)}/{len(timeframes)} for {mt5_symbol}")
    return results


async def draw_breakeven_update(symbol: str, new_sl: float, side: str) -> bool:
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        return False

    try:
        await tools.draw_text_on_chart(new_sl, "SL->BE", "#FFAA00")
        logger.info(f"TV autochart: breakeven annotation at {new_sl} on {symbol}")
        return True
    except Exception as e:
        logger.debug(f"TV autochart: breakeven draw failed: {e}")
        return False
