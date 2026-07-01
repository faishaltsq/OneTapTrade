from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "OneTapTrade"

    default_symbol: str = "XAUUSD"
    default_symbols: str = "OANDA:XAUUSD"
    default_timeframe: str = "60"
    tradingview_webhook_secret: Optional[str] = None

    tradingview_mcp_dir: str = "../tradingview-mcp"
    tradingview_mcp_node: str = "node"
    tradingview_mcp_timeout_seconds: int = 30
    tradingview_app_path: Optional[str] = None
    tradingview_cdp_port: int = 9222
    tradingview_smc_study_filter: str = "Smart Money"
    tradingview_ema_bar_count: int = 250
    auto_launch_tradingview_on_startup: bool = True
    capture_chart_on_signal: bool = True

    ai_api_key: Optional[str] = None
    ai_base_url: str = "https://api.deepseek.com"
    ai_model: str = "deepseek-v4-pro"
    ai_analysis_on_signal: bool = False
    ai_trading_style: str = "forex_daytrade"
    ai_min_trade_confidence: int = 70
    ai_min_rr: float = 1.5

    telegram_bot_token: Optional[str] = None
    telegram_allowed_chat_id: Optional[str] = None
    telegram_command_polling_enabled: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_allowed_chat_id)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ai_api_key)

    @property
    def symbols(self) -> list[str]:
        configured = [symbol.strip() for symbol in self.default_symbols.split(",") if symbol.strip()]
        return configured or [self.default_symbol]


settings = Settings()
