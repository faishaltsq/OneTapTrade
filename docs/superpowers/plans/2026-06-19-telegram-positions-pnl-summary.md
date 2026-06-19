# Telegram Positions P&L Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show floating P&L, today's realized P&L, and today's total P&L in `/positions` and the Telegram `Positions` button.

**Architecture:** Add a focused MT5 helper for today's realized P&L. Keep floating P&L calculation in the Telegram formatter because it already receives open positions. Wire both command and callback through the same formatter.

**Tech Stack:** Python, MetaTrader5 Python API, pytest, python-telegram-bot.

---

## File Structure

- Modify `app/mt5_connector/positions.py`: add `get_today_realized_pnl(symbol=None)` helper using `mt5.history_deals_get`.
- Modify `app/telegram_bot/message_templates.py`: update `format_positions_message(positions, symbol, realized_pnl=0.0)` to render summary totals.
- Modify `app/telegram_bot/commands.py`: `/positions` fetches realized P&L and passes it to formatter.
- Modify `app/telegram_bot/callbacks.py`: `Positions` button fetches realized P&L and passes it to formatter.
- Modify `tests/test_telegram_bot.py`: formatter regression tests.
- Add/modify `tests/test_positions.py`: MT5 realized P&L helper tests.

### Task 1: Formatter P&L Summary

**Files:**
- Modify: `app/telegram_bot/message_templates.py`
- Test: `tests/test_telegram_bot.py`

- [ ] **Step 1: Write failing formatter tests**

Add tests that call `format_positions_message(positions, "ALL", realized_pnl=3.25)` and assert:
- `Floating P&amp;L: $+7.50`
- `Today Realized P&amp;L: $+3.25`
- `Today Total P&amp;L: $+10.75`

Also add empty positions test asserting realized and total still render.

- [ ] **Step 2: Run formatter tests red**

Run: `pytest tests/test_telegram_bot.py -v`

Expected: FAIL because `format_positions_message` does not accept `realized_pnl`.

- [ ] **Step 3: Implement formatter update**

Change signature to `format_positions_message(positions: list, symbol: str, realized_pnl: float = 0.0) -> str`.

Calculate:
```python
floating_pnl = sum((pos.get("profit", 0) or 0) + (pos.get("swap", 0) or 0) for pos in positions)
today_total_pnl = floating_pnl + realized_pnl
```

Render summary before position rows and also for empty positions.

- [ ] **Step 4: Run formatter tests green**

Run: `pytest tests/test_telegram_bot.py -v`

Expected: PASS.

### Task 2: MT5 Realized P&L Helper

**Files:**
- Modify: `app/mt5_connector/positions.py`
- Test: `tests/test_positions.py`

- [ ] **Step 1: Write failing helper test**

Patch `app.mt5_connector.positions.mt5.history_deals_get` to return namedtuple-like deals with:
- closed buy/sell deal for `XAUUSD.c` with `profit=10`, `swap=-1`, `commission=-0.5`
- another deal for `EURUSD.c` ignored when symbol filter is `XAUUSD.c`

Assert `get_today_realized_pnl("XAUUSD.c") == 8.5`.

- [ ] **Step 2: Run helper tests red**

Run: `pytest tests/test_positions.py -v`

Expected: FAIL because helper is missing.

- [ ] **Step 3: Implement helper**

Add `get_today_realized_pnl(symbol: Optional[str] = None) -> float`.

Use local day start and `datetime.now()`:
```python
start = datetime.combine(datetime.now().date(), time.min)
deals = mt5.history_deals_get(start, datetime.now())
```

Sum `profit + swap + commission`, filtered by `symbol` when provided. Return `0.0` on errors.

- [ ] **Step 4: Run helper tests green**

Run: `pytest tests/test_positions.py -v`

Expected: PASS.

### Task 3: Wire Command And Button

**Files:**
- Modify: `app/telegram_bot/commands.py`
- Modify: `app/telegram_bot/callbacks.py`
- Test: existing formatter/helper tests plus full suite.

- [ ] **Step 1: Update command imports and calls**

In `/positions`, import `get_today_realized_pnl`, call it with `None`, and pass `realized_pnl` to `format_positions_message`.

- [ ] **Step 2: Update button callback imports and calls**

In `menu_positions_callback`, import `get_today_realized_pnl`, call it with `None`, and pass `realized_pnl` to `format_positions_message`.

- [ ] **Step 3: Run targeted tests**

Run: `pytest tests/test_telegram_bot.py tests/test_positions.py -v`

Expected: PASS.

- [ ] **Step 4: Run full verification**

Run: `pytest`

Expected: all tests pass.

## Self-Review

- Spec coverage: floating, realized, total P&L are covered by Tasks 1-3.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: `realized_pnl` is float across helper, formatter, command, and callback.
