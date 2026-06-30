# OneTapTrade - AI TradingView Signal Bot

AI-assisted TradingView daytrade signal bot with DeepSeek analysis, Telegram controls, Supabase audit logging, Smart Money Concepts context, and strict signal-only safety gates.

> Trading risk warning: this project is for education and research. Financial markets can cause substantial loss. Default mode is signal-only and execution is disabled in TradingView mode.

## What It Does

- Reads chart data through TradingView MCP.
- Builds multi-timeframe daytrade payloads using D1, H4, H1, M15, and M5 context.
- Sends structured market context to DeepSeek and expects strict JSON trading decisions.
- Applies signal quality checks before alerts.
- Runs signal-only by default; execution is disabled in TradingView mode.
- Sends Telegram dashboards, chart screenshots, settings, and control buttons.
- Broadcasts approved BUY/SELL setup signals to a Telegram channel via separate signal bot.
- Logs market snapshots, AI decisions, risk checks, trades, events, and Telegram commands to Supabase.
- Uses TradingView-format symbols such as `OANDA:XAUUSD`.

## Current Strategy

- D1 major trend is a hard filter.
- `D1_BULLISH` allows BUY only.
- `D1_BEARISH` allows SELL only.
- `D1_RANGING` blocks BUY/SELL unless breakout and retest are confirmed.
- H1 is primary daytrade bias after D1 allows direction.
- M15 is setup timeframe and M5 is entry trigger context.
- SMC context includes order blocks, fair value gaps, CHoCH, swing levels, and liquidity levels.
- Position and account checks are neutral in TradingView signal-only mode.
- Spread is `0` because TradingView candles do not provide broker bid/ask spread.
- AI owns SL/TP geometry, but BUY/SELL decisions must provide stop loss and take profit.
- Strategy mode (SMC+AI or AI-only) controls how AI processes market data. See Strategy Modes below.
- Trading style is bound to risk profile: LOW=Swing, MEDIUM=Daytrade, HIGH=Scalping. See Trading Style Profiles below.
- Noise filter gates run before AI call to skip bad market conditions. See Noise Filter below.

## Strategy Modes

Two thinking modes, toggled via Telegram:

| Mode | Description |
| --- | --- |
| `SMC_AI` | SMC + AI: AI uses Smart Money Concepts analysis (order blocks, FVG, CHoCH, liquidity) as primary methodology. Default. |
| `AI_ONLY` | AI Only: AI receives all data but decides independently from first principles. No fixed methodology priority. |

Toggle via Telegram main menu or settings keyboard. Persisted to Supabase `bot_settings.strategy_mode`.

## Trading Style Profiles

Risk profile binds to a trading style:

| Profile | Style | Entry TF | Hold Time | Min Conf | Min R:R | SL Range | TP Range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `LOW` | Swing | H4/D1 | days-weeks | 70% | 2.5 | 100-500 pips | 200-1000 pips |
| `MEDIUM` | Daytrade | H1/H4 | hours-days | 55% | 1.8 | 50-150 pips | 75-300 pips |
| `HIGH` | Scalping | M5/M15 | minutes-hours | 40% | 1.2 | 15-50 pips | 15-75 pips |

Style affects:
- AI system prompt (timeframe focus, hold time guidance, SL/TP ranges)
- Noise filter strictness (LOW strict, MEDIUM lenient, HIGH very lenient)
- Risk manager thresholds (min confidence, min R:R)

## Noise Filter

Pre-AI gate skips DeepSeek API call when market conditions are noisy. Three profile-aware gates:

1. **Multi-TF alignment**: SWING strict (D1+H4 aligned), MEDIUM lenient (D1 clear + H1 not strongly opposite), HIGH skips.
2. **ATR percentile**: SWING 20-85, MEDIUM 15-90, HIGH 10-95.
3. **Volume confirmation**: SWING >1.2x avg, MEDIUM >0.8x avg, HIGH >0.5x avg.

When noise filter blocks, bot returns HOLD with reason, saves to DB, sends Telegram update. No API call made.

## Architecture

```text
TradingView MCP
    |
    v
FastAPI backend + trading loop
    |
    +--> Market analysis: D1/H4/H1/M15/M5, SMC, trend, orderflow proxy
    +--> DeepSeek AI decision engine
    +--> Signal quality checks
    +--> Telegram control bot
    +--> Supabase logging and settings
```

## Tech Stack

- Python 3.10+
- FastAPI and Uvicorn
- TradingView MCP
- DeepSeek API through OpenAI-compatible client
- python-telegram-bot
- Supabase Python client
- Pandas and NumPy
- Pytest

## Trading Modes

| Mode | Signals | Telegram Approval | Auto Execute | Live Money |
| --- | --- | --- | --- | --- |
| `SIGNAL_ONLY` | Yes | No | No | No |
| `SEMI_AUTO` | Yes | Informational only in TradingView mode | No | No |
| `AUTO_DEMO` | Yes | No | No in TradingView mode | No |
| `LIVE_AUTO` | Yes | No | No in TradingView mode | No |

