from fastapi import APIRouter, HTTPException, Request

from app.logger import logger
from app.mt5_connector.connection import is_mt5_connected

router = APIRouter(prefix="")


@router.get("/status")
async def get_status(request: Request):
    loop = request.app.state.trading_loop
    if loop is None:
        raise HTTPException(status_code=503, detail="Trading loop not initialized")

    if not is_mt5_connected():
        status = loop.get_status()
        status["warning"] = "MT5 not connected. Account and position data unavailable."
        return status

    return loop.get_status()
