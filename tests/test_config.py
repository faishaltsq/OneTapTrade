from app.config import Settings


def test_settings_defaults_are_signal_only():
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.app_name == "OneTapTrade"
    assert settings.default_symbol == "XAUUSD"
    assert settings.symbols
    assert "OANDA:GBPJPY" in settings.symbols
    assert "OANDA:NZDUSD" in settings.symbols
    assert "TVC:USOIL" in settings.symbols
    assert "OANDA:NAS100USD" in settings.symbols
    assert "COINBASE:BTCUSD" in settings.symbols
    assert "COINBASE:ETHUSD" in settings.symbols
    assert "COINBASE:SOLUSD" in settings.symbols
    assert settings.tradingview_smc_study_filter == "Smart Money"
    assert settings.tradingview_ema_bar_count == 250
    assert settings.tradingview_snr_timeframes == "240,D"
    assert settings.tradingview_snr_bar_count == 200
    assert settings.snr_timeframes == ["240", "D"]
    assert settings.capture_chart_on_signal is True
    assert settings.prediction_drawing_enabled is True
    assert settings.prediction_drawing_bars_ahead == 24
    assert settings.ai_base_url == "https://api.deepseek.com"
    assert settings.ai_model == "deepseek-v4-pro"
    assert settings.ai_trading_style == "forex_daytrade"
    assert settings.ai_min_trade_confidence == 70
    assert settings.ai_min_rr == 1.5
    assert settings.auto_signal_enabled is False
    assert settings.auto_signal_interval_minutes == 15
    assert settings.auto_signal_timeframe == ""
    assert settings.auto_signal_min_confidence == 70
    assert settings.auto_signal_send_wait is False
    assert settings.auto_signal_cooldown_minutes == 60
    assert settings.telegram_enabled is False
    assert settings.ai_enabled is False


def test_symbols_parse_default_symbols():
    from app.config import Settings

    settings = Settings(_env_file=None, default_symbols="OANDA:XAUUSD, OANDA:EURUSD")

    assert settings.symbols == ["OANDA:XAUUSD", "OANDA:EURUSD"]


def test_telegram_enabled_requires_token_and_chat_id():
    settings = Settings(
        _env_file=None,
        telegram_bot_token="token",
        telegram_allowed_chat_id="123",
    )

    assert settings.telegram_enabled is True
