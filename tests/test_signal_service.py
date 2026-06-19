from types import SimpleNamespace


def test_generate_signal_uses_global_open_positions_for_max_entry(monkeypatch):
    from app.services.signal_service import generate_signal

    captured_context = {}

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
        return 1 if symbol is None else 0

    monkeypatch.setattr(
        "app.mt5_connector.positions.get_open_positions_count",
        fake_open_positions_count,
    )
    monkeypatch.setattr("app.mt5_connector.positions.has_open_position", lambda symbol: False)

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
            "major_trend": {"bias": "D1_BULLISH", "allowed_directions": ["BUY"]},
            "open_position_state": {"side": "BUY", "symbol": "EURUSD.c"},
        },
    )

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

    result = generate_signal("EURUSD.c")

    assert result["risk_result"]["approved"] is False
    assert captured_context["open_positions_count"] == 1
    assert captured_context["major_trend"] == {"bias": "D1_BULLISH", "allowed_directions": ["BUY"]}
    assert captured_context["open_position_state"] == {"side": "BUY", "symbol": "EURUSD.c"}
