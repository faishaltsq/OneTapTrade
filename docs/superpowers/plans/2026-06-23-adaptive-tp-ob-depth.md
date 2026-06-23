# Adaptive TP Based On OB Depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cap TP ratio to 1:1.5-1:2 for near-third OB LIMIT entries, keep SMC-based TP for premium entries, and update DeepSeek prompt with near-third guidance.

**Architecture:** Add zone depth to SMC selector output, create SMC TP target helper, adjust TP in execution service for near-third entries, and update prompt.

**Tech Stack:** Python, pytest, existing SMC payload and selector.

---

## File Structure

- Modify `app/analysis/smc_entry_selector.py`: add `zone_depth` and `is_near_third` to return.
- Create `app/analysis/smc_tp_target.py`: find nearest SMC-based TP target.
- Modify `app/services/execution_service.py`: adjust TP for near-third LIMIT entries.
- Modify `app/ai_engine/prompt_builder.py`: add near-third TP guidance.
- Create `tests/test_smc_tp_target.py`: SMC TP target tests.
- Modify `tests/test_smc_entry_selector.py`: zone depth tests.
- Modify `tests/test_execution_service.py`: TP cap tests.
- Modify `tests/test_prompt_builder.py`: prompt assertion.

### Task 1: Zone Depth In Selector

**Files:**
- Modify: `app/analysis/smc_entry_selector.py`
- Modify: `tests/test_smc_entry_selector.py`

- [ ] **Step 1: Write failing tests**

Assert selector return includes `zone_depth` (float 0-1) and `is_near_third` (bool) for BUY and SELL.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_smc_entry_selector.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement zone depth**

Add `zone_depth` and `is_near_third` to `_limit_result()`. BUY near-third: `depth < 0.33`. SELL near-third: `depth > 0.67`.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_smc_entry_selector.py -v`
Expected: PASS.

### Task 2: SMC TP Target Helper

**Files:**
- Create: `app/analysis/smc_tp_target.py`
- Create: `tests/test_smc_tp_target.py`

- [ ] **Step 1: Write failing tests**

Tests:
- BUY: returns nearest liquidity level above entry.
- BUY: returns FVG top if no liquidity.
- SELL: returns nearest liquidity level below entry.
- Returns None when no SMC target.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_smc_tp_target.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement helper**

`find_smc_tp_target(side, entry_price, smc)` returns nearest target or None.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_smc_tp_target.py -v`
Expected: PASS.

### Task 3: Execution TP Adjustment

**Files:**
- Modify: `app/services/execution_service.py`
- Modify: `tests/test_execution_service.py`

- [ ] **Step 1: Write failing tests**

Tests:
- Near-third BUY LIMIT caps TP at 2x SL distance when SMC target too far.
- Near-third BUY LIMIT uses 1.5x SL when no SMC target.
- Middle-third BUY LIMIT keeps AI TP unchanged.

- [ ] **Step 2: Run red tests**

Run: `pytest tests/test_execution_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement TP adjustment**

After SMC selector returns valid LIMIT with `is_near_third=True`, adjust `take_profit` before order build.

- [ ] **Step 4: Run green tests**

Run: `pytest tests/test_execution_service.py -v`
Expected: PASS.

### Task 4: Prompt Update

**Files:**
- Modify: `app/ai_engine/prompt_builder.py`
- Modify: `tests/test_prompt_builder.py`

- [ ] **Step 1: Write failing test**

Assert prompt mentions near-third TP conservative 1:1.5 to 1:2.

- [ ] **Step 2: Run red test**

Run: `pytest tests/test_prompt_builder.py -v`
Expected: FAIL.

- [ ] **Step 3: Update prompt**

Add near-third TP guidance.

- [ ] **Step 4: Run green test**

Run: `pytest tests/test_prompt_builder.py -v`
Expected: PASS.

### Task 5: Verification And Publish

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_smc_entry_selector.py tests/test_smc_tp_target.py tests/test_execution_service.py tests/test_prompt_builder.py -v`
Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `pytest`
Expected: PASS.

- [ ] **Step 3: Commit and push**

## Self-Review

- Spec coverage: zone depth, TP target helper, execution adjustment, prompt all covered.
- Placeholder scan: no TBD/TODO.
- Type consistency: `zone_depth`, `is_near_third`, `find_smc_tp_target` names match across plan.
