from app.analysis.smc_tp_target import find_smc_tp_target


def _smc(liquidity=None, fvg=None, supply=None, demand=None):
    return {
        "liquidity_levels": liquidity or [],
        "fvg_zones": fvg or [],
        "order_blocks": {
            "supply": supply or [],
            "demand": demand or [],
        },
    }


def test_buy_returns_nearest_liquidity_above_entry():
    smc = _smc(liquidity=[
        {"price": 105.0, "type": "high"},
        {"price": 102.0, "type": "high"},
    ])
    result = find_smc_tp_target("BUY", 100.0, smc)
    assert result == 102.0


def test_buy_returns_fvg_top_when_no_liquidity():
    smc = _smc(fvg=[
        {"direction": "bearish", "top": 103.0, "bottom": 101.0},
    ])
    result = find_smc_tp_target("BUY", 100.0, smc)
    assert result == 103.0


def test_sell_returns_nearest_liquidity_below_entry():
    smc = _smc(liquidity=[
        {"price": 95.0, "type": "low"},
        {"price": 98.0, "type": "low"},
    ])
    result = find_smc_tp_target("SELL", 100.0, smc)
    assert result == 98.0


def test_returns_none_when_no_smc_target():
    result = find_smc_tp_target("BUY", 100.0, _smc())
    assert result is None
