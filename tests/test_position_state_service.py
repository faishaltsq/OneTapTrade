def test_sync_open_positions_builds_runtime_state(monkeypatch):
    from app.services.position_state_service import (
        clear_position_state,
        get_open_position_state,
        sync_open_positions_from_mt5,
    )

    clear_position_state()
    positions = [
        {
            "ticket": 101,
            "symbol": "XAUUSD.c",
            "type": 0,
            "price_open": 2430.0,
            "sl": 2420.0,
            "tp": 2440.0,
            "volume": 0.01,
            "profit": 1.5,
        }
    ]
    monkeypatch.setattr("app.mt5_connector.positions.get_open_positions", lambda symbol=None: positions)
    monkeypatch.setattr("app.database.repositories.get_trade_by_mt5_ticket", lambda ticket: {"id": "trade-1"})

    summary = sync_open_positions_from_mt5()

    assert summary["live_positions"] == 1
    state = get_open_position_state("XAUUSD.c")
    assert state["side"] == "BUY"
    assert state["ticket"] == 101


def test_has_opposite_position_blocks_only_opposite_side(monkeypatch):
    from app.services.position_state_service import (
        clear_position_state,
        has_opposite_position,
        sync_open_positions_from_mt5,
    )

    clear_position_state()
    monkeypatch.setattr(
        "app.mt5_connector.positions.get_open_positions",
        lambda symbol=None: [{"ticket": 102, "symbol": "XAUUSD.c", "type": 0}],
    )
    monkeypatch.setattr("app.database.repositories.get_trade_by_mt5_ticket", lambda ticket: {"id": "trade-1"})
    sync_open_positions_from_mt5()

    assert has_opposite_position("XAUUSD.c", "SELL") is True
    assert has_opposite_position("XAUUSD.c", "BUY") is False


def test_sync_open_positions_saves_missing_trade(monkeypatch):
    from app.services.position_state_service import clear_position_state, sync_open_positions_from_mt5

    clear_position_state()
    saved = []
    monkeypatch.setattr(
        "app.mt5_connector.positions.get_open_positions",
        lambda symbol=None: [{"ticket": 103, "symbol": "EURUSD.c", "type": 1, "volume": 0.02, "price_open": 1.1, "sl": 1.11, "tp": 1.08}],
    )
    monkeypatch.setattr("app.database.repositories.get_trade_by_mt5_ticket", lambda ticket: None)
    monkeypatch.setattr("app.database.repositories.save_trade", lambda trade_data: saved.append(trade_data) or trade_data)

    summary = sync_open_positions_from_mt5()

    assert summary["saved_trades"] == 1
    assert saved[0]["mt5_ticket"] == 103
    assert saved[0]["side"] == "SELL"
