from app.tradingview_mcp import _timeframe_matches


def test_timeframe_matches_daily_alias():
    assert _timeframe_matches("1D", "D") is True
    assert _timeframe_matches("240", "240") is True
    assert _timeframe_matches("60", "240") is False
