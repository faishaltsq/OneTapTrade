# Aggressive Entry Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `High` Telegram profile execute more aggressive scalping setups at `50%` confidence and `1.5` RR while keeping fixed money risk unchanged.

**Architecture:** Keep profile thresholds centralized in `app/config.py`, pass profile intent into DeepSeek via `prompt_builder.py`, and enforce executable limits in `risk_manager.py`. Telegram callbacks keep updating runtime + Supabase state, but avoid crashing on Supabase failure.

**Tech Stack:** Python 3.13, pytest, python-telegram-bot, FastAPI runtime config, Supabase repository functions.

---

## File Structure

- Modify: `app/config.py` — profile threshold source of truth.
- Modify: `app/ai_engine/prompt_builder.py` — profile-aware DeepSeek instructions and prompt payload.
- Modify: `app/risk/risk_manager.py` — use effective RR threshold instead of hardcoded `2x SL`.
- Modify: `app/telegram_bot/callbacks.py` — keep profile button responsive if Supabase update fails.
- Modify: `app/telegram_bot/message_templates.py` — settings copy reflects profile thresholds.
- Modify: `tests/test_risk_manager.py` — regression tests for `High` profile thresholds and TP/SL RR validation.
- Create: `tests/test_prompt_builder.py` — profile-aware prompt regression tests.
- Modify: `tests/test_telegram_bot.py` — test risk callback updates runtime even if DB fails.

---

### Task 1: Profile Threshold Source Of Truth

**Files:**
- Modify: `app/config.py:47-62`
- Test: `tests/test_risk_manager.py`

- [ ] **Step 1: Write failing tests for `HIGH` thresholds**

Append to `tests/test_risk_manager.py`:

```python

def test_high_profile_thresholds_are_aggressive():
    from app.config import settings

    original_profile = settings.risk_profile
    try:
        settings.risk_profile = "HIGH"

        assert settings.effective_min_confidence == 0.50
        assert settings.effective_min_risk_reward == 1.5
    finally:
        settings.risk_profile = original_profile
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_risk_manager.py::test_high_profile_thresholds_are_aggressive -v`

Expected: FAIL because `effective_min_confidence` is currently `0.45`.

- [ ] **Step 3: Update `HIGH` profile threshold**

In `app/config.py`, change `risk_profile_config` to:

```python
    @property
    def risk_profile_config(self) -> dict:
        profiles = {
            "LOW": {
                "min_confidence": 0.65,
                "min_risk_reward": 2.0,
            },
            "MEDIUM": {
                "min_confidence": 0.55,
                "min_risk_reward": 1.5,
            },
            "HIGH": {
                "min_confidence": 0.50,
                "min_risk_reward": 1.5,
            },
        }
        return profiles.get(self.risk_profile, profiles["MEDIUM"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_risk_manager.py::test_high_profile_thresholds_are_aggressive -v`

Expected: PASS.

---

### Task 2: Risk Manager Uses Effective RR For TP Distance

**Files:**
- Modify: `app/risk/risk_manager.py:91-95`
- Test: `tests/test_risk_manager.py`

- [ ] **Step 1: Write failing tests for `HIGH` RR behavior**

Append to `tests/test_risk_manager.py`:

```python

class TestHighProfileAggressiveEntry:

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_high_profile_approves_tp_at_one_point_five_r(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.50
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(
            confidence=0.50,
            entry_price=2010.00,
            stop_loss=2006.00,
            take_profit_1=2016.00,
            risk_reward_to_tp1=1.5,
        )
        context = _make_context(point=0.01)

        result = evaluate_decision(decision, context)

        assert result["approved"] is True

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_high_profile_rejects_tp_below_one_point_five_r(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.50
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(
            confidence=0.50,
            entry_price=2010.00,
            stop_loss=2006.00,
            take_profit_1=2015.80,
            risk_reward_to_tp1=1.45,
        )
        context = _make_context(point=0.01)

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert "below minimum" in result["reason"] or "at least 1.5x" in result["reason"]
```

