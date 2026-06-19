from types import SimpleNamespace


def test_build_order_request_uses_pending_buy_limit(monkeypatch):
    from app.mt5_connector import execution

    fake_mt5 = SimpleNamespace(
        TRADE_ACTION_PENDING=5,
        TRADE_ACTION_DEAL=1,
        ORDER_TYPE_BUY=0,
        ORDER_TYPE_SELL=1,
        ORDER_TYPE_BUY_LIMIT=2,
        ORDER_TYPE_SELL_LIMIT=3,
        ORDER_TIME_GTC=0,
        ORDER_FILLING_FOK=0,
        symbol_info_tick=lambda symbol: SimpleNamespace(ask=100.2, bid=100.0),
    )
    monkeypatch.setattr(execution, "mt5", fake_mt5)

    request = execution.build_order_request(
        symbol="XAUUSD.c",
        order_type="BUY",
        lot=0.01,
        sl=98.0,
        tp=102.0,
        is_limit=True,
        price=98.67,
    )

    assert request["action"] == fake_mt5.TRADE_ACTION_PENDING
    assert request["type"] == fake_mt5.ORDER_TYPE_BUY_LIMIT
    assert request["price"] == 98.67


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


def test_valid_smc_demand_zone_converts_buy_to_limit(monkeypatch):
    from app.services.execution_service import execute_trade

    captured = {}
    decision = SimpleNamespace(
        decision="BUY",
        confidence=0.49,
        entry_plan=SimpleNamespace(
            entry_type=SimpleNamespace(value="MARKET"),
            preferred_entry_price=100.2,
            stop_loss=98.0,
            take_profit_1=102.0,
        ),
    )
    payload = {
        "major_trend": {"allowed_directions": ["BUY"]},
        "primary_timeframe": {"market_structure": {"trend": "BULLISH"}},
        "entry_timeframe": {"market_structure": {"trend": "BULLISH"}},
        "smc": {
            "order_blocks": {"demand": [{"low": 98.0, "high": 99.0, "index": 8}], "supply": []},
            "choch": {"m5": {"bullish_choch": True}},
            "fvg_zones": [],
            "liquidity_levels": [],
        },
    }

    monkeypatch.setattr(
        "app.risk.position_sizing.calculate_lot_size",
        lambda account_balance, sl_points, symbol_info: {"is_valid": True, "lot": 0.01},
    )

    def fake_build_order_request(**kwargs):
        captured.update(kwargs)
        return {"symbol": kwargs["symbol"], "price": kwargs["price"], "is_limit": kwargs["is_limit"]}

    monkeypatch.setattr("app.mt5_connector.execution.build_order_request", fake_build_order_request)
    monkeypatch.setattr("app.mt5_connector.execution.check_order", lambda request: {"retcode": 0, "comment": "Done"})
    monkeypatch.setattr("app.mt5_connector.execution.send_order", lambda request: {"retcode": 10009, "order": 12345, "price": request["price"]})
    monkeypatch.setattr("app.database.repositories.save_trade", lambda trade_data: {"id": trade_data["id"]})
    monkeypatch.setattr("app.database.repositories.log_bot_event", lambda **kwargs: None)

    result = execute_trade(
        decision,
        {"symbol": "XAUUSD.c"},
        {"point": 0.01, "digits": 2, "trade_stops_level": 0},
        1000.0,
        current_bid=100.0,
        current_ask=100.2,
        market_payload=payload,
    )

    assert result["success"] is True
    assert captured["is_limit"] is True
    assert captured["price"] == 98.67


def test_no_valid_limit_rejects_weak_market_fallback(monkeypatch):
    from app.services.execution_service import execute_trade

    decision = SimpleNamespace(
        decision="BUY",
        confidence=0.50,
        entry_plan=SimpleNamespace(
            entry_type=SimpleNamespace(value="MARKET"),
            preferred_entry_price=100.2,
            stop_loss=99.0,
            take_profit_1=102.0,
        ),
    )
    payload = {
        "major_trend": {"allowed_directions": ["BUY"]},
        "primary_timeframe": {"market_structure": {"trend": "BULLISH"}},
        "entry_timeframe": {"market_structure": {"trend": "BULLISH"}},
        "smc": {"order_blocks": {"demand": [], "supply": []}},
    }

    result = execute_trade(
        decision,
        {"symbol": "XAUUSD.c"},
        {"point": 0.01, "digits": 2, "trade_stops_level": 0},
        1000.0,
        current_bid=100.0,
        current_ask=100.2,
        market_payload=payload,
    )

    assert result["success"] is False
    assert "No valid SMC LIMIT" in result["error"]


def test_pending_limit_placed_retcode_is_success(monkeypatch):
    from app.services.execution_service import execute_trade

    decision = SimpleNamespace(
        decision="BUY",
        confidence=0.7,
        entry_plan=SimpleNamespace(
            entry_type=SimpleNamespace(value="MARKET"),
            preferred_entry_price=100.2,
            stop_loss=98.0,
            take_profit_1=102.0,
        ),
    )
    payload = {
        "major_trend": {"allowed_directions": ["BUY"]},
        "primary_timeframe": {"market_structure": {"trend": "BULLISH"}},
        "entry_timeframe": {"market_structure": {"trend": "BULLISH"}},
        "smc": {
            "order_blocks": {"demand": [{"low": 98.0, "high": 99.0, "index": 8}], "supply": []},
            "choch": {"m5": {"bullish_choch": True}},
        },
    }
    monkeypatch.setattr(
        "app.risk.position_sizing.calculate_lot_size",
        lambda account_balance, sl_points, symbol_info: {"is_valid": True, "lot": 0.01},
    )
    monkeypatch.setattr("app.mt5_connector.execution.build_order_request", lambda **kwargs: {"price": kwargs["price"]})
    monkeypatch.setattr("app.mt5_connector.execution.check_order", lambda request: {"retcode": 0, "comment": "Done"})
    monkeypatch.setattr("app.mt5_connector.execution.send_order", lambda request: {"retcode": 10008, "order": 777, "price": request["price"]})
    monkeypatch.setattr("app.database.repositories.save_trade", lambda trade_data: {"id": trade_data["id"]})
    monkeypatch.setattr("app.database.repositories.log_bot_event", lambda **kwargs: None)

    result = execute_trade(
        decision,
        {"symbol": "XAUUSD.c"},
        {"point": 0.01, "digits": 2, "trade_stops_level": 0},
        1000.0,
        current_bid=100.0,
        current_ask=100.2,
        market_payload=payload,
    )

    assert result["success"] is True
    assert result["ticket"] == 777
