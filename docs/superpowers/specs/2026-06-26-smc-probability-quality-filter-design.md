# SMC Probability Quality Filter Design

## Goal

Improve SMC signal quality without rewriting the trading bot. Add deterministic probability scoring, confluence filtering, risk gating, stricter DeepSeek review, and clearer Telegram output while preserving the existing app flow, endpoints, Telegram integration, DeepSeek integration, SMC detector, alerts, services, and execution path.

## Non-Goals

- Do not rewrite the project or change the main architecture.
- Do not replace existing SMC indicators or detector logic.
- Do not remove existing alerts, routes, services, or config.
- Do not change core decision enum away from `BUY`, `SELL`, `HOLD`.
- Do not let AI invent price levels, entry, SL, or TP.

## Compatibility Strategy

Use a minimal-safe adapter model. The new SMC semantic decisions are metadata only:

- `BUY_SETUP` maps to existing core `BUY`.
- `SELL_SETUP` maps to existing core `SELL`.
- `WAIT` maps to existing core `HOLD`.
- `NO_TRADE` maps to existing core `HOLD`.

This avoids broad changes in risk manager, execution service, API routes, Telegram callbacks, database fields, and existing tests. The semantic decision is stored in `market_payload["smc_probability"]` and included in `risk_result` where useful for display/filtering.

## Risk Profile Timeframe Model

Use existing profile intent, but make scoring explicit:

- `LOW`: swing profile. Filter/bias uses `D1/H4`. Execution structure uses `H4/D1`. SL/TP should follow larger H4/D1 market structure.
- `MEDIUM`: intraday profile. Filter/bias uses `D1/H4`. Execution structure uses `H1`. SL/TP should follow H1 structure while respecting H4/D1 bias.
- `HIGH`: scalping profile. Filter/bias uses `H1/H4`. Execution structure uses `M5/M15`. SL/TP should follow M5/M15 structure. D1 remains broader context and warning, not the primary hard blocker.

Profile behavior:

- Low/medium should not trade against `D1/H4` bias.
- High should not trade against `H1/H4` bias.
- High may downgrade to `WAIT` rather than immediate `NO_TRADE` when D1 conflicts but H1/H4 and M5/M15 confluence is strong.
- All profiles require SMC confluence. BOS, CHoCH, EQH/EQL, FVG, or OB alone must not become a strong signal by themselves.

Data availability rule:

- Keep existing market payload keys stable: `higher_timeframe` = D1, `secondary_timeframe` = H4, `primary_timeframe` = H1, `entry_timeframe` = M5.
- Add real M15 data only as optional scoring context, for example `market_payload["profile_timeframes"]["M15"]`, without renaming existing fields.
- If M15 data is unavailable, high profile may use M5 plus H1/H4 filter and record a `timeframe_fallback` weakness.
- Do not alter existing `settings.risk_profile_config` values except to keep them aligned with current intent: LOW `H4/D1`, MEDIUM `H1/H4`, HIGH `M5/M15`.

## New Component

Add `app/analysis/smc_probability.py` with a pure deterministic scorer:

```python
def score_smc_setup(market_payload: dict, risk_profile: str | None = None) -> dict:
    ...
```

Return shape:

```json
{
  "base_score": 50,
  "adjustments": [
    {"factor": "swing_internal_alignment", "value": 20, "reason": "Profile filter and execution bias align bullish"}
  ],
  "final_score": 70,
  "pre_ai_decision": "BUY_SETUP",
  "bias": "bullish",
  "setup_quality": "medium",
  "timeframe_model": {
    "profile": "MEDIUM",
    "filter_timeframes": ["D1", "H4"],
    "execution_timeframes": ["H1"],
    "timeframe_fallback": null
  },
  "main_confluence": [],
  "weaknesses": [],
  "risk_notes": [],
  "entry_sl_tp_note": "manual confirmation required",
  "invalidation": "manual confirmation required",
  "ai_review_used": false,
  "ai_unavailable": false
}
```

## Scoring Rules

Start from `base_score = 50`, clamp final score to `0..100`.

Market structure alignment:

- Filter and execution bias aligned bullish for buy: `+20`.
- Filter and execution bias aligned bearish for sell: `+20`.
- Filter and execution conflict: `-25`.
- Low/medium against D1/H4: force `NO_TRADE` unless data is insufficient, then `WAIT`.
- High against H1/H4: force `NO_TRADE` unless data is insufficient, then `WAIT`.
- High with D1 warning only: small penalty, usually `-5` to `-10`, not hard block.

Event quality:

- CHoCH after liquidity clue: `+15`.
- CHoCH without liquidity clue: `-10`.
- BOS continuation with aligned filter and one other confluence: `+10` when BOS data exists.
- BOS without other confluence: `-10` when BOS data exists.
- EQH/EQL/liquidity level: `+5` as clue only, never standalone entry.
- FVG aligned with direction: `+5` as support only.
- OB aligned with direction and price context: `+10`.
- OB breakout against setup: warning/invalidation, `-10` or `NO_TRADE` if severe.

Premium/discount:

- Buy in discount or lower equilibrium area: `+10`.
- Sell in premium or upper equilibrium area: `+10`.
- Buy in premium: `-15`.
- Sell in discount: `-15`.
- If insufficient swing range to compute premium/discount, add weakness and do not invent zone.

Risk/session:

- Spread above `settings.max_spread_points`: force `NO_TRADE`.
- News risk high when payload/config provides it: force `NO_TRADE`.
- RR below `settings.min_risk_reward` or `1.5`, whichever is stricter for the active profile: force `NO_TRADE`.
- Entry/SL/TP missing: no fake numbers. Set `entry_sl_tp_note = "manual confirmation required"` and block execution unless existing downstream AI/risk has valid levels.
- London/New York session: `+5`.
- Asia session for XAUUSD: `-5`, unless setup already qualifies as high quality.
- Unknown session: `-3`, never hard block.

