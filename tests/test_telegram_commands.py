import asyncio
from types import SimpleNamespace


def test_help_command_lists_current_commands():
    from app.telegram_bot.bot import handle_command_text

    response = asyncio.run(handle_command_text("/help", SimpleNamespace()))

    assert "/status" in response
    assert "/last_signal" in response
    assert "/analyze" in response
    assert "/menu" in response
    assert "/positions" not in response


def test_last_signal_command_formats_latest_signal():
    from app.telegram_bot.bot import handle_command_text

    state = SimpleNamespace(
        latest_tradingview_signal={
            "symbol": "OANDA:XAUUSD",
            "action": "BUY",
            "price": 4030,
            "timeframe": "60",
        }
    )

    response = asyncio.run(handle_command_text("/last_signal", state))

    assert "OANDA:XAUUSD" in response
    assert "BUY" in response
    assert "4030" in response


def test_status_command_uses_tradingview_status(monkeypatch):
    from app.telegram_bot.bot import handle_command_text

    async def fake_run_tv_command(command):
        assert command == "status"
        return {
            "success": True,
            "chart_symbol": "OANDA:XAUUSD",
            "chart_resolution": "60",
        }

    monkeypatch.setattr("app.tradingview_mcp.run_tv_command", fake_run_tv_command)

    state = SimpleNamespace(latest_tradingview_signal={"action": "SELL"})
    response = asyncio.run(handle_command_text("/status", state))

    assert "TradingView" in response
    assert "OANDA:XAUUSD" in response
    assert "SELL" in response


def test_analyze_command_returns_signal_format_when_ai_not_configured(monkeypatch):
    from app.telegram_bot.bot import handle_command_text

    async def fake_context(**kwargs):
        return {
            "success": True,
            "state": {"symbol": "OANDA:XAUUSD", "resolution": "60"},
            "quote": {"last": 4030.5},
            "ohlcv_summary": {"change_pct": "1.2%"},
            "screenshot": {"success": True, "file_path": "C:/tmp/chart.png"},
        }

    async def fake_analysis(context, signal):
        return {"success": False, "configured": False, "analysis": None}

    monkeypatch.setattr("app.tradingview_mcp.get_chart_context", fake_context)
    monkeypatch.setattr("app.ai_analysis.analyze_chart_context", fake_analysis)

    state = SimpleNamespace(latest_tradingview_signal={"symbol": "OANDA:XAUUSD", "action": "BUY"})
    response = asyncio.run(handle_command_text("/analyze", state))

    assert "⚪ OANDA:XAUUSD — WAIT" in response
    assert "Bias:" in response
    assert "Confidence:" in response
    assert "Entry:" in response
    assert "Entry: WAIT - no trade" in response
    assert "SL: N/A" in response
    assert "Tentukan manual" not in response
    assert "Invalid jika:" in response
    assert "Risk:" in response
    assert "OANDA:XAUUSD" in response
    assert "4030.5" in response


def test_analyze_command_supports_multi_pair_args(monkeypatch):
    from app.telegram_bot.bot import build_analysis_responses

    calls = []

    async def fake_context(**kwargs):
        calls.append(kwargs)
        return {
            "success": True,
            "state": {"symbol": kwargs["symbol"], "resolution": kwargs["timeframe"]},
            "quote": {"last": 1.23},
            "ohlcv_summary": {"change_pct": "0.1%"},
            "screenshot": {"success": True, "file_path": f"C:/tmp/{kwargs['symbol'].split(':')[-1]}.png"},
        }

    async def fake_analysis(context, signal):
        return {"success": False, "configured": False, "analysis": None}

    monkeypatch.setattr("app.tradingview_mcp.get_chart_context", fake_context)
    monkeypatch.setattr("app.ai_analysis.analyze_chart_context", fake_analysis)

    responses = asyncio.run(build_analysis_responses("/analyze OANDA:XAUUSD,OANDA:EURUSD tf=15", SimpleNamespace()))

    assert len(responses) == 2
    assert calls[0]["symbol"] == "OANDA:XAUUSD"
    assert calls[1]["symbol"] == "OANDA:EURUSD"
    assert calls[0]["timeframe"] == "15"
    assert responses[0]["photo_path"] == "C:/tmp/XAUUSD.png"


def test_menu_alias_shows_help():
    from app.telegram_bot.bot import handle_command_text

    response = asyncio.run(handle_command_text("/menu", SimpleNamespace()))

    assert "OneTapTrade Commands" in response
    assert "/analyze" in response
