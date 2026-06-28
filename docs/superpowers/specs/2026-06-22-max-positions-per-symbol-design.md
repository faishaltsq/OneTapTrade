# Max Positions Per Symbol Design

## Goal

Limit active MT5 positions per trading pair to prevent one symbol from consuming too much account exposure. Default cap is 5 active positions per symbol.

## Scope

- Count active/open positions only.
- Do not count pending orders.
- Count BUY and SELL positions together for the same symbol.
- Keep existing global `MAX_OPEN_POSITIONS` behavior.
- Keep existing opposite-direction block behavior.

## Architecture

Add a per-symbol position cap to the existing risk gate. The signal pipeline already gathers global open-position count before risk evaluation. It will also gather symbol-specific open-position count and pass it into `market_context`.

`risk_manager.evaluate_decision()` will reject non-HOLD trade decisions when `open_positions_count_symbol >= settings.max_positions_per_symbol`.

## Configuration

Add `MAX_POSITIONS_PER_SYMBOL` to settings with default value `5`.

This keeps the requested behavior as default while allowing future tuning without code changes.

## Data Flow

1. Signal service receives target symbol.
2. Signal service calls `get_open_positions_count(symbol)`.
3. Signal service stores result in `market_context["open_positions_count_symbol"]`.
4. Risk manager compares count to `settings.max_positions_per_symbol`.
5. If count is at or above cap, risk manager rejects with clear reason.

## Behavior

- If `XAUUSD` has 5 active positions, another `XAUUSD` trade is rejected.
- If `XAUUSD` has 4 active positions, another `XAUUSD` trade can pass this specific check.
- If `BTCUSD` has 0 active positions, `BTCUSD` is unaffected by `XAUUSD` count.
- Pending LIMIT orders are ignored by this cap.
- Existing opposite-direction logic still blocks opening opposite side on same symbol.

## Error Handling

If MT5 position lookup fails, existing helper returns `0`. The new flow keeps that behavior and does not add a hard failure path.

## Testing

- Add risk-manager test for rejection when per-symbol active positions equal the cap.
- Add risk-manager test that global and per-symbol caps remain independent.
- Add signal-service test to confirm symbol-specific count is placed in market context.
- Run existing test suite to guard strategy mode, SMC LIMIT, Telegram, and trading-loop behavior.

## Out Of Scope

- Counting pending orders.
- Per-direction caps.
- Telegram UI for changing this value.
- Supabase persistence for this setting.