Decision bands:

- `0..39`: `NO_TRADE`.
- `40..59`: `WAIT`.
- `60..74`: medium setup.
- `75..89`: high quality setup.
- `90..100`: very high quality setup, but wording must avoid certainty.

For executable semantic decision:

- Bullish score `>= MIN_SIGNAL_PROBABILITY`: `BUY_SETUP`.
- Bearish score `>= MIN_SIGNAL_PROBABILITY`: `SELL_SETUP`.
- Score below threshold but not invalid: `WAIT`.
- Forced risk failure: `NO_TRADE`.

## Signal Flow Changes

Modify `app/services/signal_service.py` only at integration points:

1. Build `market_payload` as today.
2. Run deterministic `score_smc_setup()`.
3. Store result in `market_payload["smc_probability"]`.
4. If deterministic result is forced `NO_TRADE`, create existing core `HOLD` decision unless `SEND_NO_TRADE_ALERT=true` requires display.
5. If `ENABLE_AI_REVIEW=true`, call existing DeepSeek path with the scoring context included.
6. Validate AI output through existing `validate_decision()`.
7. Apply final semantic filter before Telegram and execution.
8. Existing `evaluate_decision()` remains final safety guard.

No main loop rewrite is required.

## DeepSeek Prompt Changes

Update SMC mode prompt in `app/ai_engine/prompt_builder.py`:

- Replace aggressive wording with probability-review wording.
- Remove instructions that say spread does not matter.
- Remove instructions that missing a trade is worse than a small loss.
- Tell DeepSeek it is an SMC trading probability analyst, not a free market predictor.
- Tell DeepSeek to analyze only provided data and deterministic score.
- Tell DeepSeek not to invent entry, SL, TP, invalidation, premium/discount zones, or liquidity levels.
- Tell DeepSeek weak confluence should return HOLD-compatible output with semantic `WAIT` or `NO_TRADE` in reasoning/metadata.
- Tell DeepSeek probability must be confluence-based, not prediction-based.
- Keep valid JSON only.

The user prompt should include:

- Active risk profile.
- Profile filter/execution timeframe model.
- Deterministic score object.
- Existing compact market payload.

## AI Failure Fallback

If DeepSeek API errors, times out, or returns invalid JSON:

- Do not crash.
- Use deterministic scoring result.
- Convert semantic result to existing core decision.
- Set `ai_unavailable=true` in score object.
- Add final comment: `AI analysis unavailable, rule-based score used`.
- Log the error without API key or sensitive values.

## Telegram Filtering

Add optional config:

- `MIN_SIGNAL_PROBABILITY=70`.
- `SEND_NO_TRADE_ALERT=false`.
- `ENABLE_AI_REVIEW=true`.

Telegram send rules:

- Do not send `NO_TRADE` alerts unless `SEND_NO_TRADE_ALERT=true`.
- Do not send trade setup alerts when `final_score < MIN_SIGNAL_PROBABILITY`.
- `WAIT` can be silent by default unless it is already part of existing HOLD market updates; keep existing behavior where possible.
- Approved auto execution still requires existing signal-send success before execution.

## Telegram Message Format

Enhance `app/telegram_bot/message_templates.py` to render SMC probability when present:

```text
🟢/🔴/⚪ SYMBOL — SMC ANALYSIS

Bias:
HTF/Swing: ...
Internal: ...
Direction: ...
Profile TF: ...

SMC Event:
Event: ...
Timeframe: ...
Premium/Discount: ...

Confluence:
✅ ...
✅ ...
⚠️ ...

Probability:
Score: ...%
Quality: High / Medium / Low

Decision:
BUY_SETUP / SELL_SETUP / WAIT / NO_TRADE

Risk:
Spread: ...
News: ...
RR: ...

Entry/SL/TP:
Manual confirmation required
or existing payload levels only

Invalidation:
...
```

Do not delete existing trade plan option formatting. When entry/SL/TP exists, keep showing existing market/limit options. When levels are missing, show `manual confirmation required`.

## Logging

Add structured logs around:

- Incoming SMC event/payload summary.
- Deterministic score and adjustments.
- DeepSeek response preview already exists; add semantic result summary.
- Final semantic decision and core decision mapping.
- Telegram filter reason: sent, suppressed by probability, suppressed by no-trade setting, or send failed.

## Tests

Add focused tests without requiring MT5:

- `score_smc_setup` aligned bullish profile returns higher probability and `BUY_SETUP`.
- Structure conflict lowers probability.
- High spread forces `NO_TRADE`.
- Low RR forces `NO_TRADE`.
- Missing levels produce `manual confirmation required` and no invented values.
- High profile uses H1/H4 filter and M5/M15 execution model.
- Missing M15 context records `timeframe_fallback` instead of failing or renaming existing payload sections.
- Prompt no longer contains old spread-ignore/aggressive wording.
- Telegram format renders SMC probability block.
- Signal filter suppresses `NO_TRADE` when `SEND_NO_TRADE_ALERT=false`.
- DeepSeek failure fallback uses rule-based score.

## Rollout

Implement behind optional env defaults:

- `ENABLE_AI_REVIEW=true` preserves current AI involvement.
- `MIN_SIGNAL_PROBABILITY=70` filters weak setups.
- `SEND_NO_TRADE_ALERT=false` reduces noise.

Existing routes, bot commands, execution services, and database save paths remain intact.