- [ ] **Step 2: Run tests to verify at least one fails**

Run: `pytest tests/test_risk_manager.py::TestHighProfileAggressiveEntry -v`

Expected: first test FAILS because hardcoded `2x SL` still rejects `1.5R` TP.

- [ ] **Step 3: Replace hardcoded `2.0` multiplier**

In `app/risk/risk_manager.py`, replace lines that enforce TP distance with:

```python
            if take_profit_1 is not None:
                tp_pips = abs(take_profit_1 - entry_price) / point / 10.0
                min_rr = settings.effective_min_risk_reward
                if tp_pips < sl_pips * min_rr:
                    checks["risk_reward_ok"] = False
                    return _reject(checks, f"TP ({tp_pips:.0f} pips) must be at least {min_rr:.1f}x SL ({sl_pips:.0f} pips)")
```

- [ ] **Step 4: Run risk-manager tests**

Run: `pytest tests/test_risk_manager.py -v`

Expected: PASS.

---

### Task 3: DeepSeek Prompt Includes Active Profile

**Files:**
- Modify: `app/ai_engine/prompt_builder.py`
- Create: `tests/test_prompt_builder.py`

- [ ] **Step 1: Write failing prompt tests**

Create `tests/test_prompt_builder.py`:

```python
import sys

sys.path.insert(0, r'C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade\ai-trading-executor')


def test_user_prompt_includes_active_profile_thresholds():
    from app.ai_engine.prompt_builder import build_user_prompt
    from app.config import settings

    original_profile = settings.risk_profile
    try:
        settings.risk_profile = "HIGH"

        prompt = build_user_prompt({"symbol": "XAUUSDm", "bid": 2010.0})

        assert "Risk profile: HIGH" in prompt
        assert "Minimum confidence: 50%" in prompt
        assert "Minimum R:R: 1.5" in prompt
    finally:
        settings.risk_profile = original_profile


def test_system_prompt_explains_high_profile_aggressive_entries():
    from app.ai_engine.prompt_builder import build_system_prompt

    prompt = build_system_prompt()

    assert "HIGH profile" in prompt
    assert "50-60%" in prompt
    assert "1.5R" in prompt
    assert "M15 momentum" in prompt
```

- [ ] **Step 2: Run prompt tests to verify failure**

Run: `pytest tests/test_prompt_builder.py -v`

Expected: FAIL because prompt does not include profile-specific thresholds yet.

- [ ] **Step 3: Update system prompt**

In `app/ai_engine/prompt_builder.py`, add this block before `Return only valid JSON.`:

```python
Risk profile behavior:
- LOW profile: conservative. Prefer only cleaner trades with at least 65% confidence and 2.0R.
- MEDIUM profile: balanced. Accept good scalping trades with at least 55% confidence and 1.5R.
- HIGH profile: aggressive. Accept 50-60% confidence setups when M15 momentum is clear and H1 is neutral or not strongly opposite. Minimum target is 1.5R.

For HIGH profile:
- Do not wait for perfect D1/H1/H4 alignment.
- Prefer MARKET or near-market entries when momentum is active.
- A 50% confidence BUY/SELL can be valid if M15 momentum has directional edge.
- HOLD only when no directional edge exists, data is missing, or H1 and M15 strongly conflict.
```

- [ ] **Step 4: Update user prompt with runtime thresholds**

In `app/ai_engine/prompt_builder.py`, import settings and replace `build_user_prompt` with:

```python
from app.config import settings


def build_user_prompt(market_payload: dict) -> str:
    payload_json = json.dumps(market_payload, indent=2)
    return (
        "Analyze the following market data and return a trading decision.\n\n"
        f"Risk profile: {settings.risk_profile}\n"
        f"Minimum confidence: {settings.effective_min_confidence:.0%}\n"
        f"Minimum R:R: {settings.effective_min_risk_reward:.1f}\n\n"
        f"Market data:\n{payload_json}"
    )
```

- [ ] **Step 5: Run prompt tests**

