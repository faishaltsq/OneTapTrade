from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.logger import logger
from app.mt5_connector.connection import is_mt5_connected

router = APIRouter(prefix="")


@router.get("/health")
async def health_check(request: Request):
    loop = request.app.state.trading_loop
    bot_running = loop.is_running() if loop else False

    return {
        "status": "ok",
        "mt5_connected": is_mt5_connected(),
        "bot_running": bot_running,
        "mode": loop.mode if loop else "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
