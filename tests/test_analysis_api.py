from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.analysis import router


def _client():
    app = FastAPI()
    app.state.latest_tradingview_signal = {"symbol": "XAUUSD", "action": "BUY"}
    app.include_router(router)
    return TestClient(app)


def test_chart_context_endpoint_uses_tradingview_mcp(monkeypatch):
    async def fake_context(include_screenshot=True, include_indicators=True, symbol=None, timeframe=None):
        return {
            "success": True,
            "include_screenshot": include_screenshot,
            "include_indicators": include_indicators,
            "symbol": symbol,
            "timeframe": timeframe,
            "quote": {"success": True, "symbol": "OANDA:XAUUSD"},
        }

    monkeypatch.setattr("app.api.analysis.get_chart_context", fake_context)

    response = _client().get("/analysis/chart-context?screenshot=false&indicators=false&symbol=OANDA:XAUUSD&timeframe=60")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["include_screenshot"] is False
    assert body["include_indicators"] is False
    assert body["symbol"] == "OANDA:XAUUSD"
    assert body["timeframe"] == "60"


def test_chart_analysis_endpoint_returns_context_and_ai(monkeypatch):
    async def fake_context(include_screenshot=True, include_indicators=True, symbol=None, timeframe=None):
        return {"success": True, "symbol": symbol, "timeframe": timeframe, "quote": {"success": True, "close": 4030.0}}

    async def fake_analysis(context, signal=None):
        return {"success": True, "analysis": f"Signal {signal['action']} analyzed"}

    monkeypatch.setattr("app.api.analysis.get_chart_context", fake_context)
    monkeypatch.setattr("app.api.analysis.analyze_chart_context", fake_analysis)

    response = _client().post("/analysis/chart")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["chart_context"]["symbol"] == "XAUUSD"
    assert body["ai_analysis"]["analysis"] == "Signal BUY analyzed"
