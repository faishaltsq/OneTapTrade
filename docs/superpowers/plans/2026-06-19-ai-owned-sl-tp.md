# AI-Owned SL/TP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let AI determine stop loss and take profit freely, while keeping only basic execution safety checks.

**Architecture:** Risk manager stops enforcing strategy geometry and only enforces operational gates. Prompt no longer tells AI hard SL/RR ranges. AI validator no longer invents fallback SL/TP; missing AI geometry stays invalid.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest, MT5 connector.

---

## File Structure

- Modify: `app/risk/risk_manager.py` removes deterministic SL pips and R:R gates.
- Modify: `app/ai_engine/deepseek_client.py` removes fallback SL/TP generation and helper functions.
- Modify: `app/ai_engine/prompt_builder.py` removes hard SL/RR constraints from system and user prompts.
- Modify: `app/telegram_bot/message_templates.py` updates settings copy to say SL/TP are AI-owned.
- Modify: `tests/test_risk_manager.py` updates/adds tests for wide SL and low RR approval.
- Modify: `tests/test_ai_engine.py` replaces fallback test with missing SL/TP stays HOLD behavior.
- Modify: `tests/test_prompt_builder.py` verifies prompt no longer exposes hard geometry constraints.
- Modify: `tests/test_telegram_bot.py` verifies settings text says SL/TP are AI-owned.

---

### Task 1: Remove Risk Manager Geometry Rejections

**Files:**
- Modify: `tests/test_risk_manager.py`
- Modify: `app/risk/risk_manager.py`

- [ ] **Step 1: Write failing tests for wide SL and low RR approval**

Add tests to `tests/test_risk_manager.py`:

```python
def test_wide_ai_stop_loss_is_allowed_when_other_checks_pass(mock_settings):
    from app.ai_engine.schemas import AIDecisionResponse, Decision, ConfidenceLabel, MarketRegime, TimeframeBias, EntryPlan, EntryType, ExecutionPermission
    from app.risk.risk_manager import evaluate_decision

    mock_settings.effective_min_confidence = 0.55
    decision = AIDecisionResponse(
        decision=Decision.SELL,
        confidence=0.65,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_plan=EntryPlan(
            entry_type=EntryType.MARKET,
            preferred_entry_price=4168.262,
            stop_loss=4177.082,
            take_profit_1=4154.0,
            risk_reward_to_tp1=1.5,
        ),
        execution_permission=ExecutionPermission(ai_allows_execution=True),
    )
    context = {
        "symbol": "XAUUSDm",
        "current_bid": 4168.262,
        "current_ask": 4168.5,
        "open_positions_count": 0,
        "daily_drawdown_percent": 0.0,
        "mode": "AUTO_DEMO",
        "point": 0.001,
    }

    result = evaluate_decision(decision, context)

    assert result["approved"] is True
    assert result["checks"]["sl_range_ok"] is True


def test_low_ai_risk_reward_is_allowed_when_other_checks_pass(mock_settings):
    from app.ai_engine.schemas import AIDecisionResponse, Decision, ConfidenceLabel, MarketRegime, TimeframeBias, EntryPlan, EntryType, ExecutionPermission
    from app.risk.risk_manager import evaluate_decision

    mock_settings.effective_min_confidence = 0.55
    decision = AIDecisionResponse(
        decision=Decision.SELL,
        confidence=0.65,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_plan=EntryPlan(
            entry_type=EntryType.MARKET,
            preferred_entry_price=1.14468,
            stop_loss=1.14768,
            take_profit_1=1.14268,
            risk_reward_to_tp1=0.67,
        ),
        execution_permission=ExecutionPermission(ai_allows_execution=True),
    )
    context = {
        "symbol": "EURUSDm",
        "current_bid": 1.14468,
        "current_ask": 1.14472,
        "open_positions_count": 0,
        "daily_drawdown_percent": 0.0,
        "mode": "AUTO_DEMO",
        "point": 0.00001,
    }

    result = evaluate_decision(decision, context)

    assert result["approved"] is True
    assert result["checks"]["risk_reward_ok"] is True
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_risk_manager.py::test_wide_ai_stop_loss_is_allowed_when_other_checks_pass tests/test_risk_manager.py::test_low_ai_risk_reward_is_allowed_when_other_checks_pass -v`

Expected: FAIL with `SL too wide` or `TP ... must be at least`.

- [ ] **Step 3: Remove geometry gates**

In `app/risk/risk_manager.py`, delete:

```python
        if risk_reward_to_tp1 is not None and risk_reward_to_tp1 < settings.effective_min_risk_reward:
            checks["risk_reward_ok"] = False
            return _reject(
                checks,
                f"R:R ({risk_reward_to_tp1:.2f}) below minimum {settings.effective_min_risk_reward}",
            )
```

Replace the SL/TP distance block with no deterministic distance rules. Keep no code between TP existence checks and `validate_trade_params()` except existing imports and context extraction.

- [ ] **Step 4: Run risk manager tests**

Run: `pytest tests/test_risk_manager.py -v`

Expected: PASS.

---

### Task 2: Remove Fallback SL/TP Generation

**Files:**
- Modify: `tests/test_ai_engine.py`
- Modify: `app/ai_engine/deepseek_client.py`

- [ ] **Step 1: Replace fallback test**

In `tests/test_ai_engine.py`, replace `test_validate_decision_fills_missing_sl_tp_from_market_payload` with:

