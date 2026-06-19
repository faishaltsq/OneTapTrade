from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_approve_callback_uses_global_open_positions_for_max_entry(monkeypatch):
    from app.services.trading_loop import TradingLoop

    loop = TradingLoop()
    loop._last_decisions["decision-1"] = {
        "ai_decision": SimpleNamespace(decision=SimpleNamespace(value="BUY")),
        "symbol": "EURUSD.c",
    }
    captured_context = {}

    monkeypatch.setattr("app.mt5_connector.connection.ensure_mt5_connected", lambda: True)
    monkeypatch.setattr(
        "app.mt5_connector.market_data.get_latest_tick",
        lambda symbol: {"bid": 1.1000, "ask": 1.1002},
    )
    monkeypatch.setattr("app.mt5_connector.market_data.get_spread", lambda symbol: 20)
    monkeypatch.setattr("app.mt5_connector.account.get_daily_drawdown_percent", lambda: 0.0)

    def fake_open_positions_count(symbol=None):
        return 1 if symbol is None else 0

    monkeypatch.setattr(
        "app.mt5_connector.positions.get_open_positions_count",
        fake_open_positions_count,
    )

    def fake_evaluate(ai_decision, market_context):
        captured_context.update(market_context)
        return {"approved": False, "reason": "max positions", "checks": {}}

    monkeypatch.setattr("app.risk.risk_manager.evaluate_decision", fake_evaluate)
    monkeypatch.setattr("app.database.repositories.save_risk_check", lambda **kwargs: None)

    result = await loop.handle_approve_callback("decision-1")

    assert result["success"] is False
    assert captured_context["open_positions_count"] == 1


@pytest.mark.asyncio
async def test_run_once_manages_breakeven_before_symbol_analysis(monkeypatch):
    from app.config import settings
    from app.services.trading_loop import TradingLoop

    events = []
    original_default_symbols = settings.default_symbols
    original_default_symbol = settings.default_symbol
    try:
        settings.default_symbols = "XAUUSD.c"
        settings.default_symbol = "XAUUSD.c"
        loop = TradingLoop()

        monkeypatch.setattr(
            "app.services.breakeven_service.manage_breakeven_stops",
            lambda symbol=None: events.append("breakeven") or {"checked": 0},
        )

        async def fake_run_symbol(symbol):
            events.append(f"symbol:{symbol}")
            return {"symbol": symbol}

        monkeypatch.setattr(loop, "_run_symbol", fake_run_symbol)

        result = await loop.run_once()

        assert result["symbols"] == ["XAUUSD.c"]
        assert events == ["breakeven", "symbol:XAUUSD.c"]
    finally:
        settings.default_symbols = original_default_symbols
        settings.default_symbol = original_default_symbol


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
