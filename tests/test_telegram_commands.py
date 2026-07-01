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


def test_analyze_command_redraws_screenshot_after_prediction(monkeypatch):
    from app.telegram_bot.bot import build_analysis_responses

    async def fake_context(**kwargs):
        return {
            "success": True,
            "state": {"symbol": kwargs["symbol"], "resolution": kwargs["timeframe"]},
            "quote": {"last": 4030.0},
            "ohlcv_summary": {"change_pct": "1.2%", "range": 80.0},
            "screenshot": {"success": True, "file_path": "C:/tmp/before.png"},
        }

    async def fake_analysis(context, signal):
        return {
            "success": True,
            "analysis": "⚪ OANDA:XAUUSD — BUY\n\nBias: Bullish\nConfidence: 80%\n\nEntry: MARKET 4030\nSL: 4020\nTP1: 4050\nTP2: 4070\n\nReason:\nValid.\n\nInvalid jika:\nBreak SL.\n\nRisk:\nGunakan lot sesuai manajemen risiko.",
        }

    async def fake_draw_prediction(message, context):
        return {"success": True}

    async def fake_run_tv_command(*args):
        assert args == ("screenshot", "-r", "chart")
        return {"success": True, "file_path": "C:/tmp/after.png"}

    monkeypatch.setattr("app.tradingview_mcp.get_chart_context", fake_context)
    monkeypatch.setattr("app.ai_analysis.analyze_chart_context", fake_analysis)
    monkeypatch.setattr("app.signal_drawing.draw_prediction", fake_draw_prediction)
    monkeypatch.setattr("app.tradingview_mcp.run_tv_command", fake_run_tv_command)

    responses = asyncio.run(build_analysis_responses("/analyze OANDA:XAUUSD tf=60", SimpleNamespace()))

    assert responses[0]["photo_path"] == "C:/tmp/after.png"
    assert responses[0]["drawing"]["success"] is True


def test_menu_alias_shows_help():
    from app.telegram_bot.bot import handle_command_text

    response = asyncio.run(handle_command_text("/menu", SimpleNamespace()))

    assert "OneTapTrade Commands" in response
    assert "/analyze" in response


def test_auto_signal_filter_uses_action_and_confidence():
    from app.telegram_bot.bot import parse_signal_summary, should_send_auto_signal

    text = "⚪ OANDA:EURUSD — BUY\n\nBias: Bullish\nConfidence: 74%\n\nEntry: LIMIT 1.0800"

    assert parse_signal_summary(text) == {
        "symbol": "OANDA:EURUSD",
        "action": "BUY",
        "confidence": 74,
    }
    assert should_send_auto_signal(text, min_confidence=70) is True
    assert should_send_auto_signal(text, min_confidence=80) is False
    assert should_send_auto_signal("⚪ OANDA:EURUSD — WAIT\nConfidence: 90%", 70) is False
    assert should_send_auto_signal("⚪ OANDA:EURUSD — WAIT\nConfidence: 90%", 70, send_wait=True) is True


def test_auto_signal_loop_sends_filtered_signal(monkeypatch):
    from app.config import settings
    from app.telegram_bot.bot import run_auto_signal_loop

    sent_messages = []
    stop_event = asyncio.Event()

    async def fake_responses(text, app_state):
        assert text == "/analyze all tf=60"
        return [
            {
                "text": "⚪ OANDA:XAUUSD — BUY\n\nBias: Bullish\nConfidence: 75%\n\nEntry: LIMIT 4030",
                "photo_path": None,
            },
            {
                "text": "⚪ OANDA:EURUSD — WAIT\n\nBias: Neutral\nConfidence: 80%\n\nEntry: WAIT - no trade",
                "photo_path": None,
            },
        ]

    async def fake_send_message(text, **kwargs):
        sent_messages.append(text)
        stop_event.set()
        return True

    original_values = {
        "auto_signal_enabled": settings.auto_signal_enabled,
        "auto_signal_interval_minutes": settings.auto_signal_interval_minutes,
        "auto_signal_timeframe": settings.auto_signal_timeframe,
        "auto_signal_min_confidence": settings.auto_signal_min_confidence,
        "auto_signal_send_wait": settings.auto_signal_send_wait,
        "auto_signal_cooldown_minutes": settings.auto_signal_cooldown_minutes,
        "telegram_bot_token": settings.telegram_bot_token,
        "telegram_allowed_chat_id": settings.telegram_allowed_chat_id,
        "ai_api_key": settings.ai_api_key,
    }
    try:
        settings.auto_signal_enabled = True
        settings.auto_signal_interval_minutes = 1
        settings.auto_signal_timeframe = ""
        settings.auto_signal_min_confidence = 70
        settings.auto_signal_send_wait = False
        settings.auto_signal_cooldown_minutes = 60
        settings.telegram_bot_token = "token"
        settings.telegram_allowed_chat_id = "123"
        settings.ai_api_key = "key"

        monkeypatch.setattr("app.telegram_bot.bot.build_analysis_responses", fake_responses)
        monkeypatch.setattr("app.telegram_bot.bot.send_message", fake_send_message)

        asyncio.run(run_auto_signal_loop(SimpleNamespace(auto_signal_last_sent={}), stop_event))
    finally:
        for key, value in original_values.items():
            setattr(settings, key, value)

    assert len(sent_messages) == 1
    assert "OANDA:XAUUSD" in sent_messages[0]
    assert "OANDA:EURUSD" not in sent_messages[0]
