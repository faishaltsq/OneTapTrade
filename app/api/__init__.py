from app.api.health import router as health_router
from app.api.status import router as status_router
from app.api.controls import router as controls_router
from app.api.trades import router as trades_router
from app.api.settings import router as settings_router
from app.api.signals import router as signals_router

__all__ = [
    "health_router",
    "status_router",
    "controls_router",
    "trades_router",
    "settings_router",
    "signals_router",
]
