from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_approve_callback_disabled_in_tradingview_mode():
    from app.services.trading_loop import TradingLoop

    loop = TradingLoop()
    loop._last_decisions["decision-1"] = {
        "ai_decision": SimpleNamespace(decision=SimpleNamespace(value="BUY")),
        "symbol": "OANDA:EURUSD",
    }

    result = await loop.handle_approve_callback("decision-1")

    assert result["success"] is False
    assert result["error"] == "Execution disabled in TradingView signal-only mode"


@pytest.mark.asyncio
async def test_run_once_skips_breakeven_in_tradingview_mode(monkeypatch):
    from app.config import settings
    from app.services.trading_loop import TradingLoop

    events = []
    original_default_symbols = settings.default_symbols
    original_default_symbol = settings.default_symbol
    try:
        settings.default_symbols = "OANDA:XAUUSD"
        settings.default_symbol = "OANDA:XAUUSD"
        loop = TradingLoop()

        monkeypatch.setattr(
            "app.market_data.providers.get_market_data_provider",
            lambda: SimpleNamespace(health_check=lambda: True),
        )

        monkeypatch.setattr(
            "app.services.breakeven_service.manage_breakeven_stops",
            lambda symbol=None: events.append("breakeven") or {"checked": 0},
        )

        async def fake_run_symbol(symbol):
            events.append(f"symbol:{symbol}")
            return {"symbol": symbol}

        monkeypatch.setattr(loop, "_run_symbol", fake_run_symbol)

        result = await loop.run_once()

        assert result["symbols"] == ["OANDA:XAUUSD"]
        assert events == ["symbol:OANDA:XAUUSD"]
    finally:
        settings.default_symbols = original_default_symbols
        settings.default_symbol = original_default_symbol


@pytest.mark.asyncio
async def test_run_once_skips_symbols_when_tradingview_provider_unavailable(monkeypatch):
    from app.config import settings
    from app.services.trading_loop import TradingLoop

    class UnavailableProvider:
        def health_check(self):
            return False

    original_default_symbols = settings.default_symbols
    try:
        settings.default_symbols = "OANDA:XAUUSD,OANDA:EURUSD"
        loop = TradingLoop()
        monkeypatch.setattr("app.market_data.providers.get_market_data_provider", lambda: UnavailableProvider())

        async def fail_run_symbol(symbol):
            raise AssertionError("symbol analysis should be skipped")

        monkeypatch.setattr(loop, "_run_symbol", fail_run_symbol)

        result = await loop.run_once()

        assert result["skipped"] is True
        assert result["error"] == f"TradingView MCP unavailable: {settings.tv_mcp_path}"
        assert result["symbols"] == ["OANDA:XAUUSD", "OANDA:EURUSD"]
    finally:
        settings.default_symbols = original_default_symbols


@pytest.mark.asyncio
async def test_send_market_update_renders_payload_dashboard(monkeypatch):
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, MarketRegime, TimeframeBias
    from app.services.trading_loop import TradingLoop

    sent = {}
    loop = TradingLoop()
    decision = AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.4,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.RANGING,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BEARISH,
        main_reason="Waiting for cleaner trend.",
    )
    payload = {
        "current_price": {"bid": 2432.1, "ask": 2432.45, "spread_points": 35},
        "entry_timeframe": {"indicators": {"rsi_14": 48.1}, "market_structure": {"trend": "BEARISH"}},
        "primary_timeframe": {"indicators": {"rsi_14": 56.4}, "market_structure": {"trend": "BULLISH"}},
        "higher_timeframe": {"market_structure": {"trend": "BULLISH"}},
        "secondary_timeframe": {"market_structure": {"trend": "RANGING"}},
        "overall_regime": {"regime": "RANGING"},
        "orderflow_proxy": {},
        "smc": {},
    }

    async def fake_send_message(text):
        sent["text"] = text
        return True

    monkeypatch.setattr("app.telegram_bot.bot.send_message", fake_send_message)

    await loop._send_market_update(decision, "XAUUSD.c", payload)

    assert "Market Trend — XAUUSD.c" in sent["text"]
    assert "Bid/Ask: 2432.1 / 2432.45" in sent["text"]
    assert "M5 RSI: 48.1" in sent["text"]
