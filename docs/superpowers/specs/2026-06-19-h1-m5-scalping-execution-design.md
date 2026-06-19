# H1 M5 Scalping Execution Design

## Root Cause

No order reaches execution because valid BUY/SELL rarely survives signal validation.

Observed from logs:

- DeepSeek often returns `HOLD`.
- DeepSeek still rejects because of spread, despite spread not being a risk blocker.
- One `SELL` with `0.75` confidence was converted to `HOLD` because `stop_loss` was missing.
- Current pipeline fetches and prompts `M15` as entry timeframe, while desired strategy is H1 trend and M5 entry.

## Goal

Make demo scalping produce executable signals by using H1 as trend filter and M5 as entry trigger, while keeping risk manager and MT5 validation as final safeguards.

## Strategy

- H1 is primary trend direction.
- M5 is entry timeframe.
- D1/H4 are context only and should not block entries.
- Spread is informational only and must never cause DeepSeek to return HOLD.
- DeepSeek must return complete BUY/SELL JSON with SL, TP1, entry price, and RR when it sees valid H1/M5 alignment.

## Auto SL/TP Fallback

If DeepSeek returns `BUY` or `SELL` but misses SL or TP, validator should not immediately convert to `HOLD`.

Instead, generate a fallback entry plan from market payload:

- Entry price: current ask for BUY, current bid for SELL.
- SL distance: use M5 ATR-based distance if available, clamped to profile SL range.
- BUY SL: entry - SL distance.
- BUY TP1: entry + SL distance * profile RR.
- SELL SL: entry + SL distance.
- SELL TP1: entry - SL distance * profile RR.
- Entry type: `MARKET`.
- RR: active profile minimum RR.

If fallback cannot build numeric SL/TP, only then convert to HOLD.

## Files

- `app/services/signal_service.py`: fetch M5 candles, save M5 snapshot labels.
- `app/analysis/feature_builder.py`: rename entry timeframe section to M5 and use M5 for orderflow/regime.
- `app/ai_engine/prompt_builder.py`: rewrite entry rules for H1/M5 and strict BUY/SELL fields.
- `app/ai_engine/deepseek_client.py`: add market-payload-aware fallback before validate_decision converts BUY/SELL to HOLD.
- `app/telegram_bot/bot.py`: market update label M5.
- `app/telegram_bot/message_templates.py`: signal trend label M5.
- Tests: cover M5 payload, prompt, and SL/TP fallback.

## Safety

- Risk manager still validates confidence, RR, SL range, max positions, drawdown, AI permission, and MT5 trade params.
- `AUTO_DEMO` executes only after risk manager approves.
- `LIVE_AUTO` remains blocked unless `LIVE_TRADING_ENABLED=true`.

## Expected Result

DeepSeek should produce more executable `BUY`/`SELL` outputs in demo mode when H1 trend and M5 momentum align. If DeepSeek forgets SL/TP on otherwise valid BUY/SELL, fallback supplies them instead of killing the signal.
