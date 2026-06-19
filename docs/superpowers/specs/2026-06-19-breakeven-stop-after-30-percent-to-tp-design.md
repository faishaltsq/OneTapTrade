# Breakeven Stop After 30% To TP Design

## Goal

Automatically move stop loss to break-even when an open position reaches 30% progress from entry price to take profit.

## Scope

- Applies to all live MT5 open positions, including positions that already exist after server restart.
- Runs automatically during each trading loop cycle before new signal generation.
- Uses the position's existing `price_open`, `sl`, `tp`, `type`, and latest tick.
- Moves SL to `price_open` only once the threshold is reached.
- Keeps existing TP unchanged.

## Breakeven Rule

For BUY positions:

- Progress threshold = `price_open + ((tp - price_open) * 0.30)`.
- If current bid is greater than or equal to threshold, set SL to `price_open`.

For SELL positions:

- Progress threshold = `price_open - ((price_open - tp) * 0.30)`.
- If current ask is less than or equal to threshold, set SL to `price_open`.

## Skip Rules

Skip a position when:

- It has no TP.
- It has no entry price.
- BUY position already has SL at or above break-even.
- SELL position already has SL at or below break-even.
- Latest tick is unavailable.
- MT5 rejects the SL/TP modification.

## Architecture

- Add MT5 helper `move_stop_loss_to_breakeven(position)` using `TRADE_ACTION_SLTP`.
- Add service helper `manage_breakeven_stops()` that fetches open positions, evaluates thresholds, and calls the MT5 helper.
- Call `manage_breakeven_stops()` once at the start of each trading loop `run_once()` before symbol analysis.
- Log each skipped, attempted, and successful breakeven move.

## Error Handling

- MT5 errors are logged and do not stop the trading loop.
- One failed position does not block checks for other positions.
- If MT5 is disconnected, breakeven management returns a failed summary and trading loop continues existing behavior.

## Tests

- BUY reaches 30% to TP and requests SL move to entry.
- SELL reaches 30% to TP and requests SL move to entry.
- Position below threshold does not modify SL.
- Position already protected does not modify SL.
- Trading loop calls breakeven management before symbol analysis.
