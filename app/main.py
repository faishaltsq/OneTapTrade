import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.analysis import router as analysis_router
from app.api.health import router as health_router
from app.api.tradingview import router as tradingview_router
from app.config import settings
from app.logger import logger

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="TradingView signal webhook receiver with optional Telegram forwarding",
)

app.state.latest_tradingview_signal = None
app.state.telegram_stop_event = None
app.state.telegram_polling_task = None
app.state.auto_signal_stop_event = None
app.state.auto_signal_task = None
app.state.auto_signal_last_sent = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, tags=["Health"])
app.include_router(tradingview_router, tags=["TradingView"])
app.include_router(analysis_router, tags=["Analysis"])


@app.on_event("startup")
async def startup():
    logger.info(f"{settings.app_name} started in {settings.app_env} mode")
    logger.info(f"Default symbol: {settings.default_symbol}")
    logger.info(f"Telegram forwarding: {'enabled' if settings.telegram_enabled else 'disabled'}")
    logger.info(f"TradingView MCP dir: {settings.tradingview_mcp_dir}")
    if settings.auto_launch_tradingview_on_startup:
        try:
            from app.tradingview_mcp import ensure_tradingview_ready

            result = await ensure_tradingview_ready()
            if result.get("success"):
                status = result.get("status") or {}
                logger.info(
                    "TradingView ready: "
                    f"symbol={status.get('chart_symbol')} "
                    f"timeframe={status.get('chart_resolution')} "
                    f"launched={result.get('launched')}"
                )
            else:
                logger.warning(f"TradingView auto-launch failed: {result}")
        except Exception as e:
            logger.warning(f"TradingView auto-launch error: {e}")

    if settings.telegram_enabled and settings.telegram_command_polling_enabled:
        from app.telegram_bot import run_command_polling

        app.state.telegram_stop_event = asyncio.Event()
        app.state.telegram_polling_task = asyncio.create_task(
            run_command_polling(app.state, app.state.telegram_stop_event)
        )

    if settings.telegram_enabled and settings.auto_signal_enabled:
        from app.telegram_bot import run_auto_signal_loop

        app.state.auto_signal_stop_event = asyncio.Event()
        app.state.auto_signal_task = asyncio.create_task(
            run_auto_signal_loop(app.state, app.state.auto_signal_stop_event)
        )


@app.on_event("shutdown")
async def shutdown():
    tasks = (
        (getattr(app.state, "telegram_stop_event", None), getattr(app.state, "telegram_polling_task", None)),
        (getattr(app.state, "auto_signal_stop_event", None), getattr(app.state, "auto_signal_task", None)),
    )
    for stop_event, task in tasks:
        if stop_event is not None:
            stop_event.set()
        if task is not None:
            task.cancel()
    for _, task in tasks:
        if task is None:
            continue
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
