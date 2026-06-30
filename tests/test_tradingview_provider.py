from app.market_data.tradingview_provider import TradingViewMarketDataProvider


def test_tradingview_provider_normalizes_candles():
    calls = []

    def runner(args):
        calls.append(args)
        if args[0] in {"symbol", "timeframe"}:
            return {"success": True}
        assert args == ["ohlcv", "--count", "2"]
        return {
            "bars": [
                {"timestamp": 1, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100},
                {"timestamp": 2, "open": 1.5, "high": 2.5, "low": 1, "close": 2, "volume": 200},
            ]
        }

    df = TradingViewMarketDataProvider(runner=runner).get_candles("OANDA:XAUUSD", "M15", 2)

    assert list(df.columns) == ["time", "open", "high", "low", "close", "tick_volume"]
    assert ["symbol", "OANDA:XAUUSD"] in calls
    assert ["timeframe", "15"] in calls
    assert df.iloc[-1].to_dict() == {
        "time": 2,
        "open": 1.5,
        "high": 2.5,
        "low": 1.0,
        "close": 2.0,
        "tick_volume": 200.0,
    }


def test_latest_price_uses_latest_close():
    def runner(args):
        if args[0] in {"symbol", "timeframe"}:
            return {"success": True}
        return {"bars": [{"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.75}]}

    provider = TradingViewMarketDataProvider(
        runner=runner
    )

    price = provider.get_latest_price("OANDA:XAUUSD")

    assert price == {"bid": 1.75, "ask": 1.75, "last": 1.75, "source": "TRADINGVIEW"}


def test_symbol_info_marks_tradingview_source():
    info = TradingViewMarketDataProvider(runner=lambda *_: []).get_symbol_info("OANDA:XAUUSD")

    assert info["symbol"] == "OANDA:XAUUSD"
    assert info["source"] == "TRADINGVIEW"
    assert info["point"] == 0.01


def test_missing_mcp_command_error_names_tradingview(monkeypatch):
    import subprocess

    from app.config import settings

    original_path = settings.tv_mcp_path
    settings.tv_mcp_path = "missing-tv-mcp"
    try:
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
        provider = TradingViewMarketDataProvider()

        try:
            provider.get_candles("OANDA:XAUUSD", "M15", 1)
        except RuntimeError as exc:
            assert "TradingView MCP command not found: missing-tv-mcp" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError")
    finally:
        settings.tv_mcp_path = original_path


def test_capture_screenshot_sets_symbol_timeframe_and_returns_png_path(tmp_path):
    calls = []
    mcp_path = tmp_path / "mcp_screenshot.png"

    def runner(args):
        calls.append(args)
        if args[0] == "screenshot":
            return {"success": True, "file_path": str(mcp_path)}
        return {"success": True}

    output_base = tmp_path / "signal_chart"
    provider = TradingViewMarketDataProvider(runner=runner)

    screenshot_path = provider.capture_screenshot("OANDA:XAUUSD", "M5", output_base=output_base)

    assert calls == [
        ["symbol", "OANDA:XAUUSD"],
        ["timeframe", "5"],
        ["screenshot", "--region", "chart", "--output", str(output_base)],
    ]
    assert screenshot_path == mcp_path
