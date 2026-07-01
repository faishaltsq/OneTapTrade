from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.tradingview import router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_tradingview_webhook_accepts_json_signal(monkeypatch):
    from app.config import settings

    messages = []
    original_secret = settings.tradingview_webhook_secret
    original_capture = settings.capture_chart_on_signal
    original_prediction = settings.prediction_drawing_enabled
    try:
        settings.tradingview_webhook_secret = "secret-1"
        settings.capture_chart_on_signal = False
        settings.prediction_drawing_enabled = False

        async def fake_send_message(text, reply_markup=None, **kwargs):
            messages.append(text)
            return True

        monkeypatch.setattr("app.telegram_bot.bot.send_message", fake_send_message)

        response = _client().post(
            "/tradingview/webhook",
            json={
                "secret": "secret-1",
                "symbol": "XAUUSD",
                "action": "buy",
                "price": 2345.6,
                "timeframe": "15",
                "message": "Breakout confirmed",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "received"
        assert body["telegram_sent"] is True
        assert body["signal"]["source"] == "TRADINGVIEW"
        assert body["signal"]["action"] == "BUY"
        assert messages
        assert "⚪ XAUUSD — BUY" in messages[0]
        assert "Entry: MARKET 2345.600" in messages[0]
        assert "SL: " in messages[0]
        assert "TP1: " in messages[0]
        assert "Tentukan manual" not in messages[0]
        assert "Risk:" in messages[0]
    finally:
        settings.tradingview_webhook_secret = original_secret
        settings.capture_chart_on_signal = original_capture
        settings.prediction_drawing_enabled = original_prediction


def test_tradingview_webhook_rejects_invalid_secret():
    from app.config import settings

    original_secret = settings.tradingview_webhook_secret
    original_capture = settings.capture_chart_on_signal
    original_prediction = settings.prediction_drawing_enabled
    try:
        settings.tradingview_webhook_secret = "secret-1"
        settings.capture_chart_on_signal = False
        settings.prediction_drawing_enabled = False
        response = _client().post("/tradingview/webhook", json={"secret": "wrong"})

        assert response.status_code == 401
    finally:
        settings.tradingview_webhook_secret = original_secret
        settings.capture_chart_on_signal = original_capture
        settings.prediction_drawing_enabled = original_prediction


def test_tradingview_webhook_accepts_plain_text(monkeypatch):
    from app.config import settings

    original_secret = settings.tradingview_webhook_secret
    original_capture = settings.capture_chart_on_signal
    original_prediction = settings.prediction_drawing_enabled
    try:
        settings.tradingview_webhook_secret = None
        settings.capture_chart_on_signal = False
        settings.prediction_drawing_enabled = False

        async def fake_send_message(text, reply_markup=None, **kwargs):
            return False

        monkeypatch.setattr("app.telegram_bot.bot.send_message", fake_send_message)

        response = _client().post("/tradingview/webhook", content="BUY XAUUSD")

        assert response.status_code == 200
        body = response.json()
        assert body["signal"]["action"] == "ALERT"
        assert body["signal"]["message"] == "BUY XAUUSD"
    finally:
        settings.tradingview_webhook_secret = original_secret
        settings.capture_chart_on_signal = original_capture
        settings.prediction_drawing_enabled = original_prediction


def test_tradingview_webhook_sends_screenshot_when_mcp_returns_photo(monkeypatch):
    from app.config import settings

    sent_photos = []
    original_secret = settings.tradingview_webhook_secret
    original_capture = settings.capture_chart_on_signal
    original_prediction = settings.prediction_drawing_enabled
    try:
        settings.tradingview_webhook_secret = None
        settings.capture_chart_on_signal = True
        settings.prediction_drawing_enabled = False

        async def fake_context(include_screenshot=True, include_indicators=True, symbol=None, timeframe=None):
            assert symbol == "XAUUSD"
            return {
                "success": True,
                "chart_updates": {"symbol": {"success": True, "symbol": symbol}},
                "screenshot": {
                    "success": True,
                    "file_path": "C:/tmp/chart.png",
                },
            }

        async def fake_send_photo(photo_path, caption=None, **kwargs):
            sent_photos.append((photo_path, caption))
            return True

        monkeypatch.setattr("app.tradingview_mcp.get_chart_context", fake_context)
        monkeypatch.setattr("app.telegram_bot.bot.send_photo", fake_send_photo)

        response = _client().post("/tradingview/webhook", json={"symbol": "XAUUSD", "action": "sell"})

        assert response.status_code == 200
        body = response.json()
        assert body["telegram_sent"] is True
        assert body["screenshot_path"] == "C:/tmp/chart.png"
        assert sent_photos[0][0] == "C:/tmp/chart.png"
        assert "⚪ XAUUSD — SELL" in sent_photos[0][1]
        assert "Tentukan manual" not in sent_photos[0][1]
    finally:
        settings.tradingview_webhook_secret = original_secret
        settings.capture_chart_on_signal = original_capture
        settings.prediction_drawing_enabled = original_prediction
