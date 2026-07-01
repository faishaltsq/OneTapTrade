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


def test_daytrade_indicator_context_extracts_ema_and_smc():
    from app.ai_analysis import extract_daytrade_indicator_context

    context = {
        "quote": {"last": "1,0875"},
        "indicator_values": {
            "success": True,
            "studies": [
                {
                    "name": "EMA 50/200",
                    "values": {"EMA 50": "1,0850", "EMA 200": "1,0800"},
                }
            ],
        },
        "smc_lines": {
            "success": True,
            "studies": [{"name": "Smart Money Concepts", "horizontal_levels": ["1,0900", "1,0830"]}],
        },
        "smc_labels": {
            "success": True,
            "studies": [{"name": "Smart Money Concepts", "labels": [{"text": "BOS", "price": "1,0860"}]}],
        },
        "smc_boxes": {
            "success": True,
            "studies": [{"name": "Smart Money Concepts", "zones": [{"high": "1,0890", "low": "1,0870"}]}],
        },
    }

    result = extract_daytrade_indicator_context(context)

    assert result["current_price"] == 1.0875
    assert result["ema"]["bias"] == "bullish"
    assert result["ema"]["ema_50"] == 1.085
    assert result["ema"]["ema_200"] == 1.08
    assert result["smc"]["nearest_levels"]["above"] == [1.09]
    assert result["smc"]["nearest_levels"]["below"] == [1.083]
    assert result["smc"]["recent_labels"][0]["text"] == "BOS"
    assert result["smc"]["nearest_zones"][0] == {"high": 1.089, "low": 1.087}


def test_daytrade_indicator_context_computes_ema_from_ohlcv():
    from app.ai_analysis import extract_daytrade_indicator_context

    bars = [{"close": float(index)} for index in range(1, 251)]
    result = extract_daytrade_indicator_context({"quote": {"last": 250.0}, "ohlcv_bars": {"bars": bars}})

    assert result["ema"]["computed_from_ohlcv"]["bar_count"] == 250
    assert result["ema"]["computed_from_ohlcv"]["ema_50"] is not None
    assert result["ema"]["computed_from_ohlcv"]["ema_200"] is not None
    assert result["ema"]["ema_50"] > result["ema"]["ema_200"]
    assert result["ema"]["bias"] == "bullish"


def test_daytrade_indicator_context_extracts_high_tf_snr():
    from app.ai_analysis import extract_daytrade_indicator_context

    h4_bars = [
        {"high": 1.085, "low": 1.080, "close": 1.083},
        {"high": 1.088, "low": 1.082, "close": 1.085},
        {"high": 1.095, "low": 1.084, "close": 1.089},
        {"high": 1.089, "low": 1.081, "close": 1.083},
        {"high": 1.086, "low": 1.079, "close": 1.082},
        {"high": 1.090, "low": 1.082, "close": 1.088},
        {"high": 1.092, "low": 1.083, "close": 1.087},
    ]

    result = extract_daytrade_indicator_context(
        {
            "quote": {"last": 1.0875},
            "high_tf_snr": {
                "enabled": True,
                "timeframes": [{"timeframe": "240", "success": True, "ohlcv": {"bars": h4_bars}}],
            },
        }
    )

    htf_snr = result["high_tf_snr"]
    assert htf_snr["enabled"] is True
    assert htf_snr["timeframes"][0]["timeframe"] == "240"
    assert htf_snr["nearest_supports"][0]["price"] <= 1.0875
    assert htf_snr["nearest_resistances"][0]["price"] >= 1.0875
    assert htf_snr["nearest_supports"][0]["timeframe"] == "240"


def test_fallback_wait_mentions_ema_smc_confluence():
    from app.ai_analysis import fallback_signal_message

    message = fallback_signal_message(
        {
            "state": {"symbol": "OANDA:EURUSD"},
            "quote": {"last": "1,0875"},
            "ohlcv_summary": {"change_pct": "0.1%", "range": "0,0040"},
            "indicator_values": {
                "success": True,
                "studies": [{"name": "EMA 50/200", "values": {"EMA 50": "1,0850", "EMA 200": "1,0800"}}],
            },
            "smc_labels": {
                "success": True,
                "studies": [{"name": "Smart Money Concepts", "labels": [{"text": "BOS", "price": "1,0860"}]}],
            },
            "high_tf_snr": {
                "enabled": True,
                "timeframes": [
                    {
                        "timeframe": "240",
                        "success": True,
                        "ohlcv": {
                            "bars": [
                                {"high": 1.085, "low": 1.080, "close": 1.083},
                                {"high": 1.088, "low": 1.082, "close": 1.085},
                                {"high": 1.095, "low": 1.084, "close": 1.089},
                                {"high": 1.089, "low": 1.081, "close": 1.083},
                                {"high": 1.086, "low": 1.079, "close": 1.082},
                                {"high": 1.090, "low": 1.082, "close": 1.088},
                                {"high": 1.092, "low": 1.083, "close": 1.087},
                            ]
                        },
                    }
                ],
            },
        },
        {"symbol": "OANDA:EURUSD", "action": "WAIT"},
    )

    assert "Bias: Bullish" in message
    assert "Tambahan data indikator" in message
    assert "EMA 50/200 bias bullish" in message
    assert "SMC recent BOS" in message
    assert "HTF SNR" in message


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
    assert "EMA 50/200" in prompt
    assert "Smart Money Concepts" in prompt
    assert "High-timeframe SNR" in prompt
    assert "liquidity sweep" in prompt
    assert "expected reward:risk is at least 1:1.5" in prompt
    assert "confidence is at least 70%" in prompt
