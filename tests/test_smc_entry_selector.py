from app.analysis.smc_entry_selector import can_use_market_fallback, select_smc_limit_entry


def _payload(demand=None, supply=None, allowed=None, h1_trend="BULLISH", m5_trend="BULLISH"):
    return {
        "major_trend": {"allowed_directions": allowed or ["BUY"]},
        "primary_timeframe": {"market_structure": {"trend": h1_trend}},
        "entry_timeframe": {"market_structure": {"trend": m5_trend}},
        "smc": {
            "order_blocks": {
                "demand": demand or [],
                "supply": supply or [],
            },
            "choch": {"m5": {"bullish_choch": True, "bearish_choch": False}},
            "fvg_zones": [],
            "liquidity_levels": [],
        },
    }


def test_buy_selects_demand_ob_below_current_ask_as_limit():
    result = select_smc_limit_entry(
        "BUY",
        current_bid=100.0,
        current_ask=100.2,
        market_payload=_payload(demand=[{"low": 98.0, "high": 99.0, "index": 8}]),
    )

    assert result["valid"] is True
    assert result["entry_type"] == "LIMIT"
    assert result["order_type"] == "BUY_LIMIT"
    assert result["zone_type"] == "demand_ob"
    assert result["entry_price"] == 98.67
    assert result["quality"] in {"MEDIUM", "HIGH"}


def test_sell_selects_supply_ob_above_current_bid_as_limit():
    result = select_smc_limit_entry(
        "SELL",
        current_bid=100.0,
        current_ask=100.2,
        market_payload=_payload(
            supply=[{"low": 101.0, "high": 102.0, "index": 8}],
            allowed=["SELL"],
            h1_trend="BEARISH",
            m5_trend="BEARISH",
        ),
    )

    assert result["valid"] is True
    assert result["entry_type"] == "LIMIT"
    assert result["order_type"] == "SELL_LIMIT"
    assert result["zone_type"] == "supply_ob"
    assert result["entry_price"] == 101.33


def test_buy_ignores_demand_ob_above_current_ask():
    result = select_smc_limit_entry(
        "BUY",
        current_bid=100.0,
        current_ask=100.2,
        market_payload=_payload(demand=[{"low": 101.0, "high": 102.0, "index": 8}]),
    )

    assert result["valid"] is False
    assert result["entry_type"] == "MARKET"


def test_sell_ignores_supply_ob_below_current_bid():
    result = select_smc_limit_entry(
        "SELL",
        current_bid=100.0,
        current_ask=100.2,
        market_payload=_payload(
            supply=[{"low": 98.0, "high": 99.0, "index": 8}],
            allowed=["SELL"],
            h1_trend="BEARISH",
            m5_trend="BEARISH",
        ),
    )

    assert result["valid"] is False
    assert result["entry_type"] == "MARKET"


def test_market_fallback_requires_confidence_above_50_and_trend_following():
    assert can_use_market_fallback("BUY", 0.51, _payload()) is True
    assert can_use_market_fallback("BUY", 0.50, _payload()) is False
    assert can_use_market_fallback(
        "BUY",
        0.8,
        _payload(h1_trend="BEARISH", m5_trend="BEARISH"),
    ) is False
