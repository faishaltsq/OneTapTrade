from typing import Any, Optional

from app.logger import logger


async def sync_alerts_to_tv(symbol: str, entry_price: Optional[float],
                            stop_loss: Optional[float],
                            take_profit: Optional[float]) -> dict:
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        return {"synced": False, "reason": "TV not available"}

    created = []
    try:
        if entry_price is not None and entry_price > 0:
            alert_id = await tools.alert_create(
                condition="cross",
                message=f"{symbol} entry level at {entry_price}",
            )
            if alert_id:
                created.append({"level": "entry", "price": entry_price, "id": alert_id})

        if stop_loss is not None and stop_loss > 0:
            alert_id = await tools.alert_create(
                condition="crossing",
                message=f"{symbol} SL hit at {stop_loss}",
            )
            if alert_id:
                created.append({"level": "sl", "price": stop_loss, "id": alert_id})

        if take_profit is not None and take_profit > 0:
            alert_id = await tools.alert_create(
                condition="crossing",
                message=f"{symbol} TP hit at {take_profit}",
            )
            if alert_id:
                created.append({"level": "tp", "price": take_profit, "id": alert_id})

        logger.info(f"Alert bridge: synced {len(created)} alerts for {symbol}")
        return {"synced": True, "alerts": created}
    except Exception as e:
        logger.warning(f"Alert bridge sync failed: {e}")
        return {"synced": False, "reason": str(e)}


async def get_tv_alerts() -> list[dict]:
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        return []

    try:
        alerts = await tools.alert_list()
        return [a.model_dump() for a in alerts]
    except Exception as e:
        logger.debug(f"Alert bridge: get alerts failed: {e}")
        return []
