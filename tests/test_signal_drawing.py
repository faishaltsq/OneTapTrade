import asyncio


def test_parse_prediction_levels_for_buy_limit_range():
    from app.signal_drawing import parse_prediction_levels

    message = """⚪ OANDA:EURUSD — BUY

Bias: Bullish
Confidence: 76%

Entry: LIMIT 1.0800-1.0820
SL: 1.0750
TP1: 1.0900
TP2: 1.1000
"""

    levels = parse_prediction_levels(message)

    assert levels["action"] == "BUY"
    assert levels["entry_type"] == "LIMIT"
    assert levels["entry"] == 1.081
    assert levels["sl"] == 1.075
    assert levels["tp1"] == 1.09
    assert levels["tp2"] == 1.1


def test_parse_prediction_levels_rejects_wait():
    from app.signal_drawing import parse_prediction_levels

    assert parse_prediction_levels("⚪ OANDA:EURUSD — WAIT\nEntry: WAIT - no trade\nSL: N/A") is None


def test_draw_prediction_creates_risk_reward_shapes(monkeypatch):
    from app.signal_drawing import draw_prediction


    calls = []

    async def fake_run_tv_command(*args):
        calls.append(args)
        return {"success": True, "entity_id": f"shape-{len(calls)}"}

    monkeypatch.setattr("app.signal_drawing.run_tv_command", fake_run_tv_command)

    message = """⚪ OANDA:XAUUSD — SELL

Bias: Bearish
Confidence: 78%

Entry: MARKET 2400
SL: 2410
TP1: 2380
TP2: 2360
"""
    context = {
        "state": {"resolution": "60"},
        "ohlcv_bars": {"bars": [{"time": 1000, "close": 2400}]},
    }

    result = asyncio.run(draw_prediction(message, context))

    assert result["success"] is True
    assert result["levels"]["action"] == "SELL"
    assert any("rectangle" in call for call in calls)
    assert any("horizontal_line" in call for call in calls)
    assert any("SHORT OANDA:XAUUSD MARKET" in call for call in calls)
