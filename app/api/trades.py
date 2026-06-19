from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.logger import logger
from app.database.repositories import get_open_trades, get_trade_by_mt5_ticket

router = APIRouter(prefix="")


@router.get("/trades")
async def get_trades(
    request: Request,
    symbol: Optional[str] = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
):
    try:
        trades = get_open_trades(symbol) if symbol else get_open_trades()
        if not trades:
            return {"trades": [], "count": 0}

        trades = trades[:limit]
        return {"trades": trades, "count": len(trades)}
    except Exception as e:
        logger.error(f"Failed to fetch trades: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch trades")


@router.get("/trades/{trade_id}")
async def get_trade(request: Request, trade_id: int):
    try:
        trade = get_trade_by_mt5_ticket(trade_id)
        if trade is None:
            raise HTTPException(status_code=404, detail=f"Trade ticket={trade_id} not found")
        return trade
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch trade {trade_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch trade")