## Repository Layout

```text
.
├── app/
│   ├── ai_engine/          # DeepSeek prompts, schema, parsing, validation
│   ├── analysis/           # Indicators, market structure, SMC, trend payloads
│   ├── api/                # FastAPI routes
│   ├── database/           # Supabase client and repositories
│   ├── market_data/        # TradingView provider boundary
│   ├── mt5_connector/      # Legacy MT5 modules, inactive in TradingView mode
│   ├── risk/               # Risk manager, position sizing, trade validation
│   ├── services/           # Trading loop, breakeven, position state sync
│   └── telegram_bot/       # Commands, callbacks, message templates, bot lifecycle
├── docs/superpowers/       # Design notes and implementation plans
├── supabase/schema.sql     # Database schema
├── tests/                  # Pytest suite
├── .env.example            # Safe environment template
├── requirements.txt
├── run.py
└── README.md
```

## Prerequisites

- Python 3.10 or newer. Current development used Python 3.13.
- TradingView MCP CLI available as `tv` or configured through `TV_MCP_PATH`.
- DeepSeek API key.
- Telegram bot token from BotFather.
- Supabase project.

## Quick Start

Clone repository:

```powershell
git clone https://github.com/faishaltsq/OneTapTrade.git
cd OneTapTrade
```

Create virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create environment file:

```powershell
copy .env.example .env
```

Fill `.env` with your own credentials. Never commit `.env`.

Create Supabase tables:

```powershell
psql "YOUR_SUPABASE_DATABASE_URL" -f supabase/schema.sql
```

Or paste `supabase/schema.sql` into Supabase SQL Editor.

Start application:

```powershell
python run.py
```

API runs on `http://localhost:8000`.

## Environment Variables

| Variable | Description | Example |
| --- | --- | --- |
| `APP_ENV` | Runtime environment label | `development` |
| `BOT_MODE` | Initial trading mode | `SIGNAL_ONLY` |
| `MARKET_DATA_SOURCE` | Market data provider | `TRADINGVIEW` |
| `TV_ENABLED` | Enable TradingView provider | `true` |
| `TV_MCP_PATH` | TradingView MCP CLI command, JS file, or repo folder | `tv` |
| `TV_DEBUG_PORT` | TradingView debug port | `9222` |
| `DEEPSEEK_API_KEY` | DeepSeek API key | keep secret |
| `DEEPSEEK_BASE_URL` | DeepSeek API base URL | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | DeepSeek model | `deepseek-chat` |
| `TELEGRAM_BOT_TOKEN` | BotFather token | keep secret |
| `TELEGRAM_ALLOWED_CHAT_ID` | Allowed Telegram chat ID | your chat ID |
| `SIGNAL_BOT_TOKEN` | Separate bot token for channel signal broadcasts | keep secret |
| `SIGNAL_CHANNEL_ID` | Telegram channel/chat ID for BUY/SELL setup broadcasts | `@your_channel` |
| `SUPABASE_URL` | Supabase project URL | keep project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | keep secret |
| `DEFAULT_SYMBOL` | Single default TradingView symbol | `OANDA:XAUUSD` |
| `DEFAULT_SYMBOLS` | Comma-separated TradingView symbols for loop | `OANDA:XAUUSD,OANDA:EURUSD,OANDA:GBPUSD` |
| `RISK_PROFILE` | Risk profile | `LOW`, `MEDIUM`, or `HIGH` |
| `STRATEGY_MODE` | Strategy thinking mode (`SMC_AI` or `AI_ONLY`) | `SMC_AI` |
| `RISK_PER_TRADE_PERCENT` | Account risk per trade | `0.5` |
| `MAX_DAILY_DRAWDOWN_PERCENT` | Daily drawdown stop | `2.0` |
| `MAX_OPEN_POSITIONS` | Global position cap unless same-side add-on | `1` |
| `MIN_CONFIDENCE` | Legacy/base confidence config | `0.65` |
| `MIN_RISK_REWARD` | Legacy/base risk reward config | `1.5` |
| `MAX_SPREAD_POINTS` | Legacy spread config, not used as decision blocker | `35` |
| `TRADING_LOOP_INTERVAL_SECONDS` | Loop interval | `900` |
| `DAYTRADE_TIMEFRAMES` | Analysis timeframes | `D1,H4,H1,M15,M5` |

## TradingView Symbol Notes

Set symbols in TradingView format:

```env
DEFAULT_SYMBOL=OANDA:XAUUSD
DEFAULT_SYMBOLS=OANDA:XAUUSD,OANDA:EURUSD,OANDA:GBPUSD,OANDA:GBPJPY,NASDAQ:NDX,SP:SPX,BITSTAMP:BTCUSD
```

Broker suffixes such as `.c`, `.m`, and `.std` are not used by default.

## Signal-Only Safety

