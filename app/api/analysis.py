from fastapi import APIRouter, Query, Request

from app.ai_analysis import analyze_chart_context
from app.tradingview_mcp import get_chart_context

router = APIRouter(prefix="/analysis")


@router.get("/chart-context")
async def chart_context(
    screenshot: bool = Query(default=True),
    indicators: bool = Query(default=True),
    symbol: str | None = Query(default=None),
    timeframe: str | None = Query(default=None),
):
    return await get_chart_context(
        include_screenshot=screenshot,
        include_indicators=indicators,
        symbol=symbol,
        timeframe=timeframe,
    )


@router.post("/chart")
async def analyze_chart(
    request: Request,
    screenshot: bool = Query(default=True),
    indicators: bool = Query(default=True),
    symbol: str | None = Query(default=None),
    timeframe: str | None = Query(default=None),
):
    latest_signal = getattr(request.app.state, "latest_tradingview_signal", None)
    target_symbol = symbol or (latest_signal or {}).get("symbol")
    target_timeframe = timeframe or (latest_signal or {}).get("timeframe")
    context = await get_chart_context(
        include_screenshot=screenshot,
        include_indicators=indicators,
        symbol=target_symbol,
        timeframe=target_timeframe,
    )
    analysis = await analyze_chart_context(context, latest_signal)

    return {
        "success": context.get("success", False),
        "chart_context": context,
        "ai_analysis": analysis,
    }
