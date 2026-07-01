from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="")


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "app": settings.app_name,
        "mode": "TRADINGVIEW_SIGNAL_ONLY",
        "telegram_enabled": settings.telegram_enabled,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
