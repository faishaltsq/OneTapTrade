# Readable Market Trend Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render HOLD market updates and BUY/SELL trade signals as readable dashboard-style Telegram alerts.

**Architecture:** Add one shared pure formatter in `message_templates.py` that accepts `decision`, `symbol`, optional `market_payload`, and optional `risk_result`. Wire trading loop and bot signal sender to pass the existing market payload without changing decision or execution behavior.

**Tech Stack:** Python, pytest, python-telegram-bot HTML messages.

---

## File Structure

- Modify `app/telegram_bot/message_templates.py`: add `format_market_trend_alert()` and helper functions; keep `format_signal_message()` as wrapper.
- Modify `app/services/trading_loop.py`: pass `market_payload` into HOLD market update and trade signal notification calls.
- Modify `app/telegram_bot/bot.py`: accept optional `market_payload` in `send_trade_signal()` and pass it to `format_signal_message()`.
- Modify `tests/test_telegram_bot.py`: formatter tests for HOLD and BUY/SELL dashboard sections.
- Modify `tests/test_trading_loop.py`: verify HOLD market update receives and renders payload via formatter.

### Task 1: Shared Dashboard Formatter

**Files:**
- Modify: `app/telegram_bot/message_templates.py`
- Test: `tests/test_telegram_bot.py`

- [ ] **Step 1: Write failing formatter tests**

Add tests that call `format_market_trend_alert()` for HOLD and BUY with a representative `market_payload`. Assert output contains:
- `Market Trend — XAUUSD.c`
- `Bias Map`
- `Price`
- `Momentum`
- `SMC`
- `Orderflow`
- `Read`
- BUY output also contains `Trade Plan` and `Risk Check`.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_telegram_bot.py -v`

Expected: FAIL because `format_market_trend_alert` is missing.

- [ ] **Step 3: Implement formatter**

Add `format_market_trend_alert(decision, symbol, market_payload=None, risk_result=None)` plus small private helpers:
- `_val(value, default="N/A")`
- `_enum_value(value)`
- `_trend_from_section(section)`
- `_format_bias_map(...)`
- `_format_price(...)`
- `_format_momentum(...)`
- `_format_smc(...)`
- `_format_orderflow(...)`
- `_format_trade_plan(...)`

Keep output concise and HTML-safe.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_telegram_bot.py -v`

Expected: PASS.

### Task 2: Signal Formatter Compatibility

**Files:**
- Modify: `app/telegram_bot/message_templates.py`
- Test: `tests/test_telegram_bot.py`

- [ ] **Step 1: Update existing `format_signal_message` test expectations**

Keep existing M5 label test and ensure it still passes through dashboard output.

- [ ] **Step 2: Update `format_signal_message` wrapper**

Change signature to `format_signal_message(decision, risk_result, symbol, market_payload=None)` and return `format_market_trend_alert(...)`.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_telegram_bot.py -v`

Expected: PASS.

### Task 3: Wire Market Payload Into Alerts

**Files:**
- Modify: `app/services/trading_loop.py`
- Modify: `app/telegram_bot/bot.py`
- Test: `tests/test_trading_loop.py`, `tests/test_telegram_bot.py`

- [ ] **Step 1: Write failing integration test**

Patch `send_message`; call `_send_market_update(ai_decision, symbol, market_payload)`; assert sent text contains payload-derived sections such as `Bid/Ask` and `M5 RSI`.

- [ ] **Step 2: Run red test**

Run: `pytest tests/test_trading_loop.py -v`

Expected: FAIL because `_send_market_update` does not accept payload.

- [ ] **Step 3: Update trading loop**

Change `_send_market_update(self, ai_decision, symbol, market_payload=None)` to use `format_market_trend_alert()`.

Pass `signal_result.get("market_payload")` when HOLD path calls `_send_market_update`.

Pass the same payload to `send_trade_signal()` in SIGNAL_ONLY and SEMI_AUTO paths.

- [ ] **Step 4: Update bot signal sender**

Change `send_trade_signal(decision, risk_result, decision_id, market_payload=None)` to call `format_signal_message(..., market_payload=market_payload)`.

- [ ] **Step 5: Run targeted tests**

Run: `pytest tests/test_trading_loop.py tests/test_telegram_bot.py -v`

Expected: PASS.

### Task 4: Full Verification

**Files:**
- All touched files.

- [ ] **Step 1: Run full test suite**

Run: `pytest`

Expected: all tests pass.

## Self-Review

- Spec coverage: HOLD and BUY/SELL dashboards, fallback behavior, existing buttons, and payload wiring are covered.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: formatter accepts optional `market_payload` everywhere; existing callers remain compatible through defaults.
