from unittest.mock import patch, MagicMock


def test_get_pending_orders_returns_empty_when_mt5_unavailable():
    from app.mt5_connector.orders import get_pending_orders

    with patch("app.mt5_connector.orders.mt5", None):
        result = get_pending_orders("XAUUSD")

    assert result == []


def test_get_pending_orders_count_returns_zero_when_no_orders():
    from app.mt5_connector.orders import get_pending_orders_count

    with patch("app.mt5_connector.orders.mt5") as mock_mt5:
        mock_mt5.orders_get.return_value = None
        result = get_pending_orders_count("XAUUSD")

    assert result == 0


def test_get_pending_orders_count_returns_count():
    from app.mt5_connector.orders import get_pending_orders_count

    orders = [MagicMock(), MagicMock(), MagicMock()]
    with patch("app.mt5_connector.orders.mt5") as mock_mt5:
        mock_mt5.orders_get.return_value = orders
        result = get_pending_orders_count("XAUUSD")

    assert result == 3


def test_cancel_pending_order_success():
    from app.mt5_connector.orders import cancel_pending_order

    with patch("app.mt5_connector.orders.mt5") as mock_mt5:
        mock_result = MagicMock()
        mock_result.retcode = mock_mt5.TRADE_RETCODE_DONE
        mock_mt5.order_send.return_value = mock_result
        result = cancel_pending_order(12345)

    assert result is True


def test_cancel_pending_order_failure():
    from app.mt5_connector.orders import cancel_pending_order

    with patch("app.mt5_connector.orders.mt5") as mock_mt5:
        mock_result = MagicMock()
        mock_result.retcode = 10013
        mock_mt5.order_send.return_value = mock_result
        result = cancel_pending_order(12345)

    assert result is False


def test_cancel_pending_orders_for_symbol_cancels_opposite_direction():
    from app.mt5_connector.orders import cancel_pending_orders_for_symbol

    order = MagicMock()
    order.ticket = 111
    order.symbol = "XAUUSD"
    order._asdict = lambda: {"ticket": 111, "symbol": "XAUUSD", "type": 2}

    with patch("app.mt5_connector.orders.get_pending_orders", return_value=[{"ticket": 111, "symbol": "XAUUSD", "type": 2}]):
        with patch("app.mt5_connector.orders._pending_order_side", return_value="BUY"):
            with patch("app.mt5_connector.orders.cancel_pending_order", return_value=True) as mock_cancel:
                result = cancel_pending_orders_for_symbol("XAUUSD", new_direction="SELL")

    assert result["cancelled"] == 1
    assert result["errors"] == 0
    mock_cancel.assert_called_once_with(111)


def test_cancel_pending_orders_for_symbol_keeps_same_direction():
    from app.mt5_connector.orders import cancel_pending_orders_for_symbol

    with patch("app.mt5_connector.orders.get_pending_orders", return_value=[{"ticket": 111, "symbol": "XAUUSD", "type": 2}]):
        with patch("app.mt5_connector.orders._pending_order_side", return_value="BUY"):
            with patch("app.mt5_connector.orders.cancel_pending_order") as mock_cancel:
                result = cancel_pending_orders_for_symbol("XAUUSD", new_direction="BUY")

    assert result["cancelled"] == 0
    assert result["kept"] == 1
    mock_cancel.assert_not_called()


def test_cancel_all_pending_orders_cancels_all():
    from app.mt5_connector.orders import cancel_all_pending_orders

    orders = [
        {"ticket": 101, "symbol": "XAUUSD.c", "type": 2},
        {"ticket": 102, "symbol": "EURUSD.c", "type": 3},
    ]
    with patch("app.mt5_connector.orders.get_pending_orders", return_value=orders):
        with patch("app.mt5_connector.orders.cancel_pending_order", return_value=True) as mock_cancel:
            result = cancel_all_pending_orders(None)

    assert result["total"] == 2
    assert result["cancelled"] == 2
    assert result["errors"] == 0
    assert mock_cancel.call_count == 2


def test_cancel_all_pending_orders_for_specific_symbol():
    from app.mt5_connector.orders import cancel_all_pending_orders

    orders = [{"ticket": 101, "symbol": "XAUUSD.c", "type": 2}]
    with patch("app.mt5_connector.orders.get_pending_orders", return_value=orders) as mock_get:
        with patch("app.mt5_connector.orders.cancel_pending_order", return_value=True):
            result = cancel_all_pending_orders("XAUUSD.c")

    mock_get.assert_called_once_with("XAUUSD.c")
    assert result["cancelled"] == 1


def test_cancel_all_pending_orders_no_orders():
    from app.mt5_connector.orders import cancel_all_pending_orders

    with patch("app.mt5_connector.orders.get_pending_orders", return_value=[]):
        with patch("app.mt5_connector.orders.cancel_pending_order") as mock_cancel:
            result = cancel_all_pending_orders(None)

    assert result["total"] == 0
    assert result["cancelled"] == 0
    mock_cancel.assert_not_called()
