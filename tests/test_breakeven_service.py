def test_buy_reaches_30_percent_to_tp_moves_sl_to_entry():
    from app.services.breakeven_service import calculate_breakeven_stop

    position = {
        "ticket": 1,
        "symbol": "XAUUSD.c",
        "type": 0,
        "price_open": 100.0,
        "sl": 95.0,
        "tp": 110.0,
    }
    tick = {"bid": 103.0, "ask": 103.2}

    assert calculate_breakeven_stop(position, tick) == 100.0


def test_sell_reaches_30_percent_to_tp_moves_sl_to_entry():
    from app.services.breakeven_service import calculate_breakeven_stop

    position = {
        "ticket": 2,
        "symbol": "USDJPY.c",
        "type": 1,
        "price_open": 100.0,
        "sl": 105.0,
        "tp": 90.0,
    }
    tick = {"bid": 96.8, "ask": 97.0}

    assert calculate_breakeven_stop(position, tick) == 100.0


def test_position_below_30_percent_to_tp_does_not_move_sl():
    from app.services.breakeven_service import calculate_breakeven_stop

    position = {
        "ticket": 3,
        "symbol": "XAUUSD.c",
        "type": 0,
        "price_open": 100.0,
        "sl": 95.0,
        "tp": 110.0,
    }
    tick = {"bid": 102.9, "ask": 103.1}

    assert calculate_breakeven_stop(position, tick) is None


def test_already_protected_position_does_not_move_sl():
    from app.services.breakeven_service import calculate_breakeven_stop

    position = {
        "ticket": 4,
        "symbol": "XAUUSD.c",
        "type": 0,
        "price_open": 100.0,
        "sl": 100.0,
        "tp": 110.0,
    }
    tick = {"bid": 103.5, "ask": 103.7}

    assert calculate_breakeven_stop(position, tick) is None


def test_modify_position_sl_tp_sends_sltp_request(monkeypatch):
    from app.mt5_connector import execution as execution_module
    from app.mt5_connector.execution import modify_position_sl_tp

    sent = {}

    class FakeResult:
        retcode = 10009
        comment = "Done"

        def _asdict(self):
            return {"retcode": self.retcode, "comment": self.comment}

    monkeypatch.setattr(execution_module.mt5, "TRADE_ACTION_SLTP", 6, raising=False)
    monkeypatch.setattr(execution_module.mt5, "TRADE_RETCODE_DONE", 10009, raising=False)
    monkeypatch.setattr(execution_module.mt5, "order_send", lambda request: sent.update(request) or FakeResult())

    position = {"ticket": 123, "symbol": "XAUUSD.c", "tp": 110.0}

    result = modify_position_sl_tp(position, sl=100.0, tp=110.0)

    assert result["success"] is True
    assert sent["action"] == 6
    assert sent["position"] == 123
    assert sent["symbol"] == "XAUUSD.c"
    assert sent["sl"] == 100.0
    assert sent["tp"] == 110.0


def test_manage_breakeven_stops_modifies_eligible_position(monkeypatch):
    from app.services import breakeven_service
    from app.services.breakeven_service import manage_breakeven_stops

    position = {
        "ticket": 99,
        "symbol": "XAUUSD.c",
        "type": 0,
        "price_open": 100.0,
        "sl": 95.0,
        "tp": 110.0,
    }
    calls = []

    monkeypatch.setattr("app.mt5_connector.connection.is_mt5_connected", lambda: True)
    monkeypatch.setattr("app.mt5_connector.positions.get_open_positions", lambda symbol=None: [position])
    monkeypatch.setattr("app.mt5_connector.market_data.get_latest_tick", lambda symbol: {"bid": 103.0, "ask": 103.2})
    monkeypatch.setattr(
        "app.mt5_connector.execution.modify_position_sl_tp",
        lambda pos, sl, tp: calls.append((pos, sl, tp)) or {"success": True},
    )

    summary = manage_breakeven_stops()

    assert summary["checked"] == 1
    assert summary["modified"] == 1
    assert calls == [(position, 100.0, 110.0)]
