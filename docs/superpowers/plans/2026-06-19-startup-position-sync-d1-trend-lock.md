# Startup Position Sync And D1 Trend Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync live MT5 positions at startup and enforce direction consistency using open-position locks plus D1 major trend rules.

**Architecture:** Add pure analysis helpers for D1 major trend, a runtime position-state service backed by MT5 startup sync, and hard risk-manager checks using fields already passed through `market_context`. Keep same-direction add-ons allowed while blocking opposite direction.

**Tech Stack:** Python, MetaTrader5 Python API, Supabase repositories, pytest.

---

## File Structure

- Create `app/analysis/major_trend.py`: D1 candle bias and breakout/retest helpers.
- Create `app/services/position_state_service.py`: runtime open-position state and startup sync.
- Modify `app/analysis/feature_builder.py`: add `major_trend` and `open_position_state` to payload.
- Modify `app/services/signal_service.py`: pass position state and major trend into risk context.
- Modify `app/risk/risk_manager.py`: hard reject opposite direction and D1 violations while allowing same-direction add-ons.
- Modify `app/ai_engine/prompt_builder.py`: update prompt with D1 major trend and position-lock rules.
- Modify `app/main.py`: call startup position sync after MT5 login.
- Modify tests: add/extend `tests/test_major_trend.py`, `tests/test_position_state_service.py`, `tests/test_feature_builder.py`, `tests/test_risk_manager.py`, `tests/test_prompt_builder.py`.

### Task 1: D1 Major Trend Helper

**Files:**
- Create: `app/analysis/major_trend.py`
- Test: `tests/test_major_trend.py`

- [ ] **Step 1: Write failing tests**

Test these behaviors:
- Latest D1 candle `close > open` with meaningful body returns `D1_BULLISH`.
- Latest D1 candle `close < open` with meaningful body returns `D1_BEARISH`.
- Small body relative to range returns `D1_RANGING`.
- Ranging breakout retest true only when breakout direction and retest flag are present.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_major_trend.py -v`

Expected: FAIL because module is missing.

- [ ] **Step 3: Implement helper**

Add `build_major_trend_section(df_d1, smc=None)` returning:

```python
{
    "bias": "D1_BULLISH" | "D1_BEARISH" | "D1_RANGING",
    "candle_open": float | None,
    "candle_close": float | None,
    "range_high": float | None,
    "range_low": float | None,
    "breakout_retest_confirmed": bool,
    "allowed_directions": ["BUY"] | ["SELL"] | []
}
```

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_major_trend.py -v`

Expected: PASS.

### Task 2: Runtime Position State And Startup Sync

**Files:**
- Create: `app/services/position_state_service.py`
- Modify: `app/main.py`
- Test: `tests/test_position_state_service.py`

- [ ] **Step 1: Write failing tests**

Test these behaviors:
- `sync_open_positions_from_mt5()` reads MT5 positions and stores side per symbol.
- Existing BUY state blocks SELL but not BUY through helper return values.
- Startup sync calls repository upsert/save path for missing trade ticket when DB available.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_position_state_service.py -v`

Expected: FAIL because module is missing.

- [ ] **Step 3: Implement service**

Add:
- module dict `_OPEN_POSITION_STATE = {}`
- `sync_open_positions_from_mt5()`
- `get_open_position_state(symbol=None)`
- `has_opposite_position(symbol, decision)`
- `clear_position_state()` for tests

Do DB writes best-effort only.

- [ ] **Step 4: Wire startup**

In `main.py`, after `login_mt5()` success, call `sync_open_positions_from_mt5()` and log summary.

- [ ] **Step 5: Run green tests**

Run: `pytest tests/test_position_state_service.py -v`

Expected: PASS.

### Task 3: Payload Integration

**Files:**
- Modify: `app/analysis/feature_builder.py`
- Test: `tests/test_feature_builder.py`

- [ ] **Step 1: Write failing test**

Assert market payload includes:
- `major_trend.bias`
- `major_trend.allowed_directions`
- `open_position_state`

- [ ] **Step 2: Run red test**

Run: `pytest tests/test_feature_builder.py -v`

Expected: FAIL because payload fields are missing.

- [ ] **Step 3: Implement payload fields**

Call `build_major_trend_section(df_d1, smc_section)` and `get_open_position_state(symbol)` inside `build_market_payload()`.

- [ ] **Step 4: Run green test**

Run: `pytest tests/test_feature_builder.py -v`

Expected: PASS.

### Task 4: Risk Manager Enforcement

**Files:**
- Modify: `app/services/signal_service.py`
- Modify: `app/risk/risk_manager.py`
- Test: `tests/test_risk_manager.py`

- [ ] **Step 1: Write failing tests**

Tests:
- Open BUY state rejects SELL.
- Open BUY state allows BUY.
- D1 bullish rejects SELL.
- D1 bearish rejects BUY.
- D1 ranging rejects BUY/SELL when `breakout_retest_confirmed=False`.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_risk_manager.py -v`

Expected: FAIL because risk checks are missing.

- [ ] **Step 3: Pass context from signal service**

Add `major_trend` and `open_position_state` from market payload into `market_context`.

- [ ] **Step 4: Implement risk manager checks**

Add hard checks after HOLD/confidence and before trade validation:
- opposite open position check
- major trend allowed direction check
- D1 ranging breakout/retest check

Do not use `max_open_positions` for same-direction add-ons.

- [ ] **Step 5: Run green tests**

Run: `pytest tests/test_risk_manager.py -v`

Expected: PASS.

### Task 5: Prompt Rules

**Files:**
- Modify: `app/ai_engine/prompt_builder.py`
- Test: `tests/test_prompt_builder.py`

- [ ] **Step 1: Write failing prompt test**

Assert prompt includes:
- D1 major trend hard filter.
- Same-direction add-ons allowed.
- Opposite direction blocked when open position exists.
- D1 ranging requires breakout + retest.

- [ ] **Step 2: Run red test**

Run: `pytest tests/test_prompt_builder.py -v`

Expected: FAIL because prompt lacks rules.

- [ ] **Step 3: Update prompt**

Add concise rules to `SYSTEM_PROMPT`.

- [ ] **Step 4: Run green test**

Run: `pytest tests/test_prompt_builder.py -v`

Expected: PASS.

### Task 6: Full Verification

**Files:**
- All touched files.

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_major_trend.py tests/test_position_state_service.py tests/test_feature_builder.py tests/test_risk_manager.py tests/test_prompt_builder.py -v`

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `pytest`

Expected: all tests pass.

## Self-Review

- Spec coverage: startup sync, direction lock, same-direction add-on allowance, D1 filter, ranging breakout/retest, prompt, risk enforcement, and payload fields are covered.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: `major_trend` and `open_position_state` are dicts across payload and risk context.
