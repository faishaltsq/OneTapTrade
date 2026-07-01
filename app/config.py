from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "OneTapTrade"

    default_symbol: str = "XAUUSD"
    default_symbols: str = "OANDA:XAUUSD,OANDA:EURUSD,OANDA:GBPUSD,OANDA:USDJPY,OANDA:GBPJPY,OANDA:NZDUSD,TVC:USOIL,OANDA:NAS100USD,COINBASE:BTCUSD,COINBASE:ETHUSD,COINBASE:SOLUSD"
    default_timeframe: str = "60"
    tradingview_webhook_secret: Optional[str] = None

    tradingview_mcp_dir: str = "../tradingview-mcp"
    tradingview_mcp_node: str = "node"
    tradingview_mcp_timeout_seconds: int = 30
    tradingview_app_path: Optional[str] = None
    tradingview_cdp_port: int = 9222
    tradingview_smc_study_filter: str = "Smart Money"
    tradingview_ema_bar_count: int = 250
    tradingview_snr_timeframes: str = "240,D"
    tradingview_snr_bar_count: int = 200
    auto_launch_tradingview_on_startup: bool = True
    capture_chart_on_signal: bool = True
    prediction_drawing_enabled: bool = True
    prediction_drawing_bars_ahead: int = 24

    ai_api_key: Optional[str] = None
    ai_base_url: str = "https://api.deepseek.com"
    ai_model: str = "deepseek-v4-pro"
    ai_analysis_on_signal: bool = False
    ai_trading_style: str = "daytrade_scanner"
    ai_min_trade_confidence: int = 70
    ai_min_rr: float = 1.5

    auto_signal_enabled: bool = False
    auto_signal_interval_minutes: int = 15
    auto_signal_timeframe: str = ""
    auto_signal_min_confidence: int = 70
    auto_signal_min_rr: float = 1.5
    auto_signal_send_wait: bool = False
    auto_signal_send_no_setup_summary: bool = True
    auto_signal_require_screenshot: bool = True
    auto_signal_cooldown_minutes: int = 60
    auto_signal_max_broadcast_per_scan: int = 3
    day_trade_only: bool = True

    telegram_bot_token: Optional[str] = None
    telegram_allowed_chat_id: Optional[str] = None
    telegram_admin_chat_id: Optional[str] = None
    telegram_channel_id: Optional[str] = None
    telegram_command_polling_enabled: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_allowed_chat_id)

    @property
    def admin_chat_id(self) -> str | None:
        return self.telegram_admin_chat_id or self.telegram_allowed_chat_id

    @property
    def channel_enabled(self) -> bool:
        return bool(self.telegram_channel_id and self.telegram_bot_token)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ai_api_key)

    @property
    def symbols(self) -> list[str]:
        configured = [symbol.strip() for symbol in self.default_symbols.split(",") if symbol.strip()]
        return configured or [self.default_symbol]

    @property
    def snr_timeframes(self) -> list[str]:
        return [timeframe.strip() for timeframe in self.tradingview_snr_timeframes.split(",") if timeframe.strip()]


settings = Settings()
