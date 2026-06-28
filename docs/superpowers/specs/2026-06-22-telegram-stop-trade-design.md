# Telegram Stop Trade Design

## Goal

Add clear Telegram menu controls to stop and resume new trading activity without closing existing positions.

## Scope

- Stop Trade blocks new analysis/trade cycles by using the existing paused state.
- Resume Trade clears the paused state and lets the trading loop continue.
- Existing open positions remain untouched.
- Existing `/pause` and `/resume` commands keep working.
- No new execution mode is introduced.

## User Experience

The main Telegram menu shows one stateful control:

- Running state: `🛑 Stop Trade`
- Stopped state: `▶️ Resume Trade`

Status text uses trading language instead of pause language:

- Stopped: `TRADING STOPPED`
- Running: `Trading Running`

## Architecture

Reuse the current pause mechanism:

- `TradingLoop.set_paused(True)` stops new cycles.
- `TradingLoop.set_paused(False)` resumes new cycles.
- `BotStatusService.is_paused` remains the source of truth.
- Database persistence continues through existing `set_paused()` repository call.

The callback can keep `MENU_TOGGLE_PAUSE` internally, but labels and user-facing messages should say Stop Trade / Resume Trade.

## Data Flow

1. User clicks `🛑 Stop Trade`.
2. Callback toggles paused state to `True`.
3. Trading loop skips future symbol cycles.
4. User clicks `▶️ Resume Trade`.
5. Callback toggles paused state to `False`.
6. Trading loop continues on next cycle.

## Error Handling

If trading loop is unavailable, callback returns a failure alert and does not pretend the state changed.

## Testing

- Main menu button label is `🛑 Stop Trade` when not paused.
- Main menu button label is `▶️ Resume Trade` when paused.
- Toggle callback sets paused state and persists it.
- Status message shows stopped/running wording.

## Out Of Scope

- Closing open positions.
- Cancelling pending orders.
- Stopping Telegram bot polling.
- Adding a new persistent setting separate from paused state.
