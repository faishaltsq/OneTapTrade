from collections import namedtuple


def test_today_realized_pnl_sums_profit_swap_and_commission_for_symbol(monkeypatch):
    from app.mt5_connector import positions as positions_module
    from app.mt5_connector.positions import get_today_realized_pnl

    Deal = namedtuple("Deal", "symbol profit swap commission")
    deals = [
        Deal("XAUUSD.c", 10.0, -1.0, -0.5),
        Deal("EURUSD.c", 99.0, 0.0, 0.0),
    ]

    monkeypatch.setattr(positions_module.mt5, "history_deals_get", lambda start, end: deals)

    assert get_today_realized_pnl("XAUUSD.c") == 8.5
