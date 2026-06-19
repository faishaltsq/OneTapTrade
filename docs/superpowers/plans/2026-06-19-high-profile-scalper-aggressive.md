# High Profile Scalper Aggressive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make only `HIGH` profile more aggressive for short-term scalping while preserving money-risk and safety controls.

**Architecture:** Extend existing profile config with SL pip bounds, then make risk manager and Telegram settings consume those effective values. Update DeepSeek prompt so `HIGH` favors M15 momentum, near-market entries, and lower confidence/RR thresholds.

**Tech Stack:** Python 3.13, pytest, python-telegram-bot, DeepSeek prompt builder, current config singleton.

---

## File Structure

- Modify: `app/config.py` — add `HIGH` thresholds and profile-specific SL bounds.
- Modify: `app/risk/risk_manager.py` — use effective SL min/max from config.
- Modify: `app/ai_engine/prompt_builder.py` — update `HIGH` scalper prompt and user thresholds.
- Modify: `app/telegram_bot/message_templates.py` — show effective SL range and TP multiplier.
- Modify: `tests/test_risk_manager.py` — add `HIGH` threshold/SL/RR approval and rejection tests.
- Modify: `tests/test_prompt_builder.py` — assert aggressive `HIGH` prompt text and thresholds.

---

### Task 1: Config Effective Scalping Thresholds

**Files:**
- Modify: `app/config.py`
- Test: `tests/test_risk_manager.py`

- [ ] **Step 1: Write failing config test**

Append assertions to `test_high_profile_thresholds_are_aggressive`:

```python
        assert settings.effective_min_confidence == 0.40
        assert settings.effective_min_risk_reward == 1.2
        assert settings.effective_min_sl_pips == 15
        assert settings.effective_max_sl_pips == 80
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_risk_manager.py::test_high_profile_thresholds_are_aggressive -v`

Expected: FAIL because effective SL properties do not exist and confidence/RR still use previous values.

- [ ] **Step 3: Implement config values**

Update `app/config.py` profile configs:

```python
"LOW": {"min_confidence": 0.65, "min_risk_reward": 2.0, "min_sl_pips": 30, "max_sl_pips": 100},
"MEDIUM": {"min_confidence": 0.55, "min_risk_reward": 1.5, "min_sl_pips": 30, "max_sl_pips": 100},
"HIGH": {"min_confidence": 0.40, "min_risk_reward": 1.2, "min_sl_pips": 15, "max_sl_pips": 80},
```

Add properties:

```python
    @property
    def effective_min_sl_pips(self) -> int:
        return self.risk_profile_config["min_sl_pips"]

    @property
    def effective_max_sl_pips(self) -> int:
        return self.risk_profile_config["max_sl_pips"]
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_risk_manager.py::test_high_profile_thresholds_are_aggressive -v`

Expected: PASS.

---

### Task 2: Risk Manager Uses Profile SL Bounds

**Files:**
- Modify: `app/risk/risk_manager.py`
- Test: `tests/test_risk_manager.py`

- [ ] **Step 1: Write failing risk tests**

Add tests for `HIGH` approving `15 pip` SL, rejecting below `15`, rejecting above `80`, and keeping `LOW` below `30` rejected.

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_risk_manager.py::TestHighProfileAggressiveEntry -v`

Expected: FAIL because risk manager still hardcodes `30-100` pips.

- [ ] **Step 3: Replace hardcoded bounds**

In `app/risk/risk_manager.py`, use:

```python
min_sl_pips = settings.effective_min_sl_pips
max_sl_pips = settings.effective_max_sl_pips
```

Reject using those values in reason text.

- [ ] **Step 4: Run risk tests**

Run: `pytest tests/test_risk_manager.py -v`

Expected: PASS.

---

### Task 3: Prompt Reflects HIGH Scalper Aggressive Mode

**Files:**
- Modify: `app/ai_engine/prompt_builder.py`
- Test: `tests/test_prompt_builder.py`

- [ ] **Step 1: Update prompt tests**

Expect `Minimum confidence: 40%`, `Minimum R:R: 1.2`, `SL range: 15-80 pips`, and prompt text containing `D1 and H4 are context only`.

- [ ] **Step 2: Run prompt tests**

Run: `pytest tests/test_prompt_builder.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement prompt changes**

Update `HIGH profile` text to mention `40-50%`, `1.2R`, `15-80 pips`, M15 momentum, H1 strong-opposite-only blocker, and D1/H4 as context only.

Update `build_user_prompt` to include:

```python
f"SL range: {settings.effective_min_sl_pips}-{settings.effective_max_sl_pips} pips\n"
```

- [ ] **Step 4: Run prompt tests**

Run: `pytest tests/test_prompt_builder.py -v`

Expected: PASS.

---

### Task 4: Telegram Settings Shows Effective SL Range

**Files:**
- Modify: `app/telegram_bot/message_templates.py`
- Test: full suite.

- [ ] **Step 1: Update settings message**

Replace SL text with effective config values:

```python
f"<b>SL Range:</b> {settings.effective_min_sl_pips}-{settings.effective_max_sl_pips} pips\n"
```

- [ ] **Step 2: Run full tests**

Run: `pytest`

Expected: PASS.

---

### Task 5: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_risk_manager.py tests/test_prompt_builder.py -v`

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `pytest`

Expected: PASS.

---

## Self-Review Notes

- Spec coverage: HIGH-only thresholds, SL range, DeepSeek prompt, Telegram display, and tests mapped to tasks.
- Placeholder scan: no incomplete placeholder markers.
- Scope: one profile behavior change, no live-trading or lot-risk change.
