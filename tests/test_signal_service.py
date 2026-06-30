from types import SimpleNamespace

import pandas as pd


class FakeProvider:
    def __init__(self):
        self.calls = []

    def get_symbol_info(self, symbol):
        self.calls.append(("info", symbol))
        return {"point": 0.01, "source": "TRADINGVIEW"}

    def get_latest_price(self, symbol):
        self.calls.append(("price", symbol))
        return {"bid": 2010.0, "ask": 2010.0, "last": 2010.0}

    def get_candles(self, symbol, timeframe, count):
        self.calls.append(("candles", symbol, timeframe, count))
        return pd.DataFrame(
            [{"time": i, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "tick_volume": 100} for i in range(count)]
        )


def test_generate_signal_uses_tradingview_provider_without_mt5(monkeypatch):
    from app.services.signal_service import generate_signal

    provider = FakeProvider()
    captured_context = {}
    captured_payload = {}

    monkeypatch.setattr("app.mt5_connector.connection.ensure_mt5_connected", lambda: (_ for _ in ()).throw(AssertionError("MT5 called")))
    monkeypatch.setattr("app.market_data.providers.get_market_data_provider", lambda: provider)

    def fake_build_market_payload(**kwargs):
        captured_payload.update(kwargs)
        return {
            "overall_regime": {"regime": "TRENDING"},
            "higher_timeframe": {},
            "primary_timeframe": {},
            "entry_timeframe": {},
            "current_price": {},
            "orderflow_proxy": {},
            "risk_config": {},
            "major_trend": {"bias": "D1_BULLISH", "allowed_directions": ["BUY"]},
            "open_position_state": {},
        }

    monkeypatch.setattr("app.analysis.feature_builder.build_market_payload", fake_build_market_payload)

    decision = SimpleNamespace(
        decision=SimpleNamespace(value="BUY"),
        confidence=0.8,
        execution_permission=SimpleNamespace(ai_allows_execution=True),
        model_dump=lambda: {},
    )
    monkeypatch.setattr("app.ai_engine.deepseek_client.get_ai_decision", lambda payload: decision)
    monkeypatch.setattr("app.ai_engine.deepseek_client.validate_decision", lambda ai_decision, market_payload=None: ai_decision)
    monkeypatch.setattr("app.ai_engine.decision_parser.format_decision_for_db", lambda ai_decision: {})
    monkeypatch.setattr("app.database.repositories.save_market_snapshot", lambda snapshot: {"id": "snapshot-1"})
    monkeypatch.setattr("app.database.repositories.save_ai_decision", lambda decision_db: {"id": "decision-1"})
    monkeypatch.setattr("app.database.repositories.save_risk_check", lambda **kwargs: None)
    monkeypatch.setattr(
        "app.analysis.noise_filter.evaluate_noise_filter",
        lambda df_d1, df_h4, df_h1, df_m15, risk_profile: {
            "passed": True,
            "blocked_by": None,
            "details": {},
            "hold_reason": "",
        },
    )

    def fake_evaluate(ai_decision, market_context):
        captured_context.update(market_context)
        return {"approved": True, "reason": "signal only", "checks": {}}

    monkeypatch.setattr("app.risk.risk_manager.evaluate_decision", fake_evaluate)

    result = generate_signal("OANDA:XAUUSD")

    assert result["symbol"] == "OANDA:XAUUSD"
    assert result["risk_result"]["approved"] is True
    assert captured_payload["account_info"]["open_positions_count"] == 0
    assert captured_payload["account_info"]["has_open_position"] is False
    assert captured_context["open_positions_count"] == 0
    assert captured_context["daily_drawdown_percent"] == 0.0
    assert provider.calls[0] == ("info", "OANDA:XAUUSD")
    assert ("candles", "OANDA:XAUUSD", "M15", 100) in provider.calls
    assert result["market_payload"]["market_data_source"] == "TRADINGVIEW"


def test_noise_filter_block_returns_hold_without_ai_call(monkeypatch):
    from app.services import signal_service

    provider = FakeProvider()
    monkeypatch.setattr("app.market_data.providers.get_market_data_provider", lambda: provider)
    monkeypatch.setattr(
        "app.analysis.feature_builder.build_market_payload",
        lambda **kwargs: {
            "overall_regime": {"regime": "TRENDING"},
            "higher_timeframe": {},
            "primary_timeframe": {},
            "entry_timeframe": {},
            "current_price": {},
            "orderflow_proxy": {},
            "risk_config": {},
        },
    )
    monkeypatch.setattr("app.database.repositories.save_market_snapshot", lambda snapshot: {"id": "snap1"})
    monkeypatch.setattr("app.database.repositories.save_ai_decision", lambda decision_db: {"id": "decision-1"})
    monkeypatch.setattr("app.ai_engine.decision_parser.format_decision_for_db", lambda ai_decision: {})
    monkeypatch.setattr(
        "app.analysis.noise_filter.evaluate_noise_filter",
        lambda df_d1, df_h4, df_h1, df_m15, risk_profile: {
            "passed": False,
            "blocked_by": "volume",
            "details": {},
            "hold_reason": "Volume too low",
        },
    )

    def fail_ai(payload):
        raise AssertionError("AI should not be called")

    monkeypatch.setattr("app.ai_engine.deepseek_client.get_ai_decision", fail_ai)

    result = signal_service.generate_signal("OANDA:XAUUSD")

    assert "ai_decision" in result
    decision = result["ai_decision"]
    assert decision.decision.value == "HOLD"
    assert "Noise filter" in (decision.main_reason or "")
    assert "noise_filter" in result
