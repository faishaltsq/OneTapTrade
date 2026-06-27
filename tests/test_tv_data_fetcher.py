from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_fetch_tv_ohlcv_returns_dataframes():
    from app.tv_connector.schemas import OHLCVData
    from app.tv_connector.tv_data_fetcher import fetch_tv_ohlcv

    tools = MagicMock()
    tools.set_timeframe = AsyncMock(return_value=True)
    tools.get_ohlcv = AsyncMock(
        return_value=OHLCVData(
            symbol="EURUSD",
            timeframe="D1",
            bars=[
                {
                    "time": 1710000000,
                    "open": 1.1,
                    "high": 1.11,
                    "low": 1.09,
                    "close": 1.105,
                    "volume": 100,
                }
            ],
        )
    )

    result = await fetch_tv_ohlcv(tools, "EURUSD", ["D1", "H1"])

    assert set(result) == {"D1", "H1"}
    assert len(result["D1"]) == 1
    assert "close" in result["D1"].columns
    assert "tick_volume" in result["D1"].columns


@pytest.mark.asyncio
async def test_fetch_tv_quote_returns_tick_shape():
    from app.tv_connector.schemas import QuoteData
    from app.tv_connector.tv_data_fetcher import fetch_tv_quote

    tools = MagicMock()
    tools.get_quote = AsyncMock(
        return_value=QuoteData(symbol="EURUSD", bid=1.1, ask=1.1002, last=1.1001)
    )

    result = await fetch_tv_quote(tools)

    assert result["bid"] == 1.1
    assert result["ask"] == 1.1002
    assert result["mid"] == pytest.approx(1.1001)
    assert result["spread_points"] == 0


def test_classify_tv_pine_box_names():
    from app.tv_connector.tv_data_fetcher import classify_tv_box

    assert classify_tv_box("Demand OB") == "demand"
    assert classify_tv_box("Supply OB") == "supply"
    assert classify_tv_box("Bullish FVG") == "fvg"
    assert classify_tv_box("Equal Highs") == "liquidity"
    assert classify_tv_box("Unknown") == "other"


@pytest.mark.asyncio
async def test_fetch_tv_smc_zones_maps_pine_boxes_and_labels():
    from app.tv_connector.tv_data_fetcher import fetch_tv_smc_zones

    tools = MagicMock()
    tools.get_pine_boxes = AsyncMock(
        return_value=[
            SimpleNamespace(name="Demand OB", low=1.098, high=1.099, time=1),
            SimpleNamespace(name="Supply OB", low=1.102, high=1.103, time=2),
            SimpleNamespace(name="Bullish FVG", low=1.100, high=1.101, time=3),
            SimpleNamespace(name="Equal Highs", low=1.104, high=1.104, time=4),
        ]
    )
    tools.get_pine_labels = AsyncMock(
        return_value=[
            SimpleNamespace(text="Bullish CHoCH", price=1.101),
            SimpleNamespace(text="Bearish CHoCH", price=1.099),
        ]
    )

    result = await fetch_tv_smc_zones(tools)

    assert len(result["order_blocks"]["demand"]) == 1
    assert len(result["order_blocks"]["supply"]) == 1
    assert len(result["fvg_zones"]) == 1
    assert len(result["liquidity_levels"]) == 1
    assert result["choch"]["m5"]["bullish_choch"][0]["price"] == 1.101
    assert result["choch"]["m5"]["bearish_choch"][0]["price"] == 1.099
