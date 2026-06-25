from typing import Any, Optional

from app.logger import logger


async def _quick_cdp_check() -> bool:
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:9222/json/version", timeout=2.0)
            return resp.status_code == 200
    except Exception:
        return False


def _map_tv_symbol(mt5_symbol: str) -> str:
    import re
    symbol = re.sub(r"\.[A-Z0-9]+$", "", mt5_symbol.upper())
    TV_SYMBOL_MAP = {
        "US100": "NAS100",
        "US500": "PEPPERSTONE:US500",
        "BRENT": "FOREXCOM:USOIL",
    }
    return TV_SYMBOL_MAP.get(symbol, symbol)


async def _setup_chart(tools, tv_symbol: str, tf: str) -> None:
    import asyncio
    await tools.set_symbol(tv_symbol)
    await asyncio.sleep(1.5)
    await tools.set_timeframe(tf)
    await asyncio.sleep(4.0)


async def _add_indicators(tools) -> None:
    try:
        await tools.manage_indicator("add", "Moving Average Exponential")
    except Exception:
        pass


async def _draw_smc_zones(tools, smc: dict, mid: float, decision: str) -> None:
    order_blocks = smc.get("order_blocks", {})
    demand = order_blocks.get("demand", []) or []
    supply = order_blocks.get("supply", []) or []

    for blk in demand[-3:]:
        if isinstance(blk, dict):
            low = blk.get("low", 0)
            high = blk.get("high", 0)
            if low and high and low < high and low < mid:
                try:
                    await tools.draw_horizontal_line(
                        high, f"D-{high}", "#1a7a1a"
                    )
                    await tools.draw_horizontal_line(
                        low, f"D-{low}", "#1a7a1a"
                    )
                except Exception:
                    pass

    for blk in supply[-3:]:
        if isinstance(blk, dict):
            low = blk.get("low", 0)
            high = blk.get("high", 0)
            if low and high and low < high and high > mid:
                try:
                    await tools.draw_horizontal_line(
                        high, f"S-{high}", "#b31a1a"
                    )
                    await tools.draw_horizontal_line(
                        low, f"S-{low}", "#b31a1a"
                    )
                except Exception:
                    pass

    fvgs = smc.get("fair_value_gaps", []) or []
    for fvg in fvgs[:3]:
        if isinstance(fvg, dict):
            fvg_high = fvg.get("high", 0)
            fvg_low = fvg.get("low", 0)
            if fvg_high and fvg_low:
                try:
                    await tools.draw_horizontal_line(
                        fvg_high, "FVG", "#4a90d9"
                    )
                    await tools.draw_horizontal_line(
                        fvg_low, "FVG", "#4a90d9"
                    )
                except Exception:
                    pass


async def _draw_entry_plan(tools, entry_price: float, stop_loss: float,
                           take_profit: float, decision: str) -> None:
    if decision.upper() == "BUY":
        entry_color = "#00cc00"
        sl_color = "#cc3333"
        tp_color = "#3377cc"
    else:
        entry_color = "#cc0000"
        sl_color = "#cc3333"
        tp_color = "#3377cc"

    try:
        if entry_price and entry_price > 0:
            await tools.draw_horizontal_line(entry_price, f"ENTRY", entry_color)
        if stop_loss and stop_loss > 0:
            await tools.draw_horizontal_line(stop_loss, f"SL", sl_color)
        if take_profit and take_profit > 0:
            await tools.draw_horizontal_line(take_profit, f"TP1", tp_color)
    except Exception as e:
        logger.debug(f"Draw entry plan failed: {e}")


async def draw_and_capture_multi_tf(
    mt5_symbol: str,
    decision: str,
    entry_price: Optional[float],
    stop_loss: Optional[float],
    take_profit: Optional[float],
    timeframes: list[str] = None,
    market_payload: dict = None,
) -> list[dict]:
    import asyncio
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        return []

    if not await _quick_cdp_check():
        logger.debug("TV CDP not reachable — skipping multi-TF capture")
        return []

    tv_symbol = _map_tv_symbol(mt5_symbol)
    if timeframes is None:
        timeframes = ["H1", "M5", "M15"]

    smc = (market_payload or {}).get("smc", {})
    current_price = (market_payload or {}).get("current_price", {})
    mid = current_price.get("mid", 0)

    results = []

    for tf in timeframes:
        try:
            await _setup_chart(tools, tv_symbol, tf)
        except Exception:
            pass

        try:
            await _add_indicators(tools)
        except Exception:
            pass

        try:
            await tools.draw_clear()
        except Exception:
            pass

        import asyncio
        await asyncio.sleep(0.5)

        try:
            await _draw_smc_zones(tools, smc, mid, decision)
        except Exception as e:
            logger.debug(f"Draw SMC zones failed for {tv_symbol} {tf}: {e}")

        if decision.upper() in ("BUY", "SELL"):
            try:
                await _draw_entry_plan(tools, entry_price, stop_loss, take_profit, decision)
            except Exception as e:
                logger.debug(f"Draw entry plan failed for {tv_symbol} {tf}: {e}")

        try:
            await asyncio.sleep(0.5)
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
        logger.info(f"TV breakeven at {new_sl} on {symbol}")
        return True
    except Exception:
        return False
