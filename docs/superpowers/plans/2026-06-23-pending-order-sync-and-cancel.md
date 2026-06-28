# Pending Order Sync, Cap, and Cancel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Count pending orders in per-symbol cap, sync pending orders at startup, and cancel pending orders when AI direction flips.

**Architecture:** New `orders.py` module for MT5 pending order operations. Startup sync extended. Risk cap uses active + pending count. Execution service cancels opposite-direction pending orders before placing new order.

**Tech Stack:** Python, MetaTrader5, pytest, asyncio.

---

## File Structure

- Create: `app/mt5_connector/orders.py` — pending order helpers.
- Modify: `app/services/position_state_service.py` — pending order state sync.
- Modify: `app/main.py` — startup pending order sync call.
- Modify: `app/risk/risk_manager.py` — cap uses combined count.
- Modify: `app/services/signal_service.py` — pass combined count.
- Modify: `app/api/signals.py` — pass combined count.
- Modify: `app/services/trading_loop.py` — pass combined count in approve path.
- Modify: `app/telegram_bot/callbacks.py` — pass combined count in approve path.
- Modify: `app/services/execution_service.py` — cancel opposite pending before place.
- Test: `tests/test_orders.py` (new), `tests/test_risk_manager.py`, `tests/test_signal_service.py`, `tests/test_trading_loop.py`, `tests/test_telegram_bot.py`, `tests/test_position_state_service.py` (new or existing).

## Task 1: Create Pending Orders Module

**Files:**
- Create: `app/mt5_connector/orders.py`
- Test: `tests/test_orders.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_orders.py`:

```python
from unittest.mock import patch, MagicMock


def test_get_pending_orders_returns_empty_when_mt5_unavailable():
    from app.mt5_connector.orders import get_pending_orders

    with patch("app.mt5_connector.orders.mt5", None):
        result = get_pending_orders("XAUUSD")

    assert result == []


def test_get_pending_orders_count_returns_zero_when_no_orders():
    from app.mt5_connector.orders import get_pending_orders_count

    with patch("app.mt5_connector.orders.mt5") as mock_mt5:
        mock_mt5.orders_get.return_value = None
        result = get_pending_orders_count("XAUUSD")

    assert result == 0


def test_get_pending_orders_count_returns_count():
    from app.mt5_connector.orders import get_pending_orders_count

    orders = [MagicMock(), MagicMock(), MagicMock()]
    with patch("app.mt5_connector.orders.mt5") as mock_mt5:
        mock_mt5.orders_get.return_value = orders
        result = get_pending_orders_count("XAUUSD")

    assert result == 3


def test_cancel_pending_order_success():
    from app.mt5_connector.orders import cancel_pending_order

    with patch("app.mt5_connector.orders.mt5") as mock_mt5:
        mock_result = MagicMock()
        mock_result.retcode = mock_mt5.TRADE_RETCODE_DONE
        mock_mt5.order_send.return_value = mock_result
        result = cancel_pending_order(12345)

    assert result is True


def test_cancel_pending_order_failure():
    from app.mt5_connector.orders import cancel_pending_order

    with patch("app.mt5_connector.orders.mt5") as mock_mt5:
        mock_result = MagicMock()
        mock_result.retcode = 10013
        mock_mt5.order_send.return_value = mock_result
        result = cancel_pending_order(12345)

    assert result is False


def test_cancel_pending_orders_for_symbol_cancels_opposite_direction():
    from app.mt5_connector.orders import cancel_pending_orders_for_symbol

    order_buy = MagicMock()
    order_buy.ticket = 111
    order_buy.symbol = "XAUUSD"
    order_buy.type = MagicMock()
    order_buy.type.__eq__ = lambda self, other: other == "buy_limit"

    with patch("app.mt5_connector.orders.get_pending_orders", return_value=[order_buy]):
        with patch("app.mt5_connector.orders.mt5") as mock_mt5:
            mock_result = MagicMock()
            mock_result.retcode = mock_mt5.TRADE_RETCODE_DONE
            mock_mt5.order_send.return_value = mock_result
            result = cancel_pending_orders_for_symbol("XAUUSD", new_direction="SELL")

    assert result["cancelled"] == 1
    assert result["errors"] == 0


def test_cancel_pending_orders_for_symbol_keeps_same_direction():
    from app.mt5_connector.orders import cancel_pending_orders_for_symbol

    order_buy = MagicMock()
    order_buy.ticket = 111
    order_buy.type = MagicMock()

    with patch("app.mt5_connector.orders.get_pending_orders", return_value=[order_buy]) as mock_get:
        with patch("app.mt5_connector.orders._pending_order_side", return_value="BUY"):
            with patch("app.mt5_connector.orders.cancel_pending_order") as mock_cancel:
                result = cancel_pending_orders_for_symbol("XAUUSD", new_direction="BUY")

    assert result["cancelled"] == 0
    mock_cancel.assert_not_called()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_orders.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create orders module**

Create `app/mt5_connector/orders.py`:

```python
from typing import List, Optional

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    _MT5_AVAILABLE = False

