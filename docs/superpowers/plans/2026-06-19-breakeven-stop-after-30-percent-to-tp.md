# Breakeven Stop After 30% To TP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move SL to break-even automatically when an open MT5 position reaches 30% progress from entry to TP.

**Architecture:** Add a focused breakeven service that evaluates open MT5 positions and calls a low-level MT5 SL/TP modification helper. Trading loop invokes the service once per cycle before signal generation, so existing positions after restart are also protected.

**Tech Stack:** Python, MetaTrader5 Python API, pytest, asyncio trading loop.

---

## File Structure

- Create `app/services/breakeven_service.py`: position threshold logic and orchestration.
- Modify `app/mt5_connector/execution.py`: add `modify_position_sl_tp()` helper using `TRADE_ACTION_SLTP`.
- Modify `app/services/trading_loop.py`: call breakeven manager before per-symbol analysis.
- Add `tests/test_breakeven_service.py`: pure logic and service tests.
- Modify `tests/test_trading_loop.py`: verify trading loop calls breakeven manager before symbols.

### Task 1: Breakeven Logic Service

**Files:**
- Create: `app/services/breakeven_service.py`
- Test: `tests/test_breakeven_service.py`

- [ ] **Step 1: Write failing tests**

Create tests for:
- BUY at 30% to TP returns entry as new SL.
- SELL at 30% to TP returns entry as new SL.
- Below threshold returns `None`.
- Already protected returns `None`.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_breakeven_service.py -v`

Expected: FAIL because service module does not exist.

- [ ] **Step 3: Implement pure helper**

Create `calculate_breakeven_stop(position, tick)` that returns target SL or `None`.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_breakeven_service.py -v`

Expected: PASS.

### Task 2: MT5 SL/TP Modification Helper

**Files:**
- Modify: `app/mt5_connector/execution.py`
- Test: `tests/test_breakeven_service.py`

- [ ] **Step 1: Write failing MT5 helper test**

Patch MT5 `order_send` and verify request contains:
- `action=TRADE_ACTION_SLTP`
- `position=ticket`
- `symbol`
- `sl=price_open`
- `tp` unchanged

- [ ] **Step 2: Run red test**

Run: `pytest tests/test_breakeven_service.py -v`

Expected: FAIL because `modify_position_sl_tp` is missing.

- [ ] **Step 3: Implement helper**

Add `modify_position_sl_tp(position, sl, tp)` to `execution.py`.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_breakeven_service.py -v`

Expected: PASS.

### Task 3: Breakeven Manager Orchestration

**Files:**
- Modify: `app/services/breakeven_service.py`
- Test: `tests/test_breakeven_service.py`

- [ ] **Step 1: Write failing manager test**

Patch `is_mt5_connected`, `get_open_positions`, `get_latest_tick`, and `modify_position_sl_tp`. Assert eligible position triggers one modification and summary reports `modified=1`.

- [ ] **Step 2: Run red test**

Run: `pytest tests/test_breakeven_service.py -v`

Expected: FAIL because `manage_breakeven_stops` is missing.

- [ ] **Step 3: Implement manager**

Add `manage_breakeven_stops(symbol=None)` that checks all positions, applies `calculate_breakeven_stop`, and logs a summary.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_breakeven_service.py -v`

Expected: PASS.

### Task 4: Trading Loop Integration

**Files:**
- Modify: `app/services/trading_loop.py`
- Test: `tests/test_trading_loop.py`

- [ ] **Step 1: Write failing loop test**

Patch `manage_breakeven_stops` and `TradingLoop._run_symbol`; call `run_once`; assert breakeven manager runs before `_run_symbol`.

- [ ] **Step 2: Run red test**

Run: `pytest tests/test_trading_loop.py -v`

Expected: FAIL because `run_once` does not call breakeven manager.

- [ ] **Step 3: Integrate manager**

In `TradingLoop.run_once()`, call `manage_breakeven_stops(None)` via `asyncio.to_thread` before iterating symbols.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_trading_loop.py tests/test_breakeven_service.py -v`

Expected: PASS.

### Task 5: Full Verification

**Files:**
- All touched files.

- [ ] **Step 1: Run full suite**

Run: `pytest`

Expected: all tests pass.

## Self-Review

- Spec coverage: automatic 30% to TP threshold, BUY/SELL rules, skip rules, MT5 modification, restart coverage via loop are covered.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: service helpers use dict positions and tick dicts from existing MT5 connector helpers.
