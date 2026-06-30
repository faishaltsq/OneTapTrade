from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.logger import logger

router = APIRouter(prefix="")


@router.get("/status")
async def get_status(request: Request):
    loop = request.app.state.trading_loop
    if loop is None:
        raise HTTPException(status_code=503, detail="Trading loop not initialized")

    status = loop.get_status()
    status["market_data_source"] = settings.market_data_source.upper()
    status["execution_enabled"] = not settings.is_tradingview_mode
    if settings.is_tradingview_mode:
        status["execution"] = "disabled"
        status["mt5_required"] = False
    return status
