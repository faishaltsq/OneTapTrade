# Telegram Risk Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telegram buttons to control both `risk_profile` and `risk_per_trade_percent` at runtime.

**Architecture:** Extend existing Telegram menu/callback pattern with a settings-specific inline keyboard and new risk/trade callbacks. Keep runtime setting changes in `settings`, persist through `update_bot_settings`, and use tests around keyboard callback data plus callback behavior.

**Tech Stack:** Python 3.13, pytest, python-telegram-bot inline keyboards, current Supabase repository wrapper.

---

## File Structure

- Modify: `app/telegram_bot/message_templates.py` — add `build_settings_keyboard` and keep settings text.
- Modify: `app/telegram_bot/commands.py` — `/settings` replies with risk settings keyboard.
- Modify: `app/telegram_bot/callbacks.py` — settings view uses settings keyboard; add risk/trade percent callbacks.
- Modify: `app/database/repositories.py` — allow `risk_profile` persistence.
- Modify: `tests/test_telegram_bot.py` — test keyboard and callback runtime behavior.
- Create: `tests/test_repositories.py` — test `update_bot_settings` forwards `risk_profile`.

---

### Task 1: Settings Keyboard

**Files:**
- Modify: `app/telegram_bot/message_templates.py`
- Test: `tests/test_telegram_bot.py`

- [ ] **Step 1: Write failing keyboard test**

Append a test asserting callback data exists: `MENU_RISK_LOW`, `MENU_RISK_MEDIUM`, `MENU_RISK_HIGH`, `MENU_RISK_TRADE_025`, `MENU_RISK_TRADE_050`, `MENU_RISK_TRADE_100`.

- [ ] **Step 2: Run test**

Run: `pytest tests/test_telegram_bot.py::test_settings_keyboard_contains_risk_controls -v`

Expected: FAIL because `build_settings_keyboard` does not exist.

- [ ] **Step 3: Implement keyboard**

Add `build_settings_keyboard()` returning inline rows: profile buttons, risk/trade buttons, back-to-menu button.

- [ ] **Step 4: Run test**

Run: `pytest tests/test_telegram_bot.py::test_settings_keyboard_contains_risk_controls -v`

Expected: PASS.

---

### Task 2: `/settings` Uses Keyboard

**Files:**
- Modify: `app/telegram_bot/commands.py`
- Test: `tests/test_telegram_bot.py`

- [ ] **Step 1: Write failing command behavior test**

Add a lightweight fake `Update` whose `message.reply_text` is an `AsyncMock`; call `settings_command`; assert `reply_markup` is passed.

- [ ] **Step 2: Run test**

Run: `pytest tests/test_telegram_bot.py::test_settings_command_sends_keyboard -v`

Expected: FAIL because current command does not pass `reply_markup`.

- [ ] **Step 3: Implement command keyboard**

Import `build_settings_keyboard` and send it in `settings_command`.

- [ ] **Step 4: Run test**

Run: `pytest tests/test_telegram_bot.py::test_settings_command_sends_keyboard -v`

Expected: PASS.

---

### Task 3: Risk/Trade Callback

**Files:**
- Modify: `app/telegram_bot/callbacks.py`
- Test: `tests/test_telegram_bot.py`

- [ ] **Step 1: Write failing callbacks tests**

Add tests for valid risk/trade values updating `settings.risk_per_trade_percent` and invalid value rejecting without change.

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_telegram_bot.py::test_risk_trade_callback_updates_runtime_percent tests/test_telegram_bot.py::test_risk_trade_callback_rejects_invalid_percent -v`

Expected: FAIL because callback does not exist.

- [ ] **Step 3: Implement callback**

Add `menu_risk_trade_callback(update, percent)` with allowed values `{0.25, 0.5, 1.0}`, runtime update, Supabase persistence try/except, answer, and refreshed settings message.

- [ ] **Step 4: Register handlers**

Add callback patterns for `MENU_RISK_TRADE_025`, `MENU_RISK_TRADE_050`, `MENU_RISK_TRADE_100`.

- [ ] **Step 5: Run Telegram tests**

Run: `pytest tests/test_telegram_bot.py -v`

Expected: PASS.

---

### Task 4: Supabase Allow-List Persists Risk Profile

**Files:**
- Modify: `app/database/repositories.py`
- Test: `tests/test_repositories.py`

- [ ] **Step 1: Write failing repository test**

Create fake Supabase client/table chain. Patch `get_supabase` and `get_bot_settings`; call `update_bot_settings({"risk_profile": "HIGH"})`; assert update receives `{"risk_profile": "HIGH"}`.

- [ ] **Step 2: Run test**

Run: `pytest tests/test_repositories.py -v`

Expected: FAIL because allow-list filters `risk_profile` out.

- [ ] **Step 3: Add allow-list field**

Add `risk_profile` to `allowed` in `update_bot_settings`.

- [ ] **Step 4: Run repository test**

Run: `pytest tests/test_repositories.py -v`

Expected: PASS.

---

### Task 5: Final Verification

**Files:**
- No new application files.

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/test_telegram_bot.py tests/test_repositories.py -v`

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `pytest`

Expected: PASS.

---

## Self-Review Notes

- Spec coverage: profile buttons, risk/trade buttons, runtime update, persistence, invalid callbacks, settings display all covered.
- Placeholder scan: no incomplete placeholder markers.
- Scope: no live-trading behavior or drawdown/max-position changes.