from app.logger import logger


def _pending_order_side(order) -> str:
    try:
        order_type = int(getattr(order, "type", 0))
        if order_type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP):
            return "BUY"
        if order_type in (mt5.ORDER_TYPE_SELL_LIMIT, mt5.ORDER_TYPE_SELL_STOP):
            return "SELL"
    except Exception:
        pass
    return ""


def get_pending_orders(symbol: Optional[str] = None) -> List[dict]:
    try:
        if mt5 is None:
            return []
        orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
        if orders is None or len(orders) == 0:
            return []
        return [o._asdict() for o in orders]
    except Exception as e:
        logger.error(f"get_pending_orders exception: {e}")
        return []


def get_pending_orders_count(symbol: Optional[str] = None) -> int:
    try:
        if mt5 is None:
            return 0
        orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
        if orders is None:
            return 0
        return len(orders)
    except Exception as e:
        logger.error(f"get_pending_orders_count exception: {e}")
        return 0


def cancel_pending_order(ticket: int) -> bool:
    try:
        if mt5 is None:
            return False
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
        }
        result = mt5.order_send(request)
        if result is None:
            logger.error(f"cancel_pending_order returned None for ticket={ticket}")
            return False
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Pending order {ticket} cancelled")
            return True
        logger.error(f"cancel_pending_order failed: ticket={ticket}, retcode={result.retcode}, comment={result.comment}")
        return False
    except Exception as e:
        logger.error(f"cancel_pending_order exception: {e}")
        return False


def cancel_pending_orders_for_symbol(symbol: str, new_direction: str) -> dict:
    summary = {"symbol": symbol, "cancelled": 0, "errors": 0, "kept": 0}
    try:
        orders = get_pending_orders(symbol)
        new_dir = str(new_direction).upper()
        for order in orders:
            ticket = order.get("ticket")
            side = _pending_order_side(order)
            if side and side != new_dir:
                if cancel_pending_order(ticket):
                    summary["cancelled"] += 1
                else:
                    summary["errors"] += 1
            else:
                summary["kept"] += 1
        if summary["cancelled"] > 0:
            logger.info(f"Cancelled {summary['cancelled']} opposite pending orders for {symbol}")
    except Exception as e:
        logger.error(f"cancel_pending_orders_for_symbol exception: {e}")
        summary["errors"] += 1
    return summary
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_orders.py -q`
Expected: PASS.

- [ ] **Step 5: Commit policy**

Do not commit unless user explicitly asks.

## Task 2: Startup Pending Order Sync

**Files:**
- Modify: `app/services/position_state_service.py`
- Modify: `app/main.py`
- Test: `tests/test_position_state_service.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_position_state_service.py`:

```python
from unittest.mock import patch, MagicMock


def test_sync_pending_orders_stores_by_symbol():
    from app.services.position_state_service import sync_pending_orders_from_mt5, _PENDING_ORDER_STATE

    _PENDING_ORDER_STATE.clear()

    order = MagicMock()
    order.ticket = 123
    order.symbol = "XAUUSD"
    order.type = MagicMock()
    order.volume = 0.01
    order.price_open = 2000.0
    order.sl = 1990.0
    order.tp = 2020.0

    with patch("app.mt5_connector.orders.get_pending_orders", return_value=[order._asdict()]):
        summary = sync_pending_orders_from_mt5()

    assert summary["pending_orders"] == 1
    assert "XAUUSD" in _PENDING_ORDER_STATE
    assert _PENDING_ORDER_STATE["XAUUSD"][0]["ticket"] == 123
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_position_state_service.py -q`
Expected: FAIL — function does not exist.

- [ ] **Step 3: Add pending order state and sync function**

Add to `app/services/position_state_service.py`:

```python
_PENDING_ORDER_STATE: dict[str, list[dict]] = {}
```

Add function:

```python
def sync_pending_orders_from_mt5() -> dict:
    summary = {"pending_orders": 0, "errors": 0}
    _PENDING_ORDER_STATE.clear()

    try:
        from app.mt5_connector.orders import get_pending_orders

        orders = get_pending_orders(None)
        summary["pending_orders"] = len(orders)
    except Exception as e:
        logger.error(f"Failed to read MT5 pending orders during startup sync: {e}")
        summary["errors"] += 1
        return summary

    for order in orders:
        try:
            symbol = order.get("symbol")
            ticket = order.get("ticket")
            state = {
                "symbol": symbol,
                "ticket": ticket,
                "volume": order.get("volume"),
                "price_open": order.get("price_open"),
                "sl": order.get("sl"),
                "tp": order.get("tp"),
            }
            _PENDING_ORDER_STATE.setdefault(symbol, []).append(state)
        except Exception as e:
            logger.error(f"Failed to sync pending order state: {e}")
            summary["errors"] += 1

    logger.info(f"Startup pending order sync: {summary}")
    return summary
