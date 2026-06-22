# OneTapTrade - AI Trading Executor

AI-assisted MetaTrader 5 scalping executor with DeepSeek analysis, Telegram controls, Supabase audit logging, Smart Money Concepts context, and strict safety gates.

> Trading risk warning: this project is for education, research, and demo trading first. Financial markets can cause substantial loss. Keep `LIVE_TRADING_ENABLED=false` unless you understand every risk and have tested on demo.

## What It Does

- Connects to MetaTrader 5 and reads live market data.
- Builds multi-timeframe market payloads using D1, H4, H1, and M5 candles.
- Sends structured market context to DeepSeek and expects strict JSON trading decisions.
- Applies risk-manager checks before any execution.
- Supports Signal Only, Semi Auto, Demo Auto, and Live Auto modes.
- Sends Telegram dashboards, approvals, positions, settings, and control buttons.
- Logs market snapshots, AI decisions, risk checks, trades, events, and Telegram commands to Supabase.
- Syncs open MT5 positions on startup so restart does not forget live exposure.
- Moves stop loss to breakeven after price reaches 30% progress toward TP.

## Current Strategy

- D1 major trend is a hard filter.
- `D1_BULLISH` allows BUY only.
- `D1_BEARISH` allows SELL only.
- `D1_RANGING` blocks BUY/SELL unless breakout and retest are confirmed.
- H1 is primary execution direction context after D1 allows direction.
- M5 is entry trigger timeframe.
- SMC context includes order blocks, fair value gaps, CHoCH, swing levels, and liquidity levels.
- Same-direction add-ons are allowed when an open position exists on the same symbol.
- Opposite-direction trades are blocked while a live position exists on the same symbol.
- Spread is ignored for trade decisions.
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
- Trading loop interval (LOW=3600s, MEDIUM=900s, HIGH=300s; set `TRADING_LOOP_INTERVAL_SECONDS=0` for auto or non-zero to override)

## Noise Filter

Pre-AI gate skips DeepSeek API call when market conditions are noisy. Three profile-aware gates:

1. **Multi-TF alignment**: SWING strict (D1+H4 aligned), MEDIUM lenient (D1 clear + H1 not strongly opposite), HIGH skips.
2. **ATR percentile**: SWING 20-85, MEDIUM 15-90, HIGH 10-95.
3. **Volume confirmation**: SWING >1.2x avg, MEDIUM >0.8x avg, HIGH >0.5x avg.

When noise filter blocks, bot returns HOLD with reason, saves to DB, sends Telegram update. No API call made.

## Architecture

```text
MT5 Terminal
    |
    v
FastAPI backend + trading loop
    |
    +--> Market analysis: D1/H4/H1/M5, SMC, trend, orderflow proxy
    +--> DeepSeek AI decision engine
    +--> Risk manager and position sizing
    +--> MT5 order execution
    +--> Telegram control bot
    +--> Supabase logging and settings
```

## Tech Stack

- Python 3.10+
- FastAPI and Uvicorn
- MetaTrader5 Python package
- DeepSeek API through OpenAI-compatible client
- python-telegram-bot
- Supabase Python client
- Pandas and NumPy
- Pytest

## Trading Modes

| Mode | Signals | Telegram Approval | Auto Execute | Live Money |
| --- | --- | --- | --- | --- |
| `SIGNAL_ONLY` | Yes | No | No | No |
| `SEMI_AUTO` | Yes | Required | After approval | Depends on account and live flag |
| `AUTO_DEMO` | Yes | No | Yes | No, intended for demo |
| `LIVE_AUTO` | Yes | No | Yes | Yes, only if `LIVE_TRADING_ENABLED=true` |

## Repository Layout

