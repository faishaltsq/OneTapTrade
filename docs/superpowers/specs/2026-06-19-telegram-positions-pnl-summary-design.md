# Telegram Positions P&L Summary Design

## Goal

Show P&L summary when user opens `/positions` or taps the `Positions` menu button.

## Scope

- Show floating P&L from currently open MT5 positions.
- Show today's realized P&L from MT5 closed deals.
- Show today's total P&L as realized plus floating.
- Keep existing per-position P&L rows.
- If no open positions exist, still show today's realized and total P&L.

## Data Flow

1. Telegram `/positions` and `Positions` button call `get_open_positions(None)`.
2. They call a new MT5 helper to calculate today's realized P&L from history deals.
3. Message formatter calculates floating P&L from positions using `profit + swap`.
4. Formatter renders floating, realized, and total P&L at the top of the positions message.

## Error Handling

- If MT5 history fetch fails, realized P&L returns `0.0` and logs an error.
- Positions message remains available even when realized P&L cannot be loaded.

## Tests

- Formatter test verifies floating, realized, and total P&L appear.
- Empty positions test verifies realized P&L still appears.
- MT5 helper test verifies realized P&L sums profit, swap, and commission for today's closed deals.
