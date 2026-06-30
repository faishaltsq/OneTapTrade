from typing import Protocol

from app.config import settings


class MarketDataProvider(Protocol):
    def get_symbol_info(self, symbol: str) -> dict:
        ...

    def get_latest_price(self, symbol: str) -> dict:
        ...

    def get_candles(self, symbol: str, timeframe: str, count: int):
        ...


def neutral_account_context() -> dict:
    return {
        "balance": None,
        "equity": None,
        "daily_pnl_percent": None,
        "daily_drawdown_percent": 0.0,
        "open_positions_count": 0,
        "has_open_position": False,
    }


def get_market_data_provider() -> MarketDataProvider:
    source = settings.market_data_source.upper()
    if source == "TRADINGVIEW":
        from app.market_data.tradingview_provider import TradingViewMarketDataProvider

        return TradingViewMarketDataProvider()
    raise ValueError(f"Unsupported market data source: {settings.market_data_source}")
