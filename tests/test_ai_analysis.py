def test_fallback_wait_uses_no_trade_levels():
    from app.ai_analysis import fallback_signal_message

    message = fallback_signal_message(
        {
            "state": {"symbol": "OANDA:USDJPY"},
            "quote": {"last": 162.668},
            "ohlcv_summary": {"change_pct": "0.55%", "range": 1.2},
        },
        {"symbol": "OANDA:USDJPY", "action": "WAIT"},
    )

    assert "⚪ OANDA:USDJPY — WAIT" in message
    assert "Entry: WAIT - no trade" in message
    assert "SL: N/A" in message
    assert "TP1: N/A" in message
    assert "TP2: N/A" in message
    assert "Tentukan manual" not in message


def test_fallback_buy_generates_concrete_levels():
    from app.ai_analysis import fallback_signal_message

    message = fallback_signal_message(
        {
            "state": {"symbol": "OANDA:XAUUSD"},
            "quote": {"last": 4030.0},
            "ohlcv_summary": {"change_pct": "1.2%", "range": 80.0},
        },
        {"symbol": "OANDA:XAUUSD", "action": "BUY", "price": 4030.0},
    )

    assert "⚪ OANDA:XAUUSD — BUY" in message
    assert "Entry: MARKET 4030.000" in message
    assert "SL: " in message
    assert "TP1: " in message
    assert "TP2: " in message
    assert "N/A" not in message
    assert "Tentukan manual" not in message


def test_prompt_uses_deepseek_forex_daytrade_method():
    from app.ai_analysis import build_chart_analysis_prompt

    prompt = build_chart_analysis_prompt(
        {
            "state": {"symbol": "OANDA:EURUSD", "resolution": "60"},
            "quote": {"last": 1.0875},
            "ohlcv_summary": {"change_pct": "0.25%", "range": 0.004},
            "indicator_values": {"RSI": 58},
        },
        {"symbol": "OANDA:EURUSD", "action": "WAIT", "timeframe": "60"},
    )

    assert "DeepSeek-powered forex_daytrade" in prompt
    assert "FOREX DAY-TRADE METHOD" in prompt
    assert "liquidity sweep" in prompt
    assert "expected reward:risk is at least 1:1.5" in prompt
    assert "confidence is at least 70%" in prompt
