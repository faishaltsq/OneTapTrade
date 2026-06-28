# Telegram Stop Trade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename Telegram pause/resume controls into clear Stop Trade / Resume Trade controls that stop new trades without closing open positions.

**Architecture:** Reuse existing paused state and `MENU_TOGGLE_PAUSE` callback. Update user-facing labels/status/command copy only; no new persistent state or execution mode.

**Tech Stack:** Python, python-telegram-bot inline keyboards, pytest.

---

## File Structure

- Modify `app/telegram_bot/message_templates.py`: main menu button label and status wording.
- Modify `app/telegram_bot/callbacks.py`: callback answer wording and status menu wording if needed.
- Modify `app/telegram_bot/commands.py`: `/pause` and `/resume` response copy.
- Modify `tests/test_telegram_bot.py`: button label and status wording tests.

## Task 1: Main Menu Stop/Resume Labels

**Files:**
- Modify: `app/telegram_bot/message_templates.py:29-55`
- Test: `tests/test_telegram_bot.py`

- [ ] **Step 1: Add failing tests**

Add tests to `tests/test_telegram_bot.py`:

```python
def _keyboard_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_main_menu_shows_stop_trade_when_running():
    from app.telegram_bot.message_templates import build_main_menu_keyboard

    texts = _keyboard_texts(build_main_menu_keyboard(is_paused=False))

    assert "🛑 Stop Trade" in texts
    assert "⏸️ Pause" not in texts


def test_main_menu_shows_resume_trade_when_stopped():
    from app.telegram_bot.message_templates import build_main_menu_keyboard

    texts = _keyboard_texts(build_main_menu_keyboard(is_paused=True))

    assert "▶️ Resume Trade" in texts
    assert "▶️ Resume" not in texts
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_telegram_bot.py::test_main_menu_shows_stop_trade_when_running tests/test_telegram_bot.py::test_main_menu_shows_resume_trade_when_stopped -q`

Expected: FAIL because labels still use Pause/Resume.

- [ ] **Step 3: Update main menu label**

Change `pause_btn` in `app/telegram_bot/message_templates.py`:

```python
    pause_btn = InlineKeyboardButton(
        "▶️ Resume Trade" if is_paused else "🛑 Stop Trade",
        callback_data="MENU_TOGGLE_PAUSE",
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_telegram_bot.py::test_main_menu_shows_stop_trade_when_running tests/test_telegram_bot.py::test_main_menu_shows_resume_trade_when_stopped -q`

Expected: PASS.

## Task 2: Status And Callback Wording

**Files:**
- Modify: `app/telegram_bot/message_templates.py:120-154`
- Modify: `app/telegram_bot/callbacks.py:343-358`
- Modify: `app/telegram_bot/callbacks.py:429-453`
- Modify: `app/telegram_bot/commands.py:146-190`
- Test: `tests/test_telegram_bot.py`

- [ ] **Step 1: Add failing status test**

Add test to `tests/test_telegram_bot.py`:

```python
def test_status_message_uses_stop_trade_wording():
    from app.telegram_bot.message_templates import format_status_message

    stopped = format_status_message({"paused": True, "mode": "AUTO_DEMO", "symbol": "XAUUSD"})
    running = format_status_message({"paused": False, "mode": "AUTO_DEMO", "symbol": "XAUUSD"})

    assert "TRADING STOPPED" in stopped
    assert "TRADING PAUSED" not in stopped
    assert "Trading Running" in running
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_telegram_bot.py::test_status_message_uses_stop_trade_wording -q`

Expected: FAIL because status still says `TRADING PAUSED` and running status has no `Trading Running` line.

- [ ] **Step 3: Update status formatter**

In `format_status_message()` replace paused block with:

```python
    if paused:
        lines.append("\n🛑 <b>TRADING STOPPED</b>")
    else:
        lines.append("\n▶️ <b>Trading Running</b>")
```

- [ ] **Step 4: Update menu status callback wording**

In `menu_status_callback()`, change the mode/status line to:

```python
    lines.append(f"<b>Mode:</b> {mode} | {'🛑 Stopped' if paused else '▶️ Trading Running'}")
```

- [ ] **Step 5: Update toggle answer wording**

In `menu_toggle_pause_callback()`, change query answer to:

```python
            await query.answer("Stop Trade active" if not current else "Resume Trade active")
```

- [ ] **Step 6: Update command response copy**

In `pause_command()`, update reply/log wording:

```python
    await _reply(update, "<b>🛑 Stop Trade active. New trades are stopped.</b>")
    logger.info("Stop Trade activated via Telegram command")
```

In `resume_command()`, update reply/log wording:

```python
    await _reply(update, "<b>▶️ Resume Trade active. New trades can continue.</b>")
    logger.info("Resume Trade activated via Telegram command")
```

- [ ] **Step 7: Run focused tests**

Run: `pytest tests/test_telegram_bot.py -q`

Expected: PASS.

## Task 3: Full Verification

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run full test suite**

Run: `pytest -q`

Expected: PASS with existing Supabase deprecation warnings only.

- [ ] **Step 2: Inspect diff**

Run: `git diff -- app/telegram_bot/message_templates.py app/telegram_bot/callbacks.py app/telegram_bot/commands.py tests/test_telegram_bot.py docs/superpowers/specs/2026-06-22-telegram-stop-trade-design.md docs/superpowers/plans/2026-06-22-telegram-stop-trade.md`

Expected: diff only changes stop/resume Telegram wording, tests, and docs.

- [ ] **Step 3: Commit policy**

Do not commit unless user explicitly asks. If user requests commit/push, first run:

```bash
pytest -q
git status --short
git diff --stat
```