- TradingView mode never executes orders.
- Telegram approve, close-all, position, and auto-execution controls are hidden or disabled.
- Keep `BOT_MODE=SIGNAL_ONLY` for default operation.
- Treat all BUY/SELL output as research signals, not financial advice.

## Signal Quality Gates

Every BUY/SELL signal must pass these checks:

- Decision is not HOLD.
- Confidence meets active profile threshold.
- D1 major trend allows the direction.
- D1 ranging has breakout and retest confirmation.
- Stop loss is provided.
- Take profit is provided.
- Trade parameters are valid for BUY/SELL price logic.
- AI explicitly allows the signal.

AI controls SL/TP placement. Risk manager does not reject because SL is wide, SL is tight, or R:R is below fixed profile values.

## Position Sizing

Position sizing is inactive in TradingView signal-only mode. SL/TP and R:R are still included in signal output when AI returns them.

## Telegram Bot

Main commands:

| Command | Action |
| --- | --- |
| `/start` | Show welcome and controls |
| `/menu` | Open inline control menu |
| `/status` | Show bot status and TradingView source |
| `/settings` | Show current settings and risk controls |
| `/pause` | Pause trading loop |
| `/resume` | Resume trading loop |
| `/mode_signal` | Switch to signal-only mode |
| `/last_signal` | Show latest AI decision |

Inline menu supports:

- Pause/resume.
- Risk profile controls: Low, Medium, High.
- Symbol controls: all pairs or next pair.
- Manual signal generation.
- Strategy mode toggle: SMC+AI or AI Only.

In TradingView mode, execution controls are hidden or disabled: positions, close-all, approve/reject, and Signal/Semi/Auto mode buttons.

Approved BUY/SELL setups include a TradingView chart screenshot when MCP screenshot capture is available. If the screenshot fails, Telegram falls back to a text signal. HOLD updates are not broadcast to the signal channel.

## API Endpoints

Health and status:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Health check |
| `GET` | `/status` | Full bot status |

Controls:

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/pause` | Pause trading |
| `POST` | `/resume` | Resume trading |
| `POST` | `/mode` | Change bot mode |
| `POST` | `/close-all` | Disabled in TradingView mode |

Signals and trades:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/last-signal` | Latest AI decision |
| `POST` | `/generate-signal` | Trigger manual signal |
| `POST` | `/approve/{decision_id}` | Disabled in TradingView mode |
| `POST` | `/reject/{decision_id}` | Reject pending decision |
| `GET` | `/trades` | Trade history |
| `GET` | `/trades/{trade_id}` | Trade detail |

Settings:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/settings` | Current bot settings |
| `POST` | `/settings` | Update settings |

## Supabase

Run `supabase/schema.sql` before using persistence. Tables:

- `bot_settings`
- `market_snapshots`
- `ai_decisions`
- `risk_checks`
- `trades`
- `telegram_commands`
- `bot_events`

If Supabase schema cache misses `risk_profile`, run:

```sql
ALTER TABLE bot_settings ADD COLUMN IF NOT EXISTS risk_profile TEXT NOT NULL DEFAULT 'MEDIUM';
NOTIFY pgrst, 'reload schema';
```

## Running Tests

Run all tests:

```powershell
pytest
```

Run targeted tests:

```powershell
pytest tests/test_risk_manager.py -v
pytest tests/test_trading_loop.py -v
pytest tests/test_telegram_bot.py -v
```

Latest verified result before publishing:

```text
179 passed, 2 warnings
```

Warnings are Supabase client deprecation warnings for timeout/verify configuration.

## Development Notes

- `.env`, logs, and caches are intentionally ignored by git.
- Do not commit credentials, account numbers, Telegram tokens, or Supabase service role keys.
- `logs/` can contain full Telegram request URLs with bot tokens. Keep it ignored.
- Use tests before behavior changes. Signal and risk behavior should be covered by pytest.

## Troubleshooting

TradingView MCP unavailable:

- Verify `TV_ENABLED=true`.
- Verify `TV_MCP_PATH` points to `tv`, `src/cli/index.js`, or the cloned `tradingview-mcp` repo folder.
- Check logs for the exact MCP command/output error.

Symbol data unavailable:

- Check TradingView symbol format, for example `OANDA:XAUUSD`.
- Confirm the exchange prefix exists on TradingView.
- Update `DEFAULT_SYMBOLS`.

No signals generated:

- Check `TRADING_LOOP_INTERVAL_SECONDS`.
- Check noise filter logs.
- Verify DeepSeek credentials.

Execution disabled:

- Expected in TradingView mode. This project sends signals only.

## Security

- Rotate any token accidentally written to `.env.example` or logs.
- Keep Supabase service role key server-side only.
- Restrict Telegram access with `TELEGRAM_ALLOWED_CHAT_ID`.
- Treat DeepSeek, Telegram, Supabase, and TradingView credentials as high-risk secrets.

## Disclaimer

This software is not financial advice. No profit is guaranteed. You are responsible for all decisions, settings, account access, and losses.
