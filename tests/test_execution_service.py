from types import SimpleNamespace


def test_market_sell_uses_current_bid_as_order_price(monkeypatch):
    from app.services.execution_service import execute_trade

    captured = {}

    decision = SimpleNamespace(
        decision="SELL",
        entry_plan=SimpleNamespace(
            entry_type=SimpleNamespace(value="MARKET"),
            preferred_entry_price=113.03,
            stop_loss=113.15,
            take_profit_1=112.81,
        ),
    )

    monkeypatch.setattr(
        "app.risk.position_sizing.calculate_lot_size",
        lambda account_balance, sl_points, symbol_info: {"is_valid": True, "lot": 0.01},
    )

    def fake_build_order_request(**kwargs):
        captured.update(kwargs)
        return {"symbol": kwargs["symbol"], "price": kwargs["price"]}

    monkeypatch.setattr("app.mt5_connector.execution.build_order_request", fake_build_order_request)
    monkeypatch.setattr("app.mt5_connector.execution.check_order", lambda request: {"retcode": 0, "comment": "Done"})
    monkeypatch.setattr("app.mt5_connector.execution.send_order", lambda request: {"retcode": 10009, "order": 12345, "price": request["price"]})
    monkeypatch.setattr("app.database.repositories.save_trade", lambda trade_data: {"id": trade_data["id"]})
    monkeypatch.setattr("app.database.repositories.log_bot_event", lambda **kwargs: None)

    result = execute_trade(
        decision,
        {"symbol": "USDJPY.c"},
        {"point": 0.001, "digits": 3, "trade_stops_level": 0},
        1000.0,
        current_bid=113.031,
        current_ask=113.051,
    )

    assert result["success"] is True
    assert captured["price"] == 113.031
