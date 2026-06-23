from unittest.mock import patch, MagicMock


def _make_order(ticket, symbol, order_type, price_open, sl=0.0, tp=0.0, volume=0.01):
    return {
        "ticket": ticket,
        "symbol": symbol,
        "type": order_type,
        "price_open": price_open,
        "sl": sl,
        "tp": tp,
        "volume": volume,
    }


def _mt5_order_types():
    import MetaTrader5 as mt5
    return {
        "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
        "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
    }


def test_cap_does_nothing_when_count_at_or_below_max():
    from app.services.pending_order_manager import enforce_pending_order_cap

    types = _mt5_order_types()
    orders = [
        _make_order(1, "XAUUSD.c", types["BUY_LIMIT"], 1980.0),
        _make_order(2, "XAUUSD.c", types["BUY_LIMIT"], 1985.0),
    ]

    with patch("app.services.pending_order_manager.get_pending_orders", return_value=orders):
        with patch("app.services.pending_order_manager.cancel_pending_order") as mock_cancel:
            result = enforce_pending_order_cap("XAUUSD.c", max_orders=5)

    assert result["cancelled"] == 0
    mock_cancel.assert_not_called()


def test_cap_cancels_lowest_score_orders_when_above_max():
    from app.services.pending_order_manager import enforce_pending_order_cap

    types = _mt5_order_types()
    orders = [
        _make_order(1, "XAUUSD.c", types["BUY_LIMIT"], 1980.0),
        _make_order(2, "XAUUSD.c", types["BUY_LIMIT"], 1985.0),
        _make_order(3, "XAUUSD.c", types["BUY_LIMIT"], 1990.0),
        _make_order(4, "XAUUSD.c", types["BUY_LIMIT"], 1995.0),
        _make_order(5, "XAUUSD.c", types["BUY_LIMIT"], 1998.0),
        _make_order(6, "XAUUSD.c", types["BUY_LIMIT"], 1950.0),
        _make_order(7, "XAUUSD.c", types["BUY_LIMIT"], 1940.0),
    ]

    cancelled_tickets = []

    def fake_cancel(ticket):
        cancelled_tickets.append(ticket)
        return True

    with patch("app.services.pending_order_manager.get_pending_orders", return_value=orders):
        with patch("app.services.pending_order_manager.cancel_pending_order", side_effect=fake_cancel):
            with patch("app.services.pending_order_manager.get_latest_tick", return_value={"bid": 2000.0, "ask": 2000.5}):
                with patch("app.services.pending_order_manager.get_candles", return_value=MagicMock()):
                    with patch("app.services.pending_order_manager.build_smc_section", return_value={
                        "order_blocks": {
                            "demand": [{"low": 1970.0, "high": 1995.0, "index": 5}],
                            "supply": [],
                        },
                    }):
                        with patch("app.services.pending_order_manager.build_major_trend_section", return_value={
                            "bias": "D1_BULLISH",
                            "allowed_directions": ["BUY"],
                        }):
                            result = enforce_pending_order_cap("XAUUSD.c", max_orders=5)

    assert result["cancelled"] == 2
    assert len(cancelled_tickets) == 2
    assert 1950.0 not in [o["price_open"] for o in orders if o["ticket"] not in cancelled_tickets]


def test_cap_cancels_invalid_zone_orders_first():
    from app.services.pending_order_manager import enforce_pending_order_cap

    types = _mt5_order_types()
    orders = [
        _make_order(1, "XAUUSD.c", types["BUY_LIMIT"], 1980.0),
        _make_order(2, "XAUUSD.c", types["BUY_LIMIT"], 1985.0),
        _make_order(3, "XAUUSD.c", types["BUY_LIMIT"], 1990.0),
        _make_order(4, "XAUUSD.c", types["BUY_LIMIT"], 1995.0),
        _make_order(5, "XAUUSD.c", types["BUY_LIMIT"], 1998.0),
        _make_order(6, "XAUUSD.c", types["BUY_LIMIT"], 1800.0),
    ]

    cancelled_tickets = []

    def fake_cancel(ticket):
        cancelled_tickets.append(ticket)
        return True

    with patch("app.services.pending_order_manager.get_pending_orders", return_value=orders):
        with patch("app.services.pending_order_manager.cancel_pending_order", side_effect=fake_cancel):
            with patch("app.services.pending_order_manager.get_latest_tick", return_value={"bid": 2000.0, "ask": 2000.5}):
                with patch("app.services.pending_order_manager.get_candles", return_value=MagicMock()):
                    with patch("app.services.pending_order_manager.build_smc_section", return_value={
                        "order_blocks": {
                            "demand": [{"low": 1970.0, "high": 1995.0, "index": 5}],
                            "supply": [],
                        },
                    }):
                        with patch("app.services.pending_order_manager.build_major_trend_section", return_value={
                            "bias": "D1_BULLISH",
                            "allowed_directions": ["BUY"],
                        }):
                            result = enforce_pending_order_cap("XAUUSD.c", max_orders=5)

    assert result["cancelled"] == 1
    assert 6 in cancelled_tickets


