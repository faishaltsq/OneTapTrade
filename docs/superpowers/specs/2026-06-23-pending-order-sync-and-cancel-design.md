# Pending Order Sync, Cap, and Cancel Design

## Goal

Prevent pending order accumulation per pair by counting pending orders in the per-symbol cap, syncing pending orders at startup, and cancelling stale pending orders when AI direction flips.

## Problem

- `max_positions_per_symbol=5` only counts active positions (`mt5.positions_get()`).
- Pending LIMIT orders are never counted (`mt5.orders_get()` not called).
- Each cycle, AI says BUY_LIMIT in OB zone, risk manager sees 0 active positions, approves again, pending orders pile up (observed: 11 XAGUSD).
- Startup sync only reads positions, not pending orders.

## Scope

- Count active positions + pending orders together for per-symbol cap.
- Sync pending orders at startup into internal state and log.
- Cancel pending orders for a symbol when AI decision direction flips from the pending order direction.
- Keep existing pending orders when AI direction matches.
- Cancel uses MT5 `TRADE_ACTION_REMOVE` on pending order ticket.

## Architecture

### New module: `app/mt5_connector/orders.py`

Pending order helpers using `mt5.orders_get()` and `mt5.order_send(TRADE_ACTION_REMOVE)`.

Functions:
- `get_pending_orders(symbol=None) -> List[dict]`
- `get_pending_orders_count(symbol=None) -> int`
- `cancel_pending_order(ticket) -> bool`
- `cancel_pending_orders_for_symbol(symbol) -> dict`

### Startup sync

`app/main.py` lifespan: after `sync_open_positions_from_mt5()`, also call `sync_pending_orders_from_mt5()`.

`app/services/position_state_service.py`: add `_PENDING_ORDER_STATE` dict and `sync_pending_orders_from_mt5()` that reads `get_pending_orders(None)` and stores by symbol.

### Per-symbol cap includes pending

`risk_manager.py`: `open_orders_count_symbol` = active positions + pending orders. Reject when `>= max_positions_per_symbol`.

All risk context paths pass `open_orders_count_symbol` instead of `open_positions_count_symbol`:
- `signal_service.py`
- `app/api/signals.py`
- `app/services/trading_loop.py`
- `app/telegram_bot/callbacks.py`

### Cancel on direction flip

Before placing a new order in `trading_loop._run_symbol()` or `execution_service`:
1. Get pending orders for symbol.
2. Determine pending order direction: BUY_LIMIT/BUY_STOP = BUY, SELL_LIMIT/SELL_STOP = SELL.
3. If pending direction != AI decision direction → cancel those pending orders.
4. Log each cancellation.
5. Proceed with new order placement.

## Data Flow

```
startup:
  mt5.positions_get() → sync positions (existing)
  mt5.orders_get() → sync pending orders (new)

each cycle per symbol:
  active = get_open_positions_count(symbol)
  pending = get_pending_orders_count(symbol)
  total = active + pending
  if total >= max_positions_per_symbol → reject

before place new order:
  pending_orders = get_pending_orders(symbol)
  for each pending:
    if pending.direction != ai_decision.direction:
      cancel_pending_order(ticket)
  place new order
```

## Behavior

- XAGUSD has 3 active positions + 2 pending BUY_LIMIT = 5 total → new BUY_LIMIT rejected.
- XAGUSD has 2 active + 2 pending BUY_LIMIT, AI says SELL → cancel 2 BUY_LIMIT, place SELL.
- XAGUSD has 2 active + 2 pending BUY_LIMIT, AI says BUY → keep pending, place new if under cap.
- Startup: pending orders logged and tracked in internal state.

## Error Handling

- `mt5.orders_get()` returns None → treat as 0 pending, log warning.
- `cancel_pending_order` fails → log error, continue with next order.
- Startup sync failure does not block bot startup.

## Testing

- `orders.py`: get pending orders, count, cancel single, cancel by symbol.
- `position_state_service`: sync pending orders into state.
- `risk_manager`: reject when active + pending >= cap.
- `trading_loop`: cancel pending on direction flip before new order.
- `signal_service`: pass combined count in risk context.
- Startup sync integration test.

## Out Of Scope

- Cancelling pending orders based on price distance from OB zone.
- Cancelling all pending orders on every new cycle.
- Pending order expiry timers.
- Telegram UI for viewing/cancelling pending orders manually.