```

- [ ] **Step 4: Add startup call in main.py**

In `app/main.py`, after `sync_open_positions_from_mt5()` block, add:

```python
                try:
                    from app.services.position_state_service import sync_pending_orders_from_mt5

                    pending_sync = sync_pending_orders_from_mt5()
                    logger.info(f"Startup pending order sync complete: {pending_sync}")
                except Exception as e:
                    logger.error(f"Startup pending order sync failed: {e}")
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_position_state_service.py -q`
Expected: PASS.

## Task 3: Cap Includes Pending Orders

**Files:**
- Modify: `app/risk/risk_manager.py`
- Modify: `app/services/signal_service.py`
- Modify: `app/api/signals.py`
- Modify: `app/services/trading_loop.py`
- Modify: `app/telegram_bot/callbacks.py`
- Test: `tests/test_risk_manager.py`, `tests/test_signal_service.py`

- [ ] **Step 1: Write failing risk manager test**

Add to `tests/test_risk_manager.py` after existing per-symbol tests:

```python
    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_cap_rejects_when_active_plus_pending_exceeds_max(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 30
        mock_settings.max_positions_per_symbol = 5
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock()
        context = _make_context(positions=10)
        context["open_orders_count_symbol"] = 5

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["positions_per_symbol_ok"] is False
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_risk_manager.py::TestEvaluateDecision::test_cap_rejects_when_active_plus_pending_exceeds_max -q`
Expected: FAIL — `open_orders_count_symbol` not checked.

- [ ] **Step 3: Update risk manager to use combined count**

In `app/risk/risk_manager.py`, replace the per-symbol cap block:

```python
        open_positions_count_symbol = market_context.get("open_positions_count_symbol", 0)
        if open_positions_count_symbol >= settings.max_positions_per_symbol:
            checks["positions_per_symbol_ok"] = False
            return _reject(
                checks,
                f"{market_context.get('symbol', 'UNKNOWN')} positions ({open_positions_count_symbol}) "
                f"at or above per-symbol max ({settings.max_positions_per_symbol})",
            )
```

with:

```python
        open_orders_count_symbol = market_context.get(
            "open_orders_count_symbol",
            market_context.get("open_positions_count_symbol", 0),
        )
        if open_orders_count_symbol >= settings.max_positions_per_symbol:
            checks["positions_per_symbol_ok"] = False
            return _reject(
                checks,
                f"{market_context.get('symbol', 'UNKNOWN')} orders ({open_orders_count_symbol}) "
                f"at or above per-symbol max ({settings.max_positions_per_symbol})",
            )
```

- [ ] **Step 4: Update signal_service to pass combined count**

In `app/services/signal_service.py`, add import and combined count:

```python
        from app.mt5_connector.positions import get_open_positions_count, has_open_position
        from app.mt5_connector.orders import get_pending_orders_count
```

```python
        open_positions_count = get_open_positions_count(None)
        open_positions_count_symbol = get_open_positions_count(sym)
        pending_orders_count_symbol = get_pending_orders_count(sym)
        open_orders_count_symbol = open_positions_count_symbol + pending_orders_count_symbol
        has_open = open_positions_count_symbol > 0
```

Update `account_context` and `market_context` to include:

```python
            "open_orders_count_symbol": open_orders_count_symbol,
```

- [ ] **Step 5: Update API signals.py both paths**

In `app/api/signals.py` generate and approve paths, add:

```python
        from app.mt5_connector.orders import get_pending_orders_count
```

```python
        open_orders_count_symbol = open_positions_count_symbol + get_pending_orders_count(symbol)
```

And include `"open_orders_count_symbol": open_orders_count_symbol` in both `market_context` dicts.

- [ ] **Step 6: Update trading_loop approve path**

In `app/services/trading_loop.py::handle_approve_callback`, add:

```python
        from app.mt5_connector.orders import get_pending_orders_count
```

```python
            open_orders_count_symbol = open_positions_count_symbol + get_pending_orders_count(symbol)
```

Add `"open_orders_count_symbol": open_orders_count_symbol` to `market_context`.

- [ ] **Step 7: Update Telegram callback approve path**

In `app/telegram_bot/callbacks.py::approve_trade_callback`, add:

```python
        from app.mt5_connector.orders import get_pending_orders_count
```

```python
        open_orders_count_symbol = open_positions_count_symbol + get_pending_orders_count(symbol)
```

Add `"open_orders_count_symbol": open_orders_count_symbol` to `market_context`.

- [ ] **Step 8: Run focused tests**

Run: `pytest tests/test_risk_manager.py tests/test_signal_service.py tests/test_trading_loop.py tests/test_telegram_bot.py -q`
Expected: PASS.

## Task 4: Cancel Opposite Pending On Execution

**Files:**
- Modify: `app/services/execution_service.py`
- Test: `tests/test_execution_service.py` (if exists) or `tests/test_orders.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_orders.py`:

```python
def test_cancel_opposite_pending_called_in_execute_trade():
    from unittest.mock import patch, MagicMock
    from app.services.execution_service import execute_trade

    ai_decision = MagicMock()
    ai_decision.decision = "SELL"
    ai_decision.confidence = 0.8
    entry_plan = MagicMock()
    entry_plan.entry_type = MagicMock()
    entry_plan.entry_type.value = "MARKET"
    entry_plan.stop_loss = 2010.0
    entry_plan.take_profit_1 = 1990.0
    entry_plan.preferred_entry_price = None
    ai_decision.entry_plan = entry_plan

    risk_result = {"symbol": "XAUUSD", "approved": True}

    with patch("app.services.execution_service.select_smc_limit_entry", return_value={"valid": False}):
        with patch("app.services.execution_service.can_use_market_fallback", return_value=True):
            with patch("app.services.execution_service.calculate_lot_size", return_value={"is_valid": True, "lot": 0.01}):
                with patch("app.services.execution_service.build_order_request", return_value={"action": 1}):
                    with patch("app.services.execution_service.check_order", return_value={"retcode": 0}):
                        with patch("app.services.execution_service.send_order", return_value={"retcode": 10009, "order": 999, "price": 2000.0}):
                            with patch("app.services.execution_service.save_trade", return_value={"id": "t1"}):
                                with patch("app.services.execution_service.log_bot_event"):
                                    with patch("app.mt5_connector.orders.cancel_pending_orders_for_symbol") as mock_cancel:
                                        result = execute_trade(ai_decision, risk_result, {"digits": 5, "point": 0.01}, 10000.0, 2000.0, 2001.0, None)

    mock_cancel.assert_called_once_with("XAUUSD", "SELL")
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_orders.py::test_cancel_opposite_pending_called_in_execute_trade -q`
Expected: FAIL — cancel not called.

- [ ] **Step 3: Add cancel call in execute_trade**

In `app/services/execution_service.py::execute_trade`, after `decision_str` is resolved and before order build loop, add:

```python
    try:
        from app.mt5_connector.orders import cancel_pending_orders_for_symbol

        cancel_summary = cancel_pending_orders_for_symbol(sym, decision_str)
        if cancel_summary.get("cancelled", 0) > 0:
            logger.info(f"Cancelled {cancel_summary['cancelled']} opposite pending orders for {sym} before new {decision_str}")
    except Exception as e:
        logger.error(f"Failed to cancel opposite pending orders for {sym}: {e}")
```

Place this right after the `is_buy` assignment and before `digits`.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_orders.py::test_cancel_opposite_pending_called_in_execute_trade -q`
Expected: PASS.

## Task 5: Full Verification

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run full test suite**

Run: `pytest -q`
Expected: PASS with existing Supabase deprecation warnings only.

- [ ] **Step 2: Inspect diff**

Run: `git diff --stat`
Expected: only pending order sync/cap/cancel files changed.

- [ ] **Step 3: Commit policy**

Do not commit unless user explicitly asks. If user requests commit/push, first run:

```bash
pytest -q
git status --short
git diff --stat
```
