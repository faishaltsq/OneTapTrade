# Aggressive Entry Profile Design

## Goal

Make Telegram risk-profile buttons affect entry aggressiveness clearly, especially `High`, while keeping fixed money risk unchanged.

Chosen behavior: `High` profile should allow trades around `50%` AI confidence when setup has usable M15 momentum and H1 is not strongly opposite. `High` should also allow TP at `1.5x SL`, instead of forcing `2x SL`.

## Current State

- Telegram menu has `Low`, `Med`, and `High` buttons.
- Buttons set `settings.risk_profile` and persist `risk_profile` to Supabase.
- `settings.risk_profile_config` currently sets `High` to confidence `0.45` and RR `1.2`.
- Risk manager still has a hardcoded TP rule: TP must be at least `2x SL`.
- This hardcoded rule means profile RR settings do not fully control execution.
- DeepSeek prompt says to be aggressive, but it does not receive explicit profile-specific entry rules.

## Desired Behavior

Risk profile controls signal quality and entry aggressiveness only. It does not change `RISK_PER_TRADE_PERCENT` or lot sizing.

Profiles:

- `LOW`: conservative quality. Minimum confidence `65%`, minimum RR `2.0`.
- `MEDIUM`: balanced quality. Minimum confidence `55%`, minimum RR `1.5`.
- `HIGH`: aggressive scalping. Minimum confidence `50%`, minimum RR `1.5`.

For `HIGH`, execution may approve `50-60%` confidence trades if:

- decision is `BUY` or `SELL`, not `HOLD`;
- stop loss and take profit are present;
- SL is still within configured scalping range;
- TP is at least `1.5x SL`;
- open-position and drawdown limits pass;
- MT5 trade validation passes;
- AI execution permission is true.

## DeepSeek Analysis Rules

Prompt should include current risk profile and effective thresholds.

For `HIGH` profile, DeepSeek should:

- prefer decisive `BUY` or `SELL` when M15 has directional momentum;
- allow H1 neutral or mildly conflicting trend if M15 momentum is strong;
- avoid waiting for perfect D1/H1/H4 alignment;
- use market or near-market entries for scalping;
- assign realistic confidence, where `50-60%` is acceptable for aggressive entries;
- return `HOLD` only when data is missing, direction is flat, or H1 and M15 strongly conflict.

For all profiles, DeepSeek must still return strict JSON only.

## Risk Manager Rules

Risk manager should remove hardcoded `TP >= 2x SL` rule.

Risk manager should use `settings.effective_min_risk_reward` for both:

- declared `risk_reward_to_tp1` check;
- computed TP distance versus SL distance check.

Example: if profile is `HIGH`, `effective_min_risk_reward == 1.5`, so computed TP must be at least `1.5x SL`.

## Telegram UX

Buttons must continue working:

- `Low`, `Med`, `High` update runtime `settings.risk_profile`.
- Buttons persist profile to Supabase.
- Menu refreshes after profile change.
- Settings message shows active profile, effective minimum confidence, and effective minimum RR.

Labels should communicate intent:

- `Low`: safer, fewer trades.
- `Med`: balanced.
- `High`: aggressive, more entries.

## Data Flow

1. User taps Telegram risk-profile button.
2. Callback updates runtime settings and Supabase bot settings.
3. Next analysis cycle builds DeepSeek prompt with active risk profile and thresholds.
4. DeepSeek returns decision JSON with confidence and entry plan.
5. Risk manager validates confidence, RR, SL/TP distances, positions, drawdown, AI permission, and MT5 params.
6. In `AUTO_DEMO`, approved `BUY` or `SELL` executes automatically.

## Error Handling

- If Supabase update fails, callback should not crash Telegram; log error and still update runtime profile.
- If profile is invalid, fallback to `MEDIUM` thresholds.
- If DeepSeek returns invalid JSON, existing parser/retry path remains responsible.
- If SL/TP missing or invalid, risk manager rejects trade regardless of profile.

## Tests

Add or update tests for:

- `HIGH` profile uses `50%` confidence and `1.5` RR.
- Risk manager approves a valid `HIGH` setup with TP exactly `1.5x SL`.
- Risk manager rejects a `HIGH` setup below `1.5x SL`.
- Risk manager still rejects low confidence below `50%` for `HIGH`.
- Telegram risk callback persists profile and sends refreshed menu without breaking.

## Non-Goals

- Do not change `risk_per_trade_percent`.
- Do not enable live trading.
- Do not remove drawdown, max position, SL, TP, or MT5 validation safeguards.
- Do not add new Telegram slash commands.
