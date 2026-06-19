# SMC Limit Order Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prefer pending LIMIT orders at high-probability SMC order blocks while still allowing MARKET execution only for confidence >50% trend-following setups.

**Architecture:** Add a pure SMC entry selector under `app/analysis`, integrate it inside `execution_service` before MT5 request building, and update the AI prompt. Keep MT5 request construction minimal because pending LIMIT support already exists.

**Tech Stack:** Python, pytest, MetaTrader5 Python API abstractions, existing AI schema and SMC payload.

---

## File Structure

- Create `app/analysis/smc_entry_selector.py`: pure SMC LIMIT zone selection and MARKET fallback rule helpers.
- Create `tests/test_smc_entry_selector.py`: selector unit tests.
- Modify `app/services/execution_service.py`: call selector, override entry type/price for valid LIMIT, enforce MARKET fallback rule.
- Modify `tests/test_execution_service.py`: integration tests for limit override and market rejection.
- Modify `app/mt5_connector/execution.py`: treat pending-order success retcodes as successful sends.
- Modify `tests/test_execution_service.py` or add focused MT5 request test: pending LIMIT request action/type.
- Modify `app/ai_engine/prompt_builder.py`: instruct AI to prefer LIMIT at valid OB/supply/demand and restrict MARKET.
- Modify `tests/test_prompt_builder.py`: prompt assertion.

### Task 1: SMC Entry Selector

**Files:**
- Create: `app/analysis/smc_entry_selector.py`
- Create: `tests/test_smc_entry_selector.py`

- [ ] **Step 1: Write failing selector tests**

Add tests for BUY demand OB, SELL supply OB, invalid BUY demand above ask, invalid SELL supply below bid, and MARKET fallback rule.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_smc_entry_selector.py -v`
Expected: FAIL because module is missing.

- [ ] **Step 3: Implement selector**

Implement `select_smc_limit_entry()` and `can_use_market_fallback()` with deterministic score/quality output.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_smc_entry_selector.py -v`
Expected: PASS.

### Task 2: Execution Service Integration

**Files:**
- Modify: `app/services/execution_service.py`
- Modify: `tests/test_execution_service.py`

- [ ] **Step 1: Write failing execution tests**

Add tests proving execution converts BUY to LIMIT from a valid demand OB and rejects MARKET fallback when confidence <=50 and no valid LIMIT exists.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_execution_service.py -v`
Expected: FAIL because execution does not call selector or reject weak MARKET fallback.

- [ ] **Step 3: Implement integration**

Call selector before lot sizing. If selector returns LIMIT, set `is_limit=True` and use selector `entry_price`. If no LIMIT, call `can_use_market_fallback()`; reject if false.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_execution_service.py -v`
Expected: PASS.

### Task 3: Pending Order Success Handling

**Files:**
- Modify: `app/mt5_connector/execution.py`
- Test: use `tests/test_execution_service.py` or existing execution tests.

- [ ] **Step 1: Write failing test**

Assert LIMIT order request uses `TRADE_ACTION_PENDING` and BUY_LIMIT/SELL_LIMIT. Assert pending-order success retcode is accepted.

- [ ] **Step 2: Run red test**

Run: `pytest tests/test_execution_service.py -v`
Expected: FAIL if pending success retcode is not accepted.

- [ ] **Step 3: Implement minimal MT5 success acceptance**

Accept both `TRADE_RETCODE_DONE` and `TRADE_RETCODE_PLACED` as successful order sends.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_execution_service.py -v`
Expected: PASS.

### Task 4: Prompt Rules

**Files:**
- Modify: `app/ai_engine/prompt_builder.py`
- Modify: `tests/test_prompt_builder.py`

- [ ] **Step 1: Write failing prompt test**

Assert prompt includes SMC LIMIT preference, BUY_LIMIT demand OB, SELL_LIMIT supply OB, and MARKET only confidence >50 trend-following.

- [ ] **Step 2: Run red test**

Run: `pytest tests/test_prompt_builder.py -v`
Expected: FAIL because prompt lacks LIMIT-specific rules.

- [ ] **Step 3: Update prompt**

Add concise SMC entry execution rules.

- [ ] **Step 4: Run green test**

Run: `pytest tests/test_prompt_builder.py -v`
Expected: PASS.

### Task 5: Full Verification And Publish

**Files:**
- All touched files.

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_smc_entry_selector.py tests/test_execution_service.py tests/test_prompt_builder.py -v`
Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `pytest`
Expected: PASS.

- [ ] **Step 3: Commit and push**

Run `git status --short`, `git diff`, `git log --oneline -10`, commit, then push to `origin/main`.

## Self-Review

- Spec coverage: selector, LIMIT preference, MARKET fallback, GTC pending order, prompt, tests covered.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: selector return keys match spec and planned integration.