def test_startup_validation_cancels_wrong_d1_direction():
    from app.services.pending_order_manager import validate_pending_orders_on_startup

    types = _mt5_order_types()
    orders = [
        _make_order(101, "XAUUSD.c", types["SELL_LIMIT"], 2010.0),
    ]

    cancelled = []

    def fake_cancel(ticket):
        cancelled.append(ticket)
        return True

    with patch("app.services.pending_order_manager.get_pending_orders", return_value=orders):
        with patch("app.services.pending_order_manager.cancel_pending_order", side_effect=fake_cancel):
            with patch("app.services.pending_order_manager.get_latest_tick", return_value={"bid": 2000.0, "ask": 2000.5}):
                with patch("app.services.pending_order_manager.get_candles", return_value=MagicMock()):
                    with patch("app.services.pending_order_manager.build_smc_section", return_value={
                        "order_blocks": {"demand": [], "supply": [{"low": 2005.0, "high": 2015.0, "index": 3}]},
                    }):
                        with patch("app.services.pending_order_manager.build_major_trend_section", return_value={
                            "bias": "D1_BULLISH",
                            "allowed_directions": ["BUY"],
                        }):
                            result = validate_pending_orders_on_startup()

    assert result["cancelled"] == 1
    assert 101 in cancelled


def test_startup_validation_cancels_entry_outside_ob():
    from app.services.pending_order_manager import validate_pending_orders_on_startup

    types = _mt5_order_types()
    orders = [
        _make_order(201, "XAUUSD.c", types["BUY_LIMIT"], 1800.0),
    ]

    cancelled = []

    def fake_cancel(ticket):
        cancelled.append(ticket)
        return True

    with patch("app.services.pending_order_manager.get_pending_orders", return_value=orders):
        with patch("app.services.pending_order_manager.cancel_pending_order", side_effect=fake_cancel):
            with patch("app.services.pending_order_manager.get_latest_tick", return_value={"bid": 2000.0, "ask": 2000.5}):
                with patch("app.services.pending_order_manager.get_candles", return_value=MagicMock()):
                    with patch("app.services.pending_order_manager.build_smc_section", return_value={
                        "order_blocks": {"demand": [{"low": 1970.0, "high": 1995.0, "index": 5}], "supply": []},
                    }):
                        with patch("app.services.pending_order_manager.build_major_trend_section", return_value={
                            "bias": "D1_BULLISH",
                            "allowed_directions": ["BUY"],
                        }):
                            result = validate_pending_orders_on_startup()

    assert result["cancelled"] == 1
    assert 201 in cancelled


def test_startup_validation_keeps_valid_order():
    from app.services.pending_order_manager import validate_pending_orders_on_startup

    types = _mt5_order_types()
    orders = [
        _make_order(301, "XAUUSD.c", types["BUY_LIMIT"], 1985.0),
    ]

    with patch("app.services.pending_order_manager.get_pending_orders", return_value=orders):
        with patch("app.services.pending_order_manager.cancel_pending_order") as mock_cancel:
            with patch("app.services.pending_order_manager.get_latest_tick", return_value={"bid": 2000.0, "ask": 2000.5}):
                with patch("app.services.pending_order_manager.get_candles", return_value=MagicMock()):
                    with patch("app.services.pending_order_manager.build_smc_section", return_value={
                        "order_blocks": {"demand": [{"low": 1970.0, "high": 1995.0, "index": 5}], "supply": []},
                    }):
                        with patch("app.services.pending_order_manager.build_major_trend_section", return_value={
                            "bias": "D1_BULLISH",
                            "allowed_directions": ["BUY"],
                        }):
                            result = validate_pending_orders_on_startup()

    assert result["cancelled"] == 0
    assert result["kept"] == 1
    mock_cancel.assert_not_called()


def test_startup_position_validation_warns_on_wrong_d1_but_does_not_close():
    from app.services.pending_order_manager import validate_open_positions_on_startup

    positions = [
        {"ticket": 501, "symbol": "XAUUSD.c", "type": 1, "price_open": 2000.0, "sl": 1990.0, "tp": 2020.0, "volume": 0.01},
    ]

    with patch("app.services.pending_order_manager.get_open_positions", return_value=positions):
        with patch("app.services.pending_order_manager.cancel_pending_order") as mock_cancel:
            with patch("app.services.pending_order_manager.get_latest_tick", return_value={"bid": 2000.0, "ask": 2000.5}):
                with patch("app.services.pending_order_manager.get_candles", return_value=MagicMock()):
                    with patch("app.services.pending_order_manager.build_smc_section", return_value={}):
                        with patch("app.services.pending_order_manager.build_major_trend_section", return_value={
                            "bias": "D1_BULLISH",
                            "allowed_directions": ["BUY"],
                        }):
                            result = validate_open_positions_on_startup()

    assert result["total"] == 1
    assert len(result["warnings"]) == 1
    assert "501" in result["warnings"][0]
    mock_cancel.assert_not_called()


def test_startup_position_validation_passes_valid_position():
    from app.services.pending_order_manager import validate_open_positions_on_startup

    positions = [
        {"ticket": 601, "symbol": "XAUUSD.c", "type": 0, "price_open": 2000.0, "sl": 1990.0, "tp": 2020.0, "volume": 0.01},
    ]

    with patch("app.services.pending_order_manager.get_open_positions", return_value=positions):
        with patch("app.services.pending_order_manager.get_latest_tick", return_value={"bid": 2000.0, "ask": 2000.5}):
            with patch("app.services.pending_order_manager.get_candles", return_value=MagicMock()):
                with patch("app.services.pending_order_manager.build_smc_section", return_value={}):
                    with patch("app.services.pending_order_manager.build_major_trend_section", return_value={
                        "bias": "D1_BULLISH",
                        "allowed_directions": ["BUY"],
                    }):
                        result = validate_open_positions_on_startup()

    assert result["total"] == 1
    assert result["valid"] == 1
    assert len(result["warnings"]) == 0
