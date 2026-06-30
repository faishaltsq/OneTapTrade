from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.config import settings
from app.logger import logger

router = APIRouter(prefix="")


@router.get("/health")
async def health_check(request: Request):
    loop = request.app.state.trading_loop
    bot_running = loop.is_running if loop else False
    mt5_connected = False
    if not settings.is_tradingview_mode:
        from app.mt5_connector.connection import is_mt5_connected

        mt5_connected = is_mt5_connected()

    return {
        "status": "ok",
        "market_data_source": settings.market_data_source.upper(),
        "execution_enabled": not settings.is_tradingview_mode,
        "mt5_connected": mt5_connected,
        "bot_running": bot_running,
        "mode": loop.status.mode if loop else "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
