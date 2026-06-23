# Pending Order Cap And Startup Validation Design

## Goal

Limit pending orders to max 5 per symbol, auto-cancel lowest-probability orders when exceeded, and validate both pending orders and open positions on restart against D1 trend and SMC zone validity.

## Scope

- Enforce `max_positions_per_symbol=5` (already in config) as a hard cap on pending orders per symbol.
- When pending orders exceed cap, cancel lowest SMC-score orders.
- On startup, validate pending orders against D1 trend and SMC zone validity; remove invalid.
- On startup, validate open positions against D1 trend; warn if misaligned but do not force-close.
- Run validation in trading loop before each new signal to keep state fresh.

## Current State

- `config.py` already has `max_positions_per_symbol=5`.
- `app/mt5_connector/orders.py` already has `get_pending_orders()`, `cancel_pending_order()`, and `cancel_pending_orders_for_symbol()`.
- `app/services/position_state_service.py` already syncs pending orders on startup via `sync_pending_orders_from_mt5()`.
- `app/analysis/smc_entry_selector.py` already scores SMC zones.
- No cap enforcement exists yet.
- No startup validation of pending order alignment or open position alignment exists yet.

## Pending Order Cap

### Trigger

After every successful pending order placement in `execution_service.py`, call a new cap enforcement function.

Also call it at the start of each trading loop cycle for each symbol.

### Logic

Create `app/services/pending_order_manager.py`:

```python
def enforce_pending_order_cap(symbol: str, max_orders: int = 5) -> dict:
    ...
```

Steps:
1. Get all pending orders for `symbol` from MT5.
2. If count <= max_orders, return early.
3. If count > max_orders, score each order:
   - Re-derive SMC zone validity: is entry price still inside a valid demand OB (BUY) or supply OB (SELL)?
   - Score by distance from current price (closer = higher) and zone validity.
   - Orders with invalid zone get score 0.
4. Sort by score ascending (lowest first).
5. Cancel orders until count == max_orders.
6. Return summary with cancelled tickets.

### Scoring

Reuse a simplified version of `smc_entry_selector._score_zone` logic:
- Valid zone inside OB: base score 0.50.
- Closer to current price: +0.20.
- D1 alignment: +0.10.
- Invalid zone: 0.0.

## Startup Validation

### Pending Orders

Create `app/services/pending_order_manager.py`:

```python
def validate_pending_orders_on_startup() -> dict:
    ...
```

Steps:
1. Get all pending orders from MT5.
2. Get D1 trend for each symbol's pending orders.
3. For each pending order:
   - Check direction aligns with D1 allowed directions.
   - Check entry price is still inside a valid OB zone.
   - If either check fails, cancel the order.
4. Return summary.

### Open Positions

Create `app/services/pending_order_manager.py`:

```python
def validate_open_positions_on_startup() -> dict:
    ...
```

Steps:
1. Get all open positions from MT5.
2. Get D1 trend for each symbol.
3. For each position:
   - Check direction aligns with D1 allowed directions.
   - Check SL and TP are not zero and not absurdly far.
   - If misaligned, log warning and collect for Telegram notification.
   - Do NOT force-close.
4. Return summary with any warnings.

### Integration

In `main.py` after `sync_pending_orders_from_mt5()`:
1. Call `validate_pending_orders_on_startup()`.
2. Call `validate_open_positions_on_startup()`.
3. Log both summaries.
4. If position warnings exist, send Telegram notification.

In `trading_loop.py` `run_once()` before symbol loop:
1. Call `enforce_pending_order_cap()` for each configured symbol.

## Data Needed

Validation needs D1 candle data and SMC payload. Reuse existing `feature_builder` or call `get_candles(symbol, "D1", count=50)` + `build_smc_section(df_h1, df_m5)` directly.

To keep startup simple and avoid full payload rebuild, D1 trend can use `build_major_trend_section(df_d1, None)` directly.

SMC zones for pending order validation use `build_smc_section(df_h1, df_m5)`.

## Tests

- `enforce_pending_order_cap` cancels lowest-score orders when >5.
- `enforce_pending_order_cap` does nothing when <=5.
- `validate_pending_orders_on_startup` cancels order with wrong D1 direction.
- `validate_pending_orders_on_startup` cancels order with entry outside OB.
- `validate_pending_orders_on_startup` keeps valid order.
- `validate_open_positions_on_startup` warns on wrong D1 direction but does not close.
- `validate_open_positions_on_startup` passes valid position.

## Non-Goals

- Do not force-close misaligned open positions.
- Do not add new database columns.
- Do not change AI schema.
- Do not change pending order creation logic in execution service beyond calling cap enforcement.
- Do not implement order expiration.

## Self-Review

- Placeholder scan: no TBD/TODO.
- Internal consistency: cap, startup validation, and loop enforcement all use same scoring and D1 logic.
- Scope check: focused on pending order cap and startup validation only.
- Ambiguity check: "low probability" is explicitly SMC zone validity + distance, not AI confidence.