Run: `pytest tests/test_prompt_builder.py -v`

Expected: PASS.

---

### Task 4: Telegram Risk Button Resilience

**Files:**
- Modify: `app/telegram_bot/callbacks.py:501-516`
- Test: `tests/test_telegram_bot.py`

- [ ] **Step 1: Write failing callback test**

Append to `tests/test_telegram_bot.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


class FakeCallbackUpdate:
    def __init__(self):
        self.effective_chat = MagicMock(id="123")
        self.callback_query = MagicMock()
        self.callback_query.answer = AsyncMock()


@pytest.mark.asyncio
async def test_risk_callback_updates_runtime_profile_when_db_fails():
    from app.config import settings
    from app.telegram_bot.callbacks import menu_risk_callback

    original_chat_id = settings.telegram_allowed_chat_id
    original_profile = settings.risk_profile
    try:
        settings.telegram_allowed_chat_id = "123"
        settings.risk_profile = "LOW"
        update = FakeCallbackUpdate()

        with patch("app.database.repositories.update_bot_settings", side_effect=RuntimeError("db down")):
            with patch("app.telegram_bot.callbacks.send_main_menu", new=AsyncMock(return_value=True)):
                await menu_risk_callback(update, "HIGH")

        assert settings.risk_profile == "HIGH"
        update.callback_query.answer.assert_awaited()
    finally:
        settings.telegram_allowed_chat_id = original_chat_id
        settings.risk_profile = original_profile
```

- [ ] **Step 2: Run callback test to verify failure**

Run: `pytest tests/test_telegram_bot.py::test_risk_callback_updates_runtime_profile_when_db_fails -v`

Expected: FAIL because `update_bot_settings` exception exits callback.

- [ ] **Step 3: Catch Supabase persistence failure**

In `app/telegram_bot/callbacks.py`, replace risk callback persistence with:

```python
    settings.risk_profile = profile
    try:
        from app.database.repositories import update_bot_settings

        update_bot_settings({"risk_profile": profile})
    except Exception as e:
        logger.error(f"Failed to persist risk profile {profile}: {e}")

    labels = {"LOW": "Low Risk", "MEDIUM": "Medium Risk", "HIGH": "High Risk"}
    await query.answer(f"Profile: {labels.get(profile, profile)}")
    await send_main_menu()
```

- [ ] **Step 4: Run Telegram tests**

Run: `pytest tests/test_telegram_bot.py -v`

Expected: PASS.

---

### Task 5: Settings Copy Reflects Aggressive Profile

**Files:**
- Modify: `app/telegram_bot/message_templates.py:225-240`
- Test: existing assertions via full test suite.

- [ ] **Step 1: Update settings text**

In `format_settings_message`, replace the TP line:

```python
        f"<b>TP:</b> min {settings.effective_min_risk_reward:.1f}x SL\n"
```

Keep the `Min R:R` line unchanged.

- [ ] **Step 2: Run full tests**

Run: `pytest`

Expected: PASS.

---

### Task 6: Final Verification

**Files:**
- No new code files.

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_risk_manager.py tests/test_prompt_builder.py tests/test_telegram_bot.py -v`

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `pytest`

Expected: all tests pass.

- [ ] **Step 3: Manual runtime check after restart**

Run: `python run.py`

Expected startup logs include Telegram polling started.

In Telegram:

1. Send `/menu`.
2. Tap `High`.
3. Send `/settings`.
4. Confirm message shows `Risk Profile: HIGH`, `Min Confidence: 50%`, `Min R:R: 1.5`, and `TP: min 1.5x SL`.

---

## Self-Review Notes

- Spec coverage: thresholds, DeepSeek prompt, risk-manager RR, Telegram persistence, settings display, tests all mapped to tasks.
- Placeholder scan: no incomplete placeholder markers.
- Type consistency: uses existing `settings.effective_min_confidence`, `settings.effective_min_risk_reward`, `menu_risk_callback`, and pytest patterns from current test suite.
- Repo note: commit steps omitted because project folder is not currently a Git repository.
