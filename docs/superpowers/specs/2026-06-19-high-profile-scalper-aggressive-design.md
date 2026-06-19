# High Profile Scalper Aggressive Design

## Goal

Make only the `HIGH` risk profile more aggressive for short-term demo scalping. `LOW` and `MEDIUM` behavior stays unchanged.

## Scope

This change applies only when `settings.risk_profile == "HIGH"`, usually selected from the Telegram `High` button.

## Desired HIGH Behavior

- Minimum AI confidence: `40%`.
- Minimum R:R: `1.2`.
- Stop-loss range: `15-80 pips`.
- Take-profit minimum: `1.2x SL`.
- Prefer `BUY` or `SELL` when M15 has clear directional momentum.
- H1 only blocks when strongly opposite to M15.
- D1 and H4 are context only, not hard blockers.
- Prefer `MARKET` or near-market entries for scalping.
- Return `HOLD` only when market is flat, data is missing, or M15 and H1 strongly conflict.

## Preserved Safety Rules

- `RISK_PER_TRADE_PERCENT` does not change.
- `max_open_positions` still applies.
- `max_daily_drawdown_percent` still applies.
- MT5 trade validation still applies.
- Live trading remains controlled by `LIVE_TRADING_ENABLED` and `BOT_MODE`.

## Profile Matrix

- `LOW`: confidence `65%`, RR `2.0`, SL `30-100 pips`.
- `MEDIUM`: confidence `55%`, RR `1.5`, SL `30-100 pips`.
- `HIGH`: confidence `40%`, RR `1.2`, SL `15-80 pips`.

## Implementation Notes

- Add profile-specific SL bounds in config instead of hardcoding `30-100` in risk manager.
- Risk manager uses effective profile values for confidence, RR, SL minimum, and SL maximum.
- DeepSeek prompt includes active profile thresholds and specifically explains `HIGH` as aggressive short-term scalping.
- Telegram settings display effective SL and TP values for the active profile.

## Tests

- `HIGH` thresholds expose confidence `40%`, RR `1.2`, SL `15-80`.
- Valid `HIGH` setup with confidence `40%`, RR `1.2`, SL `15 pips` is approved.
- `HIGH` setup below `40%` confidence is rejected.
- `HIGH` setup with SL below `15 pips` is rejected.
- `HIGH` setup with SL above `80 pips` is rejected.
- `LOW` and `MEDIUM` retain `30-100 pips` SL behavior.
- Prompt includes `HIGH` profile aggressive scalping rules.
