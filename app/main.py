import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.logger import logger
from app.config import settings
from app.services.trading_loop import TradingLoop

from app.api.health import router as health_router
from app.api.status import router as status_router
from app.api.controls import router as controls_router
from app.api.trades import router as trades_router
from app.api.settings import router as settings_router
from app.api.signals import router as signals_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("AI TradingView Signal Bot starting — FRESH SESSION")
    logger.info(f"Mode: {settings.bot_mode} | Profile: {settings.risk_profile}")
    logger.info(f"Symbols: {settings.symbols}")
    logger.info(f"Environment: {settings.app_env}")
    logger.info("=" * 60)

    mt5_ok = False
    if settings.is_tradingview_mode:
        logger.info("TradingView signal-only mode — MT5 startup skipped; execution disabled")
        try:
            from app.market_data.tradingview_launcher import launch_tradingview_if_configured

            launch_result = launch_tradingview_if_configured()
            if launch_result.get("launched"):
                logger.info(f"TradingView launched with debug port {launch_result.get('port')}")
            else:
                logger.info(f"TradingView launch skipped: {launch_result.get('reason')}")
        except Exception as e:
            logger.error(f"TradingView launch failed: {e}")
    else:
        try:
            from app.mt5_connector.connection import initialize_mt5, login_mt5

            if initialize_mt5():
                logger.info("MT5 initialized")
                if login_mt5():
                    logger.info("MT5 login successful")
                    mt5_ok = True
                    try:
                        from app.services.position_state_service import sync_open_positions_from_mt5

                        sync_summary = sync_open_positions_from_mt5()
                        logger.info(f"Startup open position sync complete: {sync_summary}")
                    except Exception as e:
                        logger.error(f"Startup open position sync failed: {e}")
                else:
                    logger.warning("MT5 login failed — running without MT5")
            else:
                logger.warning("MT5 initialization failed — running without MT5")
        except Exception as e:
            logger.error(f"MT5 init error: {e}")

        logger.info(f"MT5 connected: {mt5_ok}")

    try:
        from app.database.supabase_client import supabase_available

        db_ok = supabase_available()
        logger.info(f"Supabase database available: {db_ok}")
    except Exception as e:
        logger.warning(f"Database init check failed: {e}")

    trading_loop = TradingLoop()
    app.state.trading_loop = trading_loop
    loop_task = asyncio.create_task(trading_loop.run_forever())
    logger.info("Trading loop started in background — running immediately")

    telegram_task = None
    try:
        from app.telegram_bot.bot import init_telegram_bot, run_bot

        if init_telegram_bot(trading_loop):
            telegram_task = asyncio.create_task(run_bot())
            logger.info("Telegram bot started in background")
        else:
            logger.warning("Telegram bot not configured — skipping")
    except Exception as e:
        logger.error(f"Telegram bot init failed: {e}")

    logger.info("=" * 60)
    logger.info("AI TradingView Signal Bot started")
    logger.info("=" * 60)

    yield

    logger.info("=" * 60)
    logger.info("AI TradingView Signal Bot shutting down...")

    trading_loop.stop()
    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass
    logger.info("Trading loop stopped — no pending tasks")

    if telegram_task is not None:
        try:
            from app.telegram_bot.bot import stop_bot

            await stop_bot()
            telegram_task.cancel()
            try:
                await telegram_task
            except asyncio.CancelledError:
                pass
            logger.info("Telegram bot stopped")
        except Exception as e:
            logger.error(f"Error stopping Telegram bot: {e}")

    if mt5_ok:
        try:
            from app.mt5_connector.connection import shutdown_mt5

            shutdown_mt5()
            logger.info("MT5 shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down MT5: {e}")

    logger.info("AI TradingView Signal Bot shutdown complete")
    logger.info("=" * 60)


app = FastAPI(
    title="AI TradingView Signal Bot",
    version="0.1.0",
    description="AI-powered TradingView signal system using DeepSeek AI, Telegram control, and Supabase database",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, tags=["Health"])
app.include_router(status_router, tags=["Status"])
app.include_router(controls_router, tags=["Controls"])
app.include_router(trades_router, tags=["Trades"])
app.include_router(settings_router, tags=["Settings"])
app.include_router(signals_router, tags=["Signals"])


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
