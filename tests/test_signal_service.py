from types import SimpleNamespace


def test_generate_signal_uses_global_open_positions_for_max_entry(monkeypatch):
    from app.services.signal_service import generate_signal

    captured_context = {}
    captured_build_kwargs = {}

    monkeypatch.setattr("app.mt5_connector.connection.ensure_mt5_connected", lambda: True)
    monkeypatch.setattr("app.mt5_connector.market_data.select_symbol", lambda symbol: True)
    monkeypatch.setattr(
        "app.mt5_connector.market_data.get_symbol_info",
        lambda symbol: {"point": 0.01},
    )
    monkeypatch.setattr(
        "app.mt5_connector.market_data.get_latest_tick",
        lambda symbol: {"bid": 2010.0, "ask": 2010.5},
    )
    monkeypatch.setattr("app.mt5_connector.market_data.get_spread", lambda symbol: 50)
    monkeypatch.setattr("app.mt5_connector.market_data.get_candles", lambda *args, **kwargs: [1] * 100)
    monkeypatch.setattr("app.mt5_connector.market_data.get_market_depth", lambda symbol: None)

    monkeypatch.setattr("app.mt5_connector.account.get_balance", lambda: 1000.0)
    monkeypatch.setattr("app.mt5_connector.account.get_equity", lambda: 1000.0)
    monkeypatch.setattr("app.mt5_connector.account.get_daily_drawdown_percent", lambda: 0.0)

    def fake_open_positions_count(symbol=None):
        return 1 if symbol is None else 4

    monkeypatch.setattr(
        "app.mt5_connector.positions.get_open_positions_count",
        fake_open_positions_count,
    )

    def fake_build_market_payload(**kwargs):
        captured_build_kwargs.update(kwargs)
        return {
            "overall_regime": {"regime": "TRENDING"},
            "higher_timeframe": {},
            "primary_timeframe": {},
            "entry_timeframe": {},
            "current_price": {},
            "orderflow_proxy": {},
            "risk_config": {},
            "major_trend": {"bias": "D1_BULLISH", "allowed_directions": ["BUY"]},
            "open_position_state": {"side": "BUY", "symbol": "EURUSD.c"},
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

    def fake_evaluate(ai_decision, market_context):
        captured_context.update(market_context)
        return {"approved": False, "reason": "max positions", "checks": {}}

    monkeypatch.setattr("app.risk.risk_manager.evaluate_decision", fake_evaluate)

    monkeypatch.setattr(
        "app.analysis.noise_filter.evaluate_noise_filter",
        lambda df_d1, df_h4, df_h1, df_m5, risk_profile: {
            "passed": True,
            "blocked_by": None,
            "details": {},
            "hold_reason": "",
        },
    )

    result = generate_signal("EURUSD.c")

    assert result["risk_result"]["approved"] is False
    assert captured_build_kwargs["account_info"]["open_positions_count"] == 1
    assert captured_build_kwargs["account_info"]["open_positions_count_symbol"] == 4
    assert captured_build_kwargs["account_info"]["has_open_position"] is True
    assert captured_context["open_positions_count"] == 1
    assert captured_context["open_positions_count_symbol"] == 4
    assert captured_context["has_open_position"] is True
    assert captured_context["major_trend"] == {"bias": "D1_BULLISH", "allowed_directions": ["BUY"]}
    assert captured_context["open_position_state"] == {"side": "BUY", "symbol": "EURUSD.c"}


def test_noise_filter_block_returns_hold_without_ai_call():
    from unittest.mock import patch, MagicMock
    import pandas as pd
    from app.services import signal_service

    df_empty = pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume"])

    with patch("app.mt5_connector.connection.ensure_mt5_connected", return_value=True), \
         patch("app.mt5_connector.market_data.select_symbol", return_value=True), \
         patch("app.mt5_connector.market_data.get_symbol_info", return_value={"point": 0.01}), \
         patch("app.mt5_connector.market_data.get_latest_tick", return_value={"bid": 2000, "ask": 2001}), \
         patch("app.mt5_connector.market_data.get_spread", return_value=10), \
         patch("app.mt5_connector.market_data.get_candles", return_value=df_empty), \
         patch("app.mt5_connector.market_data.get_market_depth", return_value=None), \
         patch("app.mt5_connector.account.get_balance", return_value=10000), \
         patch("app.mt5_connector.account.get_equity", return_value=10000), \
         patch("app.mt5_connector.account.get_daily_drawdown_percent", return_value=0.0), \
         patch("app.mt5_connector.positions.get_open_positions_count", return_value=0), \
         patch("app.mt5_connector.positions.has_open_position", return_value=False), \
         patch("app.database.repositories.save_market_snapshot", return_value={"id": "snap1"}), \
         patch("app.ai_engine.deepseek_client.get_ai_decision") as mock_ai, \
         patch("app.config.settings.risk_profile", "LOW"):

        result = signal_service.generate_signal("XAUUSD")

        assert "ai_decision" in result
        decision = result["ai_decision"]
        assert decision.decision.value == "HOLD"
        assert "Noise filter" in (decision.main_reason or "")
        assert mock_ai.call_count == 0
        assert "noise_filter" in result
