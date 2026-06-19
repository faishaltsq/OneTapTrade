# AI-Owned Stop Loss And Take Profit Design

## Problem

The bot currently rejects valid AI SELL/BUY decisions because deterministic risk gates enforce profile-based stop-loss width and minimum risk-reward rules. Recent Telegram rejections show this clearly:

- XAU SELL rejected because SL was `882 pips`, above profile max `100`.
- Forex SELL rejected because TP distance was below required `1.5x SL`.

The user wants AI to decide SL and TP freely. The bot should not hardcode SL width or TP/RR distance.

## Desired Behavior

AI owns trade geometry:

- AI chooses `stop_loss`.
- AI chooses `take_profit_1`.
- AI may choose `risk_reward_to_tp1`, but bot does not enforce a minimum.
- Bot does not clamp, rewrite, or generate SL/TP using profile rules.

Risk profile still controls entry aggressiveness and confidence threshold, not SL/TP geometry.

## Risk Manager Changes

Remove deterministic geometry gates from `app/risk/risk_manager.py`:

- Remove minimum R:R rejection.
- Remove SL minimum pips rejection.
- Remove SL maximum pips rejection.
- Remove TP must be at least `min_rr * SL` rejection.

Keep non-geometry safety gates:

- HOLD decisions do not execute.
- Confidence threshold still applies per active risk profile.
- Max open positions still applies.
- Daily drawdown still applies.
- SL must exist for BUY/SELL.
- TP1 must exist for BUY/SELL.
- AI execution permission still applies.
- Live mode still requires `LIVE_TRADING_ENABLED=true`.
- Basic trade parameter validation still applies.

## Trade Parameter Validation

Keep `app/risk/trade_validator.py` side checks:

- BUY SL must be below entry/current price.
- BUY TP1 must be above entry price.
- SELL SL must be above entry/current price.
- SELL TP1 must be below entry price.

These are not strategy constraints; they prevent invalid MT5 order geometry.

## AI Validation Changes

Remove fallback SL/TP generation from `app/ai_engine/deepseek_client.py`.

If AI returns BUY/SELL without `stop_loss` or `take_profit_1`, validator should convert to HOLD as before. It must not invent SL/TP.

## Prompt Changes

Update `app/ai_engine/prompt_builder.py`:

- Remove profile SL range instructions.
- Remove minimum R:R instructions.
- Ask AI to choose logical SL and TP freely from market structure, volatility, and current setup.
- Keep requirement that BUY/SELL must include `stop_loss`, `take_profit_1`, `preferred_entry_price`, and optional `risk_reward_to_tp1`.

`build_user_prompt()` should no longer send `Minimum R:R` or `SL range` as constraints.

## Telegram Settings Display

Update `app/telegram_bot/message_templates.py` settings text:

- Do not display `Min R:R`, `SL Range`, or `TP min x SL` as active constraints.
- Display that SL/TP are AI-owned.
- Keep risk/trade percent because position sizing still uses it.

## Position Sizing

Do not change position sizing.

Lot size remains based on:

- Account balance.
- AI SL distance.
- `risk_per_trade_percent`.
- MT5 symbol tick value and volume limits.

If minimum lot would exceed configured risk percent, rejection can still happen. This protects account exposure, not SL/TP strategy choice.

## Tests

Add/update tests to verify:

- Wide AI SL is approved when other gates pass.
- Low AI RR is approved when other gates pass.
- Missing SL still prevents execution.
- Missing TP1 still prevents execution.
- Prompt no longer contains hard SL/RR constraints.
- Telegram settings says SL/TP are AI-owned.

## Out Of Scope

- No live trading default change.
- No spread filter restoration.
- No change to confidence thresholds.
- No change to max open positions or daily drawdown.
- No attempt to guarantee profitability.
