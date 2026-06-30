from pathlib import Path


def test_launch_tradingview_when_enabled(monkeypatch, tmp_path):
    from app.config import settings
    from app.market_data.tradingview_launcher import launch_tradingview_if_configured

    exe = tmp_path / "TradingView.exe"
    exe.write_text("", encoding="utf-8")
    calls = []

    original_enabled = settings.tv_launch_on_startup
    original_path = settings.tv_exe_path
    original_port = settings.tv_debug_port
    try:
        settings.tv_launch_on_startup = True
        settings.tv_exe_path = str(exe)
        settings.tv_debug_port = 9333

        result = launch_tradingview_if_configured(starter=lambda **kwargs: calls.append(kwargs), sleeper=lambda seconds: None)

        assert result == {"launched": True, "path": str(exe), "port": 9333}
        assert calls == [{"file_path": str(exe), "arguments": ["--remote-debugging-port=9333"]}]
    finally:
        settings.tv_launch_on_startup = original_enabled
        settings.tv_exe_path = original_path
        settings.tv_debug_port = original_port


def test_launch_tradingview_skips_when_disabled():
    from app.config import settings
    from app.market_data.tradingview_launcher import launch_tradingview_if_configured

    original_enabled = settings.tv_launch_on_startup
    try:
        settings.tv_launch_on_startup = False
        result = launch_tradingview_if_configured(starter=lambda **kwargs: (_ for _ in ()).throw(AssertionError("called")))
        assert result == {"launched": False, "reason": "TV_LAUNCH_ON_STARTUP disabled"}
    finally:
        settings.tv_launch_on_startup = original_enabled


def test_launch_tradingview_reports_missing_path(tmp_path):
    from app.config import settings
    from app.market_data.tradingview_launcher import launch_tradingview_if_configured

    missing = tmp_path / "missing.exe"
    original_enabled = settings.tv_launch_on_startup
    original_path = settings.tv_exe_path
    try:
        settings.tv_launch_on_startup = True
        settings.tv_exe_path = str(missing)
        result = launch_tradingview_if_configured(starter=lambda **kwargs: None)
        assert result == {"launched": False, "reason": f"TV_EXE_PATH not found: {missing}"}
    finally:
        settings.tv_launch_on_startup = original_enabled
        settings.tv_exe_path = original_path
