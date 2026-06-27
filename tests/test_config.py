import sys

sys.path.insert(0, r'C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade')


def test_strategy_mode_default_is_smc_ai(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("STRATEGY_MODE", raising=False)
    s = Settings(_env_file=None)
    assert s.strategy_mode == "SMC_AI"


def test_smc_probability_config_defaults():
    from app.config import Settings

    settings = Settings(_env_file=None)
    assert settings.min_signal_probability == 70
    assert settings.send_no_trade_alert is False
    assert settings.enable_ai_review is True


def test_tv_first_mode_defaults_enabled():
    from app.config import Settings

    settings = Settings(_env_file=None)
    assert settings.tv_first_mode is True


def test_risk_profile_config_has_style_and_timeframe_fields():
    from app.config import settings

    original = settings.risk_profile
    try:
        for profile in ("LOW", "MEDIUM", "HIGH"):
            settings.risk_profile = profile
            cfg = settings.risk_profile_config
            assert "style" in cfg
            assert "entry_tf" in cfg
            assert "hold" in cfg
            assert "sl_pips" in cfg
            assert "tp_pips" in cfg
            assert "min_confidence" in cfg
            assert "min_risk_reward" in cfg
    finally:
        settings.risk_profile = original


def test_low_profile_maps_to_swing():
    from app.config import settings

    original = settings.risk_profile
    try:
        settings.risk_profile = "LOW"
        assert settings.effective_style == "SWING"
        assert settings.effective_entry_tfs == ["H4", "D1"]
        assert settings.effective_hold_time == "days-weeks"
        assert settings.effective_min_confidence == 0.70
        assert settings.effective_min_risk_reward == 2.5
        assert settings.effective_sl_pip_range == (100, 500)
        assert settings.effective_tp_pip_range == (200, 1000)
    finally:
        settings.risk_profile = original


def test_medium_profile_maps_to_daytrade():
    from app.config import settings

    original = settings.risk_profile
    try:
        settings.risk_profile = "MEDIUM"
        assert settings.effective_style == "DAYTRADE"
        assert settings.effective_entry_tfs == ["H1", "H4"]
        assert settings.effective_hold_time == "hours-days"
        assert settings.effective_min_confidence == 0.55
        assert settings.effective_min_risk_reward == 1.8
        assert settings.effective_sl_pip_range == (50, 150)
        assert settings.effective_tp_pip_range == (75, 300)
    finally:
        settings.risk_profile = original


def test_high_profile_maps_to_scalping():
    from app.config import settings

    original = settings.risk_profile
    try:
        settings.risk_profile = "HIGH"
        assert settings.effective_style == "SCALPING"
        assert settings.effective_entry_tfs == ["M5", "M15"]
        assert settings.effective_hold_time == "minutes-hours"
        assert settings.effective_min_confidence == 0.40
        assert settings.effective_min_risk_reward == 1.2
        assert settings.effective_sl_pip_range == (15, 50)
        assert settings.effective_tp_pip_range == (15, 75)
    finally:
        settings.risk_profile = original


def test_effective_loop_interval_auto_from_profile():
    from app.config import settings

    original_profile = settings.risk_profile
    original_interval = settings.trading_loop_interval_seconds
    try:
        settings.trading_loop_interval_seconds = 0
        settings.risk_profile = "LOW"
        assert settings.effective_loop_interval == 3600
        settings.risk_profile = "MEDIUM"
        assert settings.effective_loop_interval == 900
        settings.risk_profile = "HIGH"
        assert settings.effective_loop_interval == 300
    finally:
        settings.risk_profile = original_profile
        settings.trading_loop_interval_seconds = original_interval


def test_effective_loop_interval_env_override_takes_precedence():
    from app.config import settings

    original_profile = settings.risk_profile
    original_interval = settings.trading_loop_interval_seconds
    try:
        settings.risk_profile = "HIGH"
        settings.trading_loop_interval_seconds = 120
        assert settings.effective_loop_interval == 120
    finally:
        settings.risk_profile = original_profile
        settings.trading_loop_interval_seconds = original_interval
