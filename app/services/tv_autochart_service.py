from typing import Optional

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


_TF_MAP = {
    "D1": "D", "D": "D",
    "H4": "240", "H1": "60", "H": "60",
    "M15": "15", "M5": "5", "M1": "1",
    "W1": "W", "W": "W",
}


def _map_tf(tf: str) -> str:
    return _TF_MAP.get(tf.upper(), tf)


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
        logger.debug("TV CDP not reachable — skipping capture")
        return []

    tv_symbol = _map_tv_symbol(mt5_symbol)
    if timeframes is None:
        timeframes = ["D1", "H1", "M5"]

    results = []

    for tf in timeframes:
        tv_tf = _map_tf(tf)
        try:
            await tools.set_symbol(tv_symbol)
            await asyncio.sleep(2.0)
            await tools.set_timeframe(tv_tf)
            await asyncio.sleep(3.0)
        except Exception:
            pass

        try:
            await tools._client.try_call_tool("ui_evaluate", {
                "expression": """
(function() {
    try {
        var chart = window.TradingViewApi._activeChartWidgetWV.value();
        if (chart && chart._chartWidget) {
            var pane = chart._chartWidget.panes()[0];
            if (pane) pane.setPriceScaleVisible(true, 'right');
        }
    } catch(e) {}
})()
"""
            }, timeout=3.0)
        except Exception:
            pass

        try:
            screenshot = await tools.capture_screenshot("full")
            if screenshot:
                results.append({
                    "timeframe": tf,
                    "symbol": tv_symbol,
                    "image": screenshot,
                })
        except Exception as e:
            logger.debug(f"TV capture failed for {tv_symbol} {tf}: {e}")

    logger.info(f"TV capture: {len(results)}/{len(timeframes)} for {mt5_symbol}")
    return results
