# Telegram Alert Data Quality EMA200 RSI 25/75 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Telegram market trend alerts show real data first, use EMA50/EMA200, and classify RSI with 25/75 thresholds.

**Architecture:** Keep analysis data creation in `feature_builder.py`, display logic in `message_templates.py`, and AI instructions in `prompt_builder.py`. Add tests before each behavior change and keep fallback wording display-only without inventing broker data.

**Tech Stack:** Python, pandas, pytest, FastAPI project modules, python-telegram-bot message formatting.

---

## File Structure

- Modify `app/analysis/feature_builder.py`: expose `ema_200` and `rsi_state` in timeframe indicators.
- Modify `app/telegram_bot/message_templates.py`: display EMA50/200, RSI state, Indonesian fallback wording, and bias fallback from EMA.
- Modify `app/ai_engine/prompt_builder.py`: update RSI 25/75 and EMA50/200 guidance.
- Modify `tests/test_feature_builder.py`: verify indicators contain EMA200 and RSI state.
- Modify `tests/test_telegram_bot.py`: verify market alert wording and fallback behavior.
- Modify `tests/test_prompt_builder.py`: verify prompt RSI/EMA guidance.

### Task 1: Indicator Payload

**Files:**
- Modify: `tests/test_feature_builder.py`
- Modify: `app/analysis/feature_builder.py`

- [ ] **Step 1: Write failing test**

Add a test asserting `entry_timeframe.indicators` includes `ema_50`, `ema_200`, and `rsi_state`, and does not need `ema_20` for alert momentum.

- [ ] **Step 2: Run test**

Run: `pytest tests/test_feature_builder.py -v`
Expected: FAIL because `ema_200` and `rsi_state` are missing.

- [ ] **Step 3: Implement indicators**

Update `_safe_indicators()` to compute EMA50, EMA200, RSI14, ATR14, and RSI state using 25/75 thresholds.

- [ ] **Step 4: Run green test**

Run: `pytest tests/test_feature_builder.py -v`
Expected: PASS.

### Task 2: Telegram Alert Formatting

**Files:**
- Modify: `tests/test_telegram_bot.py`
- Modify: `app/telegram_bot/message_templates.py`

- [ ] **Step 1: Write failing tests**

Add tests asserting market trend alert:
- displays `EMA50/200`.
- displays RSI state, such as `Normal`.
- does not display `N/A` or `UNCLEAR` in market trend alert when fallback wording applies.
- uses EMA50/200 to infer bias when structure is `UNCLEAR`.

- [ ] **Step 2: Run test**

Run: `pytest tests/test_telegram_bot.py -v`
Expected: FAIL because formatter still shows `EMA20/50`, `N/A`, or `UNCLEAR`.

- [ ] **Step 3: Implement formatter**

Add display helpers for missing data and unclear bias. Update `_ema_bias()` to use EMA50/EMA200 and update `_format_momentum()`, `_format_bias_map()`, `_format_smc()`, and `_format_orderflow()` fallback text.

- [ ] **Step 4: Run green test**

Run: `pytest tests/test_telegram_bot.py -v`
Expected: PASS.

### Task 3: Prompt Rules

**Files:**
- Modify: `tests/test_prompt_builder.py`
- Modify: `app/ai_engine/prompt_builder.py`

- [ ] **Step 1: Write failing test**

Assert system prompt contains EMA50/EMA200, overbought `>75`, and oversold `<25`.

- [ ] **Step 2: Run test**

Run: `pytest tests/test_prompt_builder.py -v`
Expected: FAIL because prompt still uses old thresholds.

- [ ] **Step 3: Implement prompt update**

Update BUY/SELL rules and trading style text to mention EMA50/EMA200 and RSI 25/75.

- [ ] **Step 4: Run green test**

Run: `pytest tests/test_prompt_builder.py -v`
Expected: PASS.

### Task 4: Verification And Publish

**Files:**
- All touched files.

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_feature_builder.py tests/test_telegram_bot.py tests/test_prompt_builder.py -v`
Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `pytest`
Expected: PASS.

- [ ] **Step 3: Commit and push**

Run: `git status --short`, `git diff`, `git log --oneline -10`, then commit and push to `origin/main`.

## Self-Review

- Spec coverage: covers real data fallback, EMA50/200, RSI 25/75, prompt update, tests, and no fake orderflow.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: `rsi_state`, `ema_50`, and `ema_200` names match across plan.
