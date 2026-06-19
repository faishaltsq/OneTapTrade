from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.logger import logger
from app.database.repositories import get_bot_settings, update_bot_settings

router = APIRouter(prefix="")


class SettingsUpdateRequest(BaseModel):
    risk_per_trade_percent: Optional[float] = Field(default=None, ge=0.01, le=100.0)
    max_daily_drawdown_percent: Optional[float] = Field(default=None, ge=0.1, le=100.0)
    max_spread_points: Optional[int] = Field(default=None, ge=0, le=1000)
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    min_risk_reward: Optional[float] = Field(default=None, ge=0.1, le=20.0)
    max_open_positions: Optional[int] = Field(default=None, ge=0, le=50)
    symbol: Optional[str] = Field(default=None, min_length=1, max_length=20)


@router.get("/settings")
async def get_settings(request: Request):
    try:
        db_settings = get_bot_settings()
        return {"settings": db_settings}
    except Exception as e:
        logger.error(f"Failed to fetch settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch settings")


@router.post("/settings")
async def update_settings(request: Request, body: SettingsUpdateRequest):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        result = update_bot_settings(updates)
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to update settings in database")

        logger.info(f"Bot settings updated via API: {list(updates.keys())}")
        return {"status": "ok", "settings": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update settings")
