# Telegram Risk Settings Design

## Goal

Allow Telegram to control both signal aggressiveness and monetary risk per trade from the bot UI.

## Scope

Telegram settings will control:

- `risk_profile`: `LOW`, `MEDIUM`, `HIGH`.
- `risk_per_trade_percent`: preset values `0.25%`, `0.5%`, `1.0%`.

## Behavior

- Main menu keeps quick `Low`, `Med`, `High` profile buttons.
- Settings view adds inline buttons for both profile and risk/trade percent.
- Tapping a profile button updates runtime `settings.risk_profile` immediately.
- Tapping a risk/trade button updates runtime `settings.risk_per_trade_percent` immediately.
- Updates persist to Supabase `bot_settings` when Supabase is available.
- If Supabase persistence fails, runtime update still succeeds and error is logged.
- `/settings` displays active profile, active risk/trade percent, profile thresholds, SL range, TP rule, drawdown, max positions, interval, and live-trading flag.

## Safety Rules

- Allowed risk/trade presets are `0.25`, `0.5`, and `1.0` only.
- Invalid callback values are rejected and do not change runtime settings.
- Maximum Telegram-configurable risk/trade is `1.0%`.
- This feature does not enable live trading.
- Drawdown, max positions, SL/TP validation, and MT5 validation remain unchanged.

## Persistence Fix

Repository `update_bot_settings` must allow `risk_profile`; current allow-list includes `risk_per_trade_percent` but not `risk_profile`.

## UI

Settings panel layout:

- First section: settings text.
- Row: `Low`, `Med`, `High`.
- Row: `Risk 0.25%`, `Risk 0.5%`, `Risk 1%`.
- Row: `Back/Menu`.

## Tests

- `update_bot_settings` allows `risk_profile`.
- Risk profile callback updates runtime and persists `risk_profile`.
- Risk/trade callback accepts `0.25`, `0.5`, `1.0`.
- Risk/trade callback rejects invalid values.
- Settings keyboard contains profile buttons and risk/trade buttons.
- Settings message shows active risk/trade percent.
