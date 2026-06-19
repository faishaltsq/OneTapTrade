# Startup Position Sync And D1 Trend Lock Design

## Goal

Prevent inconsistent post-restart entries by syncing live MT5 positions at startup, locking new signals to existing open position direction, and enforcing D1 candle bias as the major trend filter.

## Scope

- Sync currently open MT5 positions when the server starts after MT5 login.
- Keep runtime awareness of open position side per symbol.
- Allow same-direction add-on entries.
- Block opposite-direction entries while a live position exists on the same symbol.
- Enforce D1 major trend direction for all new entries.
- For D1 ranging conditions, only allow entry after breakout and retest confirmation.
- Preserve existing position management such as breakeven SL logic.

## Startup Sync

After MT5 login succeeds during FastAPI lifespan startup:

1. Fetch all open MT5 positions with `positions_get()`.
2. For each live position, build a runtime position state record:
   - `symbol`
   - `side` (`BUY` or `SELL`)
   - `ticket`
   - `entry_price`
   - `sl`
   - `tp`
   - `volume`
   - `profit`
3. Upsert the live position into the `trades` table by `mt5_ticket` when Supabase is available.
4. If the `trades` table has `OPEN` rows whose `mt5_ticket` is not currently open in MT5, mark them `CLOSED` with status reason `not_found_on_startup_sync` when possible.
5. Log a sync summary with counts for live positions, inserted/updated DB rows, and stale DB rows closed.

## Direction Lock

Direction lock is per symbol and only blocks the opposite side.

Rules:

- If an open BUY exists on `XAUUSD.c`, new SELL entries for `XAUUSD.c` are rejected.
- If an open SELL exists on `XAUUSD.c`, new BUY entries for `XAUUSD.c` are rejected.
- Same-direction entries remain allowed, subject to D1 trend filter and other risk checks.
- `MAX_OPEN_POSITIONS` no longer blocks same-direction add-on entries for this restart consistency logic.

Example reject reasons:

- `Blocked: open BUY exists, SELL not allowed`
- `Blocked: open SELL exists, BUY not allowed`

## D1 Major Trend Filter

Use the latest D1 candle as deterministic major trend context.

Rules:

- `D1_BULLISH`: latest D1 candle closes above open with meaningful body.
- `D1_BEARISH`: latest D1 candle closes below open with meaningful body.
- `D1_RANGING`: latest D1 candle body is small relative to candle range, or candle data is unclear.

Entry rules:

- D1 bullish: only BUY signals allowed.
- D1 bearish: only SELL signals allowed.
- D1 ranging: HOLD unless breakout + retest is confirmed.

## D1 Ranging Breakout + Retest

When D1 is ranging, entries require all of the following:

- Breakout above D1 range high for BUY or below D1 range low for SELL.
- Retest of the broken level, H1/M5 order block, or FVG zone.
- M5 momentum confirms the breakout direction.
- SMC context supports the direction through CHoCH, liquidity sweep, order block reaction, or FVG reaction.

If any condition is missing, return HOLD.

## Enforcement Layers

Use defense-in-depth so the AI cannot bypass rules.

1. Feature payload:
   - Add `major_trend` section from D1 candle.
   - Add `open_position_state` section from live MT5 positions.
2. Prompt:
   - Tell DeepSeek to follow D1 major trend and position direction lock.
   - Tell DeepSeek same-direction add-ons are allowed when setup is valid.
3. Risk manager:
   - Hard reject opposite direction vs existing live position on same symbol.
   - Hard reject entries against D1 major trend.
   - Hard reject entries during D1 ranging until breakout + retest is confirmed.
4. Startup sync:
   - Populate position state before first trading loop cycle.

## Error Handling

- If MT5 position sync fails, log the error and continue startup.
- If Supabase is unavailable, maintain runtime state from MT5 and skip DB upsert.
- If D1 candle data is missing or invalid, mark `major_trend.bias` as `D1_RANGING` and require HOLD unless breakout + retest data is available.

## Tests

- Startup sync reads MT5 open positions and builds runtime state.
- Startup sync upserts live MT5 positions by ticket when DB is available.
- Risk manager rejects SELL when open BUY exists for the symbol.
- Risk manager allows BUY when open BUY exists for the symbol.
- Risk manager rejects SELL when D1 is bullish.
- Risk manager rejects BUY when D1 is bearish.
- Risk manager rejects BUY/SELL when D1 is ranging without breakout + retest.
- Prompt includes D1 major trend and direction-lock rules.
- Market payload includes `major_trend` and `open_position_state`.