```python
def test_validate_decision_does_not_generate_missing_sl_tp():
    decision = AIDecisionResponse(
        decision=Decision.BUY,
        confidence=0.5,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.TRENDING_UP,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BULLISH,
        entry_plan=EntryPlan(entry_type=EntryType.MARKET),
        execution_permission=ExecutionPermission(ai_allows_execution=True),
    )
    payload = {
        "current_price": {"bid": 2010.0, "ask": 2010.5},
        "entry_timeframe": {"indicators": {"atr_14": 1.5}},
        "risk_config": {"point": 0.01},
    }

    corrected = validate_decision(decision, market_payload=payload)

    assert corrected.decision == Decision.HOLD
    assert corrected.entry_plan.entry_type == EntryType.NONE
    assert corrected.entry_plan.stop_loss is None
    assert corrected.entry_plan.take_profit_1 is None
    assert corrected.execution_permission.ai_allows_execution is False
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_ai_engine.py::test_validate_decision_does_not_generate_missing_sl_tp -v`

Expected: FAIL because current code generates fallback SL/TP and keeps BUY.

- [ ] **Step 3: Remove fallback code**

In `app/ai_engine/deepseek_client.py`:

- Keep signature `validate_decision(decision: AIDecisionResponse, market_payload: dict | None = None)` to avoid changing callers.
- In missing `stop_loss` branch, always switch to HOLD.
- In missing `take_profit_1` branch, always switch to HOLD.
- Delete `_fill_missing_entry_plan`, `_infer_point`, and `_price_decimals`.

- [ ] **Step 4: Run AI engine tests**

Run: `pytest tests/test_ai_engine.py -v`

Expected: PASS.

---

### Task 3: Remove Prompt And Settings Geometry Constraints

**Files:**
- Modify: `tests/test_prompt_builder.py`
- Modify: `tests/test_telegram_bot.py`
- Modify: `app/ai_engine/prompt_builder.py`
- Modify: `app/telegram_bot/message_templates.py`

- [ ] **Step 1: Add prompt test**

Add to `tests/test_prompt_builder.py`:

```python
def test_prompt_does_not_hardcode_sl_or_rr_constraints():
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt({"symbol": "XAUUSDm", "current_price": {"bid": 2000, "ask": 2001}})
    combined = f"{system_prompt}\n{user_prompt}"

    assert "SL range" not in combined
    assert "Minimum R:R" not in combined
    assert "30-100" not in combined
    assert "15-80" not in combined
    assert "minimum profile R:R" not in combined
    assert "AI chooses stop_loss and take_profit_1" in combined
```

- [ ] **Step 2: Add Telegram settings test**

Add to `tests/test_telegram_bot.py`:

```python
def test_settings_message_says_sl_tp_are_ai_owned():
    from app.telegram_bot.message_templates import format_settings_message

    message = format_settings_message()

    assert "SL/TP: AI-owned" in message
    assert "SL Range" not in message
    assert "Min R:R" not in message
    assert "TP:</b> min" not in message
```

- [ ] **Step 3: Run tests to verify failure**

Run: `pytest tests/test_prompt_builder.py::test_prompt_does_not_hardcode_sl_or_rr_constraints tests/test_telegram_bot.py::test_settings_message_says_sl_tp_are_ai_owned -v`

Expected: FAIL because current prompt/settings still mention hard geometry constraints.

- [ ] **Step 4: Update prompt**

In `app/ai_engine/prompt_builder.py`:

- Replace `Stop Loss & Take Profit rules` content with:

```text
Stop Loss & Take Profit rules:
- AI chooses stop_loss and take_profit_1 freely from market structure, volatility, liquidity, and the current setup.
- Set logical SL at invalidation level for the setup.
- Set TP1 at the best realistic target for the setup.
- Do not force SL width or R:R to match fixed profile values.
```

- Replace risk profile behavior text so LOW/MEDIUM/HIGH mention confidence and aggressiveness only, not RR or SL ranges.
- Remove `Minimum R:R` and `SL range` lines from `build_user_prompt()`.

- [ ] **Step 5: Update Telegram settings text**

In `app/telegram_bot/message_templates.py`, replace settings lines:

```python
        f"<b>Min R:R:</b> {settings.effective_min_risk_reward:.1f}\n"
        f"<b>SL Range:</b> {settings.effective_min_sl_pips}-{settings.effective_max_sl_pips} pips\n"
        f"<b>TP:</b> min {settings.effective_min_risk_reward:.1f}x SL\n"
```

with:

```python
        "<b>SL/TP:</b> AI-owned\n"
```

- [ ] **Step 6: Run prompt and Telegram tests**

Run: `pytest tests/test_prompt_builder.py tests/test_telegram_bot.py -v`

Expected: PASS.

---

### Task 4: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run targeted test group**

Run: `pytest tests/test_risk_manager.py tests/test_ai_engine.py tests/test_prompt_builder.py tests/test_telegram_bot.py -v`

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run: `pytest`

Expected: all tests PASS.

- [ ] **Step 3: Manual runtime check**

Restart bot with: `python run.py`

Expected behavior in Telegram/logs:

- Rejections no longer say `SL too wide`.
- Rejections no longer say `TP (...) must be at least ...x SL`.
- If AI sends BUY/SELL with valid side geometry and other gates pass, risk manager approves.
- If MT5 rejects order, rejection comes from MT5/order_check/position sizing, not hard SL/RR gates.

---

## Self-Review

- Spec coverage: risk manager geometry gates, AI fallback removal, prompt constraints, Telegram settings, position sizing unchanged, and tests all covered.
- Placeholder scan: no TBD/TODO/placeholder steps.
- Type consistency: all referenced functions and classes already exist in the project.