```text
.
├── app/
│   ├── ai_engine/          # DeepSeek prompts, schema, parsing, validation
│   ├── analysis/           # Indicators, market structure, SMC, trend payloads
│   ├── api/                # FastAPI routes
│   ├── database/           # Supabase client and repositories
│   ├── mt5_connector/      # MT5 connection, data, account, positions, execution
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

- Windows machine with MetaTrader 5 installed.
- MT5 demo account logged in and broker symbols visible in Market Watch.
- Python 3.10 or newer. Current development used Python 3.13.
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
| `LIVE_TRADING_ENABLED` | Hard live trading kill switch | `false` |
| `MT5_LOGIN` | MT5 account number | `12345678` |
| `MT5_PASSWORD` | MT5 password | keep secret |
| `MT5_SERVER` | Broker server name | `JustMarkets-Demo3` |
| `MT5_PATH` | Optional path to `terminal64.exe` | `C:\Program Files\MetaTrader 5\terminal64.exe` |
| `DEEPSEEK_API_KEY` | DeepSeek API key | keep secret |
| `DEEPSEEK_BASE_URL` | DeepSeek API base URL | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | DeepSeek model | `deepseek-chat` |
| `TELEGRAM_BOT_TOKEN` | BotFather token | keep secret |
| `TELEGRAM_ALLOWED_CHAT_ID` | Allowed Telegram chat ID | your chat ID |
| `SUPABASE_URL` | Supabase project URL | keep project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | keep secret |
| `DEFAULT_SYMBOL` | Single default symbol | `XAUUSD.c` |
| `DEFAULT_SYMBOLS` | Comma-separated symbols for loop | `XAUUSD.c,EURUSD.c,GBPJPY.c,GBPUSD.c` |
| `RISK_PROFILE` | Risk profile | `LOW`, `MEDIUM`, or `HIGH` |
| `STRATEGY_MODE` | Strategy thinking mode (`SMC_AI` or `AI_ONLY`) | `SMC_AI` |
| `RISK_PER_TRADE_PERCENT` | Account risk per trade | `0.5` |
| `MAX_DAILY_DRAWDOWN_PERCENT` | Daily drawdown stop | `2.0` |
| `MAX_OPEN_POSITIONS` | Global position cap unless same-side add-on | `1` |
| `MIN_CONFIDENCE` | Legacy/base confidence config | `0.65` |
| `MIN_RISK_REWARD` | Legacy/base risk reward config | `1.5` |
| `MAX_SPREAD_POINTS` | Legacy spread config, not used as decision blocker | `35` |
| `TRADING_LOOP_INTERVAL_SECONDS` | Loop interval (`0` = auto from profile: LOW=3600, MEDIUM=900, HIGH=300) | `0` |

## Broker Symbol Notes

Set symbols exactly as your broker exposes them. JustMarkets demo commonly uses `.c` suffixes:

```env
DEFAULT_SYMBOL=XAUUSD.c
DEFAULT_SYMBOLS=XAUUSD.c,EURUSD.c,GBPJPY.c,GBPUSD.c
```

Wrong suffixes cause symbol selection failures.

## MT5 Safety Checklist

- Use demo account first.
- Confirm MT5 terminal is running.
- Confirm account is logged in.
- Enable Algo Trading in MT5 only when you intend to test execution.
- After switching accounts, MT5 may disable automated trading. Re-enable it manually.
- Keep `LIVE_TRADING_ENABLED=false` for normal development.
- Use `SIGNAL_ONLY` or `SEMI_AUTO` before `AUTO_DEMO`.

## Risk Manager Gates

Every BUY/SELL must pass these checks:

- Decision is not HOLD.
- Confidence meets active profile threshold.
- No opposite open position on same symbol.
- D1 major trend allows the direction.
- D1 ranging has breakout and retest confirmation.
- Position count does not exceed cap, except same-direction add-ons.
- Daily drawdown stays below max drawdown.
- Stop loss is provided.
- Take profit is provided.
- Trade parameters are valid for BUY/SELL price logic.
- AI explicitly allows execution.
- `LIVE_AUTO` requires `LIVE_TRADING_ENABLED=true`.

AI controls SL/TP placement. Risk manager does not reject because SL is wide, SL is tight, or R:R is below fixed profile values.

## Position Sizing

- Lot size uses balance or equity and `RISK_PER_TRADE_PERCENT`.
- Broker min/max/step constraints are respected.
- If calculated lot is below broker minimum, executor uses broker minimum and logs warning.
- Telegram settings cap risk/trade presets at 1%.

## Telegram Bot

Main commands:

| Command | Action |
| --- | --- |
| `/start` | Show welcome and controls |
| `/menu` | Open inline control menu |
| `/status` | Show bot/account/trading status |
| `/settings` | Show current settings and risk controls |
| `/positions` | Show all open positions plus P&L summary |
| `/pause` | Pause trading loop |
| `/resume` | Resume trading loop |
| `/mode_signal` | Switch to signal-only mode |
| `/mode_semi` | Switch to semi-auto mode |
| `/mode_demo_auto` | Switch to demo auto mode |
| `/close_all` | Confirm close all positions |
| `/last_signal` | Show latest AI decision |

Inline menu supports:

- Mode controls.
- Pause/resume.
- Position view and close-all confirmation.
- Risk profile controls: Low, Medium, High.
- Risk/trade controls: 0.25%, 0.5%, 1%.
- Symbol controls: all pairs or next pair.
- Manual signal generation and approvals in semi-auto mode.

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
| `POST` | `/close-all` | Close open positions |

Signals and trades:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/last-signal` | Latest AI decision |
| `POST` | `/generate-signal` | Trigger manual signal |
| `POST` | `/approve/{decision_id}` | Approve pending decision |
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
113 passed, 2 warnings
```

Warnings are Supabase client deprecation warnings for timeout/verify configuration.

## Development Notes

- `.env`, logs, caches, and local MT5 probe scripts are intentionally ignored by git.
- Do not commit credentials, account numbers, Telegram tokens, or Supabase service role keys.
- `logs/` can contain full Telegram request URLs with bot tokens. Keep it ignored.
- Root-level local probe scripts that send MT5 orders should stay local and untracked.
- Use tests before behavior changes. Risk and execution behavior should be covered by pytest.

## Troubleshooting

MT5 not connected:

- Start MT5 terminal.
- Log in to correct demo account.
- Verify `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, and optional `MT5_PATH`.

Symbol selection fails:

- Check broker suffix.
- Open Market Watch in MT5.
- Add symbol manually.
- Update `DEFAULT_SYMBOLS`.

Order rejected with AutoTrading disabled:

- Enable Algo Trading toolbar button.
- Check MT5 Tools > Options > Expert Advisors > Allow Automated Trading.
- Re-enable after account switch.

Unsupported filling mode:

- Broker-specific. JustMarkets `.c` symbols were tested with `ORDER_FILLING_FOK`.

Invalid stops or invalid price:

- Broker can enforce dynamic stop constraints.
- Executor refreshes ticks and widens stops on retry where supported.

## Security

- Rotate any token accidentally written to `.env.example` or logs.
- Keep Supabase service role key server-side only.
- Restrict Telegram access with `TELEGRAM_ALLOWED_CHAT_ID`.
- Treat MT5 credentials as high-risk secrets.

## Disclaimer

This software is not financial advice. No profit is guaranteed. You are responsible for all trades, settings, broker behavior, live account access, and losses. Use demo mode first.
