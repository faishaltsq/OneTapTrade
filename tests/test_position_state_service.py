from unittest.mock import patch, MagicMock


def test_sync_pending_orders_stores_by_symbol():
    from app.services.position_state_service import sync_pending_orders_from_mt5, _PENDING_ORDER_STATE

    _PENDING_ORDER_STATE.clear()

    order = {
        "ticket": 123,
        "symbol": "XAUUSD",
        "type": 2,
        "volume": 0.01,
        "price_open": 2000.0,
        "sl": 1990.0,
        "tp": 2020.0,
    }

    with patch("app.mt5_connector.orders.get_pending_orders", return_value=[order]):
        summary = sync_pending_orders_from_mt5()

    assert summary["pending_orders"] == 1
    assert "XAUUSD" in _PENDING_ORDER_STATE
    assert _PENDING_ORDER_STATE["XAUUSD"][0]["ticket"] == 123


def test_sync_pending_orders_clears_state_before_sync():
    from app.services.position_state_service import sync_pending_orders_from_mt5, _PENDING_ORDER_STATE

    _PENDING_ORDER_STATE["OLD"] = [{"ticket": 999}]

    with patch("app.mt5_connector.orders.get_pending_orders", return_value=[]):
        summary = sync_pending_orders_from_mt5()

    assert summary["pending_orders"] == 0
    assert "OLD" not in _PENDING_ORDER_STATE
