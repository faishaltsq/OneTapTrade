# Progress

## 2026-06-30

- Converted default runtime to TradingView-driven `SIGNAL_ONLY` mode.
- Disabled MT5 startup and order execution for TradingView mode.
- Added TradingView MCP market-data provider and desktop launcher support.
- Added TradingView symbol defaults such as `OANDA:XAUUSD`.
- Added multi-timeframe daytrade payload support for D1, H4, H1, M15, and M5.
- Kept strategy modes: `SMC_AI` and `AI_ONLY`.
- Kept risk profiles: LOW swing, MEDIUM daytrade, HIGH scalping.
- Simplified Telegram menu for TradingView signal-only usage.
- Added TradingView chart screenshot capture for approved BUY/SELL setup signals.
- Added channel broadcasts using `SIGNAL_BOT_TOKEN` and `SIGNAL_CHANNEL_ID`.
- HOLD signals are not broadcast to the public signal channel.
- Added text fallbacks when screenshot capture or photo send fails.
- Updated `.env.example` with signal-channel env keys.
- Verified TradingView MCP connection and screenshot smoke test.
- Verified test suite: `179 passed, 2 warnings`.

## Next

- Rotate any credentials shared outside `.env`.
- Fill local `.env` with `SIGNAL_BOT_TOKEN` and `SIGNAL_CHANNEL_ID`.
- Start app with TradingView Desktop remote debugging enabled.
- Send one manual BUY/SELL setup in staging/private channel before public use.
