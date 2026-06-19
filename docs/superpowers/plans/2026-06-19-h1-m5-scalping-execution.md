# H1 M5 Scalping Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make demo scalping use H1 trend and M5 entry, and prevent valid BUY/SELL ideas from dying when DeepSeek forgets SL/TP.

**Architecture:** Change market payload entry timeframe from M15 to M5 across signal generation, feature building, prompt, storage labels, and Telegram labels. Add a deterministic SL/TP fallback in the AI validation path using market payload, profile RR, profile SL bounds, and current bid/ask.

**Tech Stack:** Python 3.13, pytest, pandas feature payloads, OpenAI-compatible DeepSeek client, MT5 market data wrapper.

---

## File Structure

- Modify: `app/services/signal_service.py` — fetch M5, pass M5, snapshot M5.
- Modify: `app/analysis/feature_builder.py` — entry timeframe section becomes M5.
- Modify: `app/ai_engine/prompt_builder.py` — H1/M5 prompt and mandatory BUY/SELL fields.
- Modify: `app/ai_engine/deepseek_client.py` — payload-aware SL/TP fallback before validation converts to HOLD.
- Modify: `app/telegram_bot/bot.py` — market update labels M5.
- Modify: `app/telegram_bot/message_templates.py` — signal labels M5.
- Modify: tests for feature builder, prompt builder, and AI validation fallback.

---

### Task 1: M5 Entry Payload

**Files:**
- Modify: `app/analysis/feature_builder.py`
- Modify: `app/services/signal_service.py`
- Test: `tests/test_feature_builder.py`

- [ ] **Step 1: Write failing feature test**

Add test asserting `build_market_payload(... df_m15=entry_df ...)` returns `entry_timeframe["timeframe"] == "M5"` and orderflow is present.

- [ ] **Step 2: Run test**

Run: `pytest tests/test_feature_builder.py::test_entry_timeframe_is_m5 -v`

Expected: FAIL because timeframe is currently M15.

- [ ] **Step 3: Implement M5 label and fetch**

In `feature_builder.py`, build entry section as `M5`.

In `signal_service.py`, fetch `get_candles(sym, timeframe="M5", count=100)`, log M5, pass as entry dataframe, and save snapshot `timeframe: "M5"`, technical key `M5`.

- [ ] **Step 4: Run feature tests**

Run: `pytest tests/test_feature_builder.py -v`

Expected: PASS.

---

### Task 2: H1/M5 Prompt

**Files:**
- Modify: `app/ai_engine/prompt_builder.py`
- Test: `tests/test_prompt_builder.py`

- [ ] **Step 1: Write failing prompt test**

Update prompt tests to assert `H1 trend`, `M5 entry`, `ignore spread`, and mandatory `stop_loss`/`take_profit_1` text.

- [ ] **Step 2: Run prompt tests**

Run: `pytest tests/test_prompt_builder.py -v`

Expected: FAIL until prompt is updated.

- [ ] **Step 3: Implement prompt**

Rewrite scalping prompt to state:

- H1 is primary trend filter.
- M5 is entry trigger.
- D1/H4 context only.
- Spread must never trigger HOLD.
- BUY/SELL must include entry_plan.stop_loss, take_profit_1, preferred_entry_price, risk_reward_to_tp1.
- If H1 and M5 align, prefer BUY/SELL.

- [ ] **Step 4: Run prompt tests**

Run: `pytest tests/test_prompt_builder.py -v`

Expected: PASS.

---

### Task 3: Auto SL/TP Fallback

**Files:**
- Modify: `app/ai_engine/deepseek_client.py`
- Test: `tests/test_ai_engine.py`

- [ ] **Step 1: Write failing fallback test**

Add test that builds BUY decision missing SL/TP plus market payload with current ask, point, risk config, M5 ATR; call new `validate_decision(decision, market_payload=payload)`; assert decision remains BUY and SL/TP are filled.

- [ ] **Step 2: Run fallback test**

Run: `pytest tests/test_ai_engine.py -v`

Expected: FAIL because validate_decision does not accept market payload and converts missing SL to HOLD.

- [ ] **Step 3: Implement payload-aware fallback**

Change `validate_decision(decision, market_payload=None)`.

If decision BUY/SELL and SL or TP missing, call helper to fill market entry:

- point from payload `risk_config.point` or infer `0.01` default.
- entry = ask for BUY, bid for SELL.
- ATR from `entry_timeframe.indicators.atr_14` if numeric.
- SL pips = clamp ATR-derived pips to `min_sl_pips/max_sl_pips` from payload risk_config or settings.
- TP distance = SL distance * min RR.

Update `get_ai_decision` to call `validate_decision(..., market_payload=market_payload)`.

- [ ] **Step 4: Run AI tests**

Run: `pytest tests/test_ai_engine.py -v`

Expected: PASS.

---

### Task 4: Labels M5

**Files:**
- Modify: `app/telegram_bot/bot.py`
- Modify: `app/telegram_bot/message_templates.py`
- Test: existing suite.

- [ ] **Step 1: Update labels**

Replace user-facing `M15` label with `M5` for entry timeframe in signal and market update messages.

- [ ] **Step 2: Run Telegram tests**

Run: `pytest tests/test_telegram_bot.py -v`

Expected: PASS.

---

### Task 5: Final Verification

**Files:**
- No new app files.

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_feature_builder.py tests/test_prompt_builder.py tests/test_ai_engine.py tests/test_telegram_bot.py -v`

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `pytest`

Expected: PASS.

---

## Self-Review Notes

- Spec coverage: M5 payload, H1/M5 prompt, spread ignore, mandatory fields, fallback SL/TP, labels, tests all mapped.
- Placeholder scan: no incomplete placeholder markers.
- Scope: no live trading enablement, no lot-risk changes.
