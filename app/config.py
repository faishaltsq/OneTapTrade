from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import Any, Optional


class Settings(BaseSettings):
    app_env: str = "development"
    bot_mode: str = "SIGNAL_ONLY"
    live_trading_enabled: bool = False

    mt5_login: Optional[int] = None
    mt5_password: Optional[str] = None
    mt5_server: Optional[str] = None
    mt5_path: Optional[str] = None

    deepseek_api_key: Optional[str] = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_fallback_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: int = 120

    telegram_bot_token: Optional[str] = None
    telegram_allowed_chat_id: Optional[str] = None

    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None

    default_symbol: str = "XAUUSD"
    default_symbols: str = ""
    risk_profile: str = "MEDIUM"
    strategy_mode: str = "SMC_AI"
    min_signal_probability: int = 70
    send_no_trade_alert: bool = False
    enable_ai_review: bool = True
    risk_per_trade_percent: float = 0.5
    max_daily_drawdown_percent: float = 2.0
    max_open_positions: int = 1
    max_positions_per_symbol: int = 5
    min_confidence: float = 0.65
    min_risk_reward: float = 1.5
    max_spread_points: int = 35
    trading_loop_interval_seconds: int = 0
    auto_signal_enabled: bool = False

    tv_enabled: bool = True
    tv_first_mode: bool = True
    tv_launch_on_startup: bool = True
    tv_debug_port: int = 9222
    tv_health_check_interval: int = 30
    tv_mcp_max_retries: int = 3
    tv_mcp_path: str = "tradingview-mcp"
    tv_exe_path: Optional[str] = None
    signal_bot_token: Optional[str] = None
    signal_channel_id: Optional[str] = None
    signal_channel_id: Optional[str] = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("mt5_login", mode="before")
    @classmethod
    def coerce_mt5_login(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        return int(v)

    @property
    def risk_profile_config(self) -> dict:
        profiles = {
            "LOW": {
                "style": "SWING",
                "entry_tf": ["H4", "D1"],
                "hold": "days-weeks",
                "loop_interval": 3600,
                "min_confidence": 0.70,
                "min_risk_reward": 2.5,
                "sl_pips": (100, 500),
                "tp_pips": (200, 1000),
            },
            "MEDIUM": {
                "style": "DAYTRADE",
                "entry_tf": ["H1", "H4"],
                "hold": "hours-days",
                "loop_interval": 900,
                "min_confidence": 0.55,
                "min_risk_reward": 1.8,
                "sl_pips": (50, 150),
                "tp_pips": (75, 300),
            },
            "HIGH": {
                "style": "SCALPING",
                "entry_tf": ["M5", "M15"],
                "hold": "minutes-hours",
                "loop_interval": 300,
                "min_confidence": 0.40,
                "min_risk_reward": 1.2,
                "sl_pips": (15, 50),
                "tp_pips": (15, 75),
            },
        }
        return profiles.get(self.risk_profile, profiles["MEDIUM"])

    @property
    def symbols(self) -> list:
        if self.default_symbols:
            return [s.strip() for s in self.default_symbols.split(",") if s.strip()]
        return [self.default_symbol]

    @property
    def is_live_allowed(self) -> bool:
        return self.live_trading_enabled

    @property
    def is_signal_only(self) -> bool:
        return self.bot_mode == "SIGNAL_ONLY"

    @property
    def is_semi_auto(self) -> bool:
        return self.bot_mode == "SEMI_AUTO"

    @property
    def is_auto_demo(self) -> bool:
        return self.bot_mode == "AUTO_DEMO"

    @property
    def is_live_auto(self) -> bool:
        return self.bot_mode == "LIVE_AUTO"

    @property
    def effective_min_confidence(self) -> float:
        return self.risk_profile_config["min_confidence"]

    @property
    def effective_min_risk_reward(self) -> float:
        return self.risk_profile_config["min_risk_reward"]

    @property
    def effective_min_sl_pips(self) -> int:
        return self.risk_profile_config["sl_pips"][0]

    @property
    def effective_max_sl_pips(self) -> int:
        return self.risk_profile_config["sl_pips"][1]

    @property
    def effective_style(self) -> str:
        return self.risk_profile_config["style"]

    @property
    def effective_entry_tfs(self) -> list[str]:
        return self.risk_profile_config["entry_tf"]

    @property
    def effective_hold_time(self) -> str:
        return self.risk_profile_config["hold"]

    @property
    def effective_sl_pip_range(self) -> tuple[int, int]:
        return self.risk_profile_config["sl_pips"]

    @property
    def effective_tp_pip_range(self) -> tuple[int, int]:
        return self.risk_profile_config["tp_pips"]

    @property
    def effective_loop_interval(self) -> int:
        if self.trading_loop_interval_seconds > 0:
            return self.trading_loop_interval_seconds
        return self.risk_profile_config["loop_interval"]

    @property
    def tv_mcp_server_path(self) -> str:
        import os
        return os.path.join(self.tv_mcp_path, "src", "server.js")

    @property
    def tv_mcp_node_cmd(self) -> str:
        return "node"


settings = Settings()
