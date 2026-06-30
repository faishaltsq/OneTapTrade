from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.logger import logger

router = APIRouter(prefix="")


class ModeUpdateRequest(BaseModel):
    mode: Literal["SIGNAL_ONLY", "SEMI_AUTO", "AUTO_DEMO", "LIVE_AUTO"]


@router.post("/pause")
async def pause_trading(request: Request):
    loop = request.app.state.trading_loop
    if loop is None:
        raise HTTPException(status_code=503, detail="Trading loop not initialized")

    loop.set_paused(True)
    logger.info("Trading loop paused via API")
    return {"status": "ok", "message": "Trading loop paused"}


@router.post("/resume")
async def resume_trading(request: Request):
    loop = request.app.state.trading_loop
    if loop is None:
        raise HTTPException(status_code=503, detail="Trading loop not initialized")

    loop.set_paused(False)
    logger.info("Trading loop resumed via API")
    return {"status": "ok", "message": "Trading loop resumed"}


@router.post("/mode")
async def update_mode(request: Request, body: ModeUpdateRequest):
    loop = request.app.state.trading_loop
    if loop is None:
        raise HTTPException(status_code=503, detail="Trading loop not initialized")

    error = loop.set_mode(body.mode)
    if error:
        raise HTTPException(status_code=400, detail=error)

    logger.info(f"Trading mode changed to {body.mode} via API")
    return {"status": "ok", "message": f"Mode set to {body.mode}", "mode": loop.status.mode}


@router.post("/close-all")
async def close_all(request: Request):
    loop = request.app.state.trading_loop
    if loop is None:
        raise HTTPException(status_code=503, detail="Trading loop not initialized")

    if settings.is_tradingview_mode:
        raise HTTPException(status_code=400, detail="Execution disabled in TradingView signal-only mode")

    from app.mt5_connector.connection import is_mt5_connected

    if not is_mt5_connected():
        raise HTTPException(status_code=503, detail="MT5 not connected")

    success = loop.close_all()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to close positions")

    logger.info(f"All positions closed for {loop.symbol} via API")
    return {"status": "ok", "message": f"All positions closed for {loop.symbol}"}
