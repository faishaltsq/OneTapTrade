# Pending Order Cap And Startup Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce max 5 pending orders per symbol, cancel lowest SMC-score orders, and validate pending orders + open positions on restart against D1 trend and SMC zone validity.

**Architecture:** Add a pure `pending_order_manager` service that scores, caps, and validates orders. Wire it into startup after sync and into the trading loop before each cycle. Keep MT5 order cancellation in existing `orders.py`.

**Tech Stack:** Python, pytest, MetaTrader5 Python API abstractions, existing SMC selector and major trend helpers.

---

## File Structure

- Create `app/services/pending_order_manager.py`: cap enforcement, startup validation for pending orders and open positions.
- Create `tests/test_pending_order_manager.py`: unit tests.
- Modify `app/main.py`: call validation functions after startup sync.
- Modify `app/services/trading_loop.py`: call cap enforcement before symbol loop.
- Modify `app/services/execution_service.py`: call cap enforcement after successful LIMIT placement.

### Task 1: Pending Order Manager - Cap Enforcement

**Files:**
- Create: `app/services/pending_order_manager.py`
- Create: `tests/test_pending_order_manager.py`

- [ ] **Step 1: Write failing tests**

Tests:
- `enforce_pending_order_cap` does nothing when count <= 5.
- `enforce_pending_order_cap` cancels lowest-score orders when count > 5.
- Cancelled orders are the ones with invalid zones (score 0).

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_pending_order_manager.py -v`
Expected: FAIL because module is missing.

- [ ] **Step 3: Implement cap enforcement**

Implement `enforce_pending_order_cap(symbol, max_orders=5)` that:
- Gets pending orders for symbol.
- Scores each order using SMC zone validity + distance.
- Cancels lowest-score orders until count == max_orders.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_pending_order_manager.py -v`
Expected: PASS.

### Task 2: Startup Validation - Pending Orders

**Files:**
- Modify: `app/services/pending_order_manager.py`
- Modify: `tests/test_pending_order_manager.py`

- [ ] **Step 1: Write failing tests**

Tests:
- `validate_pending_orders_on_startup` cancels order with wrong D1 direction.
- `validate_pending_orders_on_startup` cancels order with entry outside OB.
- `validate_pending_orders_on_startup` keeps valid order.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_pending_order_manager.py -v`
Expected: FAIL because function is missing.

- [ ] **Step 3: Implement startup pending validation**

Implement `validate_pending_orders_on_startup()` that:
- Gets all pending orders from MT5.
- Gets D1 trend and SMC zones for each symbol.
- Cancels orders with wrong D1 direction or invalid zone.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_pending_order_manager.py -v`
Expected: PASS.

### Task 3: Startup Validation - Open Positions

**Files:**
- Modify: `app/services/pending_order_manager.py`
- Modify: `tests/test_pending_order_manager.py`

- [ ] **Step 1: Write failing tests**

Tests:
- `validate_open_positions_on_startup` warns on wrong D1 direction but does not close.
- `validate_open_positions_on_startup` passes valid position.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_pending_order_manager.py -v`
Expected: FAIL because function is missing.

- [ ] **Step 3: Implement startup position validation**

Implement `validate_open_positions_on_startup()` that:
- Gets all open positions from MT5.
- Gets D1 trend for each symbol.
- Logs warning for misaligned positions.
- Returns summary with warnings list.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_pending_order_manager.py -v`
Expected: PASS.

### Task 4: Wire Into Startup And Trading Loop

**Files:**
- Modify: `app/main.py`
- Modify: `app/services/trading_loop.py`
- Modify: `app/services/execution_service.py`

- [ ] **Step 1: Wire startup validation**

In `main.py` after `sync_pending_orders_from_mt5()`:
- Call `validate_pending_orders_on_startup()`.
- Call `validate_open_positions_on_startup()`.
- Log both summaries.

- [ ] **Step 2: Wire cap enforcement into trading loop**

In `trading_loop.py` `run_once()` before symbol loop:
- Call `enforce_pending_order_cap()` for each configured symbol.

- [ ] **Step 3: Wire cap enforcement after LIMIT placement**

In `execution_service.py` after successful order send:
- Call `enforce_pending_order_cap(sym)`.

- [ ] **Step 4: Run full suite**

Run: `pytest`
Expected: PASS.

### Task 5: Verification And Publish

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_pending_order_manager.py -v`
Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `pytest`
Expected: PASS.

- [ ] **Step 3: Commit and push**

Run `git status --short`, `git diff`, `git log --oneline -10`, commit, push.

## Self-Review

- Spec coverage: cap enforcement, startup pending validation, startup position validation, loop integration, execution integration all covered.
- Placeholder scan: no TBD/TODO.
- Type consistency: `enforce_pending_order_cap`, `validate_pending_orders_on_startup`, `validate_open_positions_on_startup` names match across plan.
