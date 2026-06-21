# Strategy Mode Toggle + Trading Style Profiles + Noise Filter

**Date**: 2026-06-21
**Status**: Design approved, ready for implementation plan
**Approach**: A — Conditional prompt builder + functional noise filter module

## Goal

Let user switch bot "thinking mode" via Telegram and bind trading style (swing/daytrade/scalping) to existing risk profiles. Reduce chart noise via pre-AI gate so bad-market conditions skip DeepSeek API call entirely.

## Decisions from brainstorming

| Question | Decision |
|---|---|
| AI-only mode definition | Keep payload identical. AI free to use/ignore any section. Only system prompt changes. |
| Noise reduction strategy | Multi-TF alignment + ATR percentile + volume confirmation (all three) |
| Profile differentiation | Timeframe focus + hold time + skip condition per profile |
| Strategy mode persistence | Persist to Supabase `bot_settings.strategy_mode` |
| Noise filter location | Pre-AI gate (fail = HOLD, skip API call) |
| Profile strictness | LOW strict, MEDIUM lenient, HIGH very lenient (still allow entries) |

## Section 1 — Strategy mode + config

### Config (`app/config.py`)

Add field:
```python
strategy_mode: str = "SMC_AI"  # valid: SMC_AI, AI_ONLY
```

Replace `risk_profile_config` mapping. Each profile binds to a trading style:

```python
profiles = {
    "LOW": {
        "style": "SWING",
        "entry_tf": ["H4", "D1"],
        "hold": "days-weeks",
        "min_confidence": 0.70,
        "min_risk_reward": 2.5,
        "sl_pips": (100, 500),
        "tp_pips": (200, 1000),
    },
    "MEDIUM": {
        "style": "DAYTRADE",
        "entry_tf": ["H1", "H4"],
        "hold": "hours-days",
        "min_confidence": 0.55,
        "min_risk_reward": 1.8,
        "sl_pips": (50, 150),
        "tp_pips": (75, 300),
    },
    "HIGH": {
        "style": "SCALPING",
        "entry_tf": ["M5", "M15"],
        "hold": "minutes-hours",
        "min_confidence": 0.40,
        "min_risk_reward": 1.2,
        "sl_pips": (15, 50),
        "tp_pips": (15, 75),
    },
}
```

New properties on `Settings`:
- `effective_style` → `"SWING" | "DAYTRADE" | "SCALPING"`
- `effective_entry_tfs` → `list[str]`
- `effective_hold_time` → `str`
- `effective_sl_pip_range` → `tuple[int, int]`
- `effective_tp_pip_range` → `tuple[int, int]`

Existing `effective_min_confidence`, `effective_min_risk_reward` still work, now read from new mapping.

### Supabase schema

```sql
ALTER TABLE bot_settings
    ADD COLUMN IF NOT EXISTS strategy_mode TEXT NOT NULL DEFAULT 'SMC_AI';
NOTIFY pgrst, 'reload schema';
```

### Repositories (`app/database/repositories.py`)

Add `strategy_mode` to `allowed` set in `update_bot_settings`.

### `.env.example`

Add:
```
STRATEGY_MODE=SMC_AI
```

## Section 2 — Prompt structure

`app/ai_engine/prompt_builder.py` builds composite prompt from base + style block.

### Base SMC_AI prompt

Extends existing `SYSTEM_PROMPT`. Retains:
- D1 hard filter (BULLISH → BUY only, BEARISH → SELL only, RANGING → HOLD unless breakout retest)
- SMC rules (order blocks, FVG, CHoCH, liquidity levels, swing points)
- Open position rules (same-direction add-on, opposite blocked)
- SL/TP freedom from market structure
- Spread ignore
- Aggressive bias

Style block appended at end (see below).

### Base AI_ONLY prompt (new)

```
You are an AI trading execution analysis engine for MT5.
You receive ALL available market data (indicators, structure, SMC, orderflow, volume profile).
You decide INDEPENDENTLY which signals matter. No fixed methodology.
Think from first principles: price action, momentum, volume, context.
Weight factors dynamically per situation — no hardcoded priority.
Return strict JSON only.

D1 major trend remains a hard filter (cannot fight major bias).
Same-direction add-ons allowed. Opposite blocked when position open.
SL/TP: you choose freely from market structure. Set logical invalidation + realistic target.
Spread does NOT matter — never HOLD because of spread.

[STYLE BLOCK inserted here]

Return only valid JSON.
```

### Style blocks (shared by both modes)

```
SWING (LOW):
- Target hold: days to weeks. Entry TF: H4/D1.
- Prioritize D1+H4 alignment. Skip if D1 and H4 conflict.
- SL: 100-500 pips range. TP: 200-1000 pips. R:R min 2.5.
- Min confidence 70%. Only clean structural setups.
- Avoid news spikes. Avoid tight ranges. Patience over frequency.

DAYTRADE (MEDIUM):
- Target hold: hours to days. Entry TF: H1/H4.
- D1 must allow direction. H1 is primary execution context.
- SL: 50-150 pips. TP: 75-300 pips. R:R min 1.8.
- Min confidence 55%. Balance quality and frequency.
- Accept H4+H1 aligned setups even if M5 noisy.

SCALPING (HIGH):
- Target hold: minutes to hours. Entry TF: M5/M15.
- H1 is direction filter, M5 is trigger.
- SL: 15-50 pips. TP: 15-75 pips. R:R min 1.2.
- Min confidence 40%. Aggressive on momentum.
- D1 remains hard filter but M5 momentum can override H1 if not strongly opposite.
```

### `build_system_prompt()`

Reads `settings.strategy_mode` + `settings.risk_profile`, composes:
1. Base prompt (SMC_AI or AI_ONLY)
2. Style block (SWING / DAYTRADE / SCALPING)

### `build_user_prompt(market_payload)`

Adds context header before payload JSON:
```
Analyze the following market data and return a trading decision.

Strategy mode: SMC+AI
Trading style: Daytrade (MEDIUM)
Entry TF: H1/H4 | Hold: hours-days
Risk profile: MEDIUM
Minimum confidence: 55%

Market data:
{payload_json}
```

### Schema (`app/ai_engine/schemas.py`)

Add optional fields to `AIDecisionResponse`:
```python
strategy_mode: Optional[str] = None
trading_style: Optional[str] = None
```

Filled post-parse from `settings` in `deepseek_client.get_ai_decision()`. Not required from AI.

### Token budget

AI_ONLY base ~60% length of SMC_AI base. Both fit within `max_tokens=4000`.

## Section 3 — Noise filter

**New module**: `app/analysis/noise_filter.py`

**Function**: `evaluate_noise_filter(df_d1, df_h4, df_h1, df_m5, risk_profile: str) -> dict`

Called in `signal_service.py` after `build_market_payload`, before `get_ai_decision`.

### Gate 1: Multi-TF alignment

Uses `detect_trend(df)` from `app/analysis/market_structure.py`.

| Profile | Rule |
|---|---|
| SWING (LOW) | `D1.direction == H4.direction` and both non-UNCLEAR. Else HOLD. |
| DAYTRADE (MEDIUM) | `D1.direction` non-UNCLEAR and `H1.direction` not strongly opposite to D1. H4 UNCLEAR tolerated. "Strongly opposite" = exact opposite (D1=BULLISH and H1=BEARISH, or D1=BEARISH and H1=BULLISH). NEUTRAL/UNCLEAR on H1 does NOT count as opposite. |
| SCALPING (HIGH) | Skip this gate. M5 momentum may override. D1 hard filter still applies in risk_manager. |

### Gate 2: ATR percentile

Uses `_atr_percentile(df_h1, 14)` from `app/analysis/regime_detector.py`.

| Profile | Pass band | Block reason |
|---|---|---|
| SWING (LOW) | 20 ≤ ATR pct ≤ 85 | `<20`: dead market, `>85`: chaos |
| DAYTRADE (MEDIUM) | 15 ≤ ATR pct ≤ 90 | slightly lenient |
| SCALPING (HIGH) | 10 ≤ ATR pct ≤ 95 | almost never blocks |

### Gate 3: Volume confirmation

Compares `tick_volume` of last candle vs average of last 20 candles on entry-TF dataframe (df_m5 for SCALPING, df_h1 for DAYTRADE, df_h4 for SWING).

| Profile | Threshold | Block reason |
|---|---|---|
| SWING (LOW) | `volume_last > 1.2 * avg20` | wants strong confirmation |
| DAYTRADE (MEDIUM) | `volume_last > 0.8 * avg20` | just needs activity |
| SCALPING (HIGH) | `volume_last > 0.5 * avg20` | only blocks truly dead market |

### Return format

```python
{
    "passed": bool,
    "blocked_by": Optional[str],  # "tf_alignment" | "atr_percentile" | "volume" | None
    "details": {
        "tf_alignment": {"d1": "BULLISH", "h4": "BULLISH", "h1": "NEUTRAL", "m5": "UNCLEAR"},
        "atr_percentile": 45.2,
        "volume_ratio": 1.1,
    },
    "hold_reason": str,  # for Telegram display
}
```

### Integration in `signal_service.py`

Insert between Step 10 (snapshot save) and Step 11 (AI call):

```python
from app.analysis.noise_filter import evaluate_noise_filter

noise_result = evaluate_noise_filter(df_d1, df_h4, df_h1, df_m15, settings.risk_profile)
if not noise_result["passed"]:
    from app.ai_engine.deepseek_client import _default_hold
    from app.ai_engine.schemas import MarketRegime, TimeframeBias

    hold_decision = _default_hold()
    hold_decision.main_reason = f"Noise filter: {noise_result['hold_reason']}"
    # keep market_regime from payload if available
    regime_raw = market_payload.get("overall_regime", {}).get("regime", "UNCLEAR")
    try:
        hold_decision.market_regime = MarketRegime(regime_raw)
    except ValueError:
        hold_decision.market_regime = MarketRegime.UNCLEAR

    # save to DB for audit trail
    # return HOLD with noise_filter result, skip AI call
    return {
        "symbol": sym,
        "ai_decision": hold_decision,
        "risk_result": {"approved": False, "reason": f"Noise filter: {noise_result['hold_reason']}"},
        "market_payload": market_payload,
        "snapshot_id": snapshot_id,
        "decision_id": None,
        "noise_filter": noise_result,
    }
```

### Telegram display for noise-filter HOLD

`_send_market_update` in `trading_loop.py` already handles HOLD. `format_market_trend_alert` should detect `main_reason` starting with `"Noise filter:"` and render:

```
⚪ Market Update — XAUUSD

Decision: HOLD (noise filter)
Reason: TF conflict: D1=BULLISH, H4=BEARISH
```

No code change needed in `trading_loop.py` — it already sends market update on HOLD. Only `message_templates.py` may add a small formatting nicety (optional).

### Audit

`noise_filter` result stored in returned dict. `signal_service` can save it into `market_snapshots.raw_payload` or `ai_decisions.input_json` for later review. Implementation detail: include `noise_filter` key in the snapshot's `raw_payload` before saving.

## Section 4 — Telegram UI + risk manager

### Main menu (`message_templates.py:build_main_menu_keyboard`)

Add row above risk profile row:

```python
[
    InlineKeyboardButton("🧠 SMC+AI" + (" ✅" if strategy_mode=="SMC_AI" else ""), callback_data="MENU_STRATEGY_SMC"),
    InlineKeyboardButton("🤖 AI Only" + (" ✅" if strategy_mode=="AI_ONLY" else ""), callback_data="MENU_STRATEGY_AI"),
],
```

Function signature gains `strategy_mode: str = "SMC_AI"` parameter. Callers in `callbacks.py` and `bot.py` pass `settings.strategy_mode`.

### Settings keyboard (`build_settings_keyboard`)

Profile buttons show style label:

```python
[
    InlineKeyboardButton("🟢 Low (Swing)", callback_data="MENU_RISK_LOW"),
    InlineKeyboardButton("🟡 Med (Day)", callback_data="MENU_RISK_MEDIUM"),
    InlineKeyboardButton("🔴 High (Scalp)", callback_data="MENU_RISK_HIGH"),
],
[
    InlineKeyboardButton("🧠 SMC+AI" + active_marker, callback_data="MENU_STRATEGY_SMC"),
    InlineKeyboardButton("🤖 AI Only" + active_marker, callback_data="MENU_STRATEGY_AI"),
],
[
    InlineKeyboardButton("Risk 0.25%", callback_data="MENU_RISK_TRADE_025"),
    InlineKeyboardButton("Risk 0.5%", callback_data="MENU_RISK_TRADE_050"),
    InlineKeyboardButton("Risk 1%", callback_data="MENU_RISK_TRADE_100"),
],
[InlineKeyboardButton("⬅️ Back/Menu", callback_data="MENU_BACK")],
```

### Settings message (`format_settings_message`)

```
⚙️ Settings

Strategy: 🧠 SMC+AI
Profile: MEDIUM → Daytrade
Entry TF: H1/H4 | Hold: hours-days
Min Conf: 55% | Min R:R: 1.8
SL range: 50-150 pips | TP range: 75-300 pips
Noise filter: lenient (MEDIUM)
Risk/Trade: 0.5%
Max Daily DD: 2.0%
Max Positions: 1
Interval: 300s
Live Trading: ❌
```

### Callbacks (`callbacks.py`)

Two new handlers:

```python
async def menu_strategy_smc_cb(update, context):
    await _menu_set_strategy(update, "SMC_AI")

async def menu_strategy_ai_cb(update, context):
    await _menu_set_strategy(update, "AI_ONLY")

async def _menu_set_strategy(update, mode: str):
    query = update.callback_query
    # auth check
    settings.strategy_mode = mode
    from app.database.repositories import update_bot_settings
    update_bot_settings({"strategy_mode": mode})
    labels = {"SMC_AI": "SMC + AI", "AI_ONLY": "AI Only"}
    await query.answer(f"Strategy: {labels[mode]}")
    await _edit_message(update, format_settings_message(), reply_markup=build_settings_keyboard())
```

Register in `get_callback_handlers()`:
```python
CallbackQueryHandler(menu_strategy_smc_cb, pattern=r"^MENU_STRATEGY_SMC$"),
CallbackQueryHandler(menu_strategy_ai_cb, pattern=r"^MENU_STRATEGY_AI$"),
```

Risk profile callback labels update to include style name in toast answer.

### Risk manager (`app/risk/risk_manager.py`)

**No structural change.** Reads `settings.effective_min_confidence` and `settings.effective_min_risk_reward` which now return new profile values automatically.

**SL/TP range**: AI owns SL/TP. Risk manager does NOT reject for out-of-range SL. Optional: log warning if SL pip distance outside `effective_sl_pip_range`. No rejection.

**Strategy mode**: no effect on risk manager. Mode only changes prompt + noise filter. Risk manager is mode-agnostic.

### Full new flow

```
1. TradingLoop.run_once() per symbol
2. signal_service.generate_signal(symbol)
3. Fetch MT5 data (D1/H4/H1/M5 + tick + depth)
4. build_market_payload() — still sends ALL data sections
5. ★ NEW: noise_filter.evaluate(df_d1, df_h4, df_h1, df_m5, risk_profile)
   → FAIL: build HOLD decision with reason, save to DB, return early. Skip AI.
   → PASS: continue
6. get_ai_decision(payload) — prompt depends on strategy_mode + risk_profile
7. validate_decision()
8. risk_manager.evaluate_decision() — final gate
9. Execute / signal / hold per bot_mode
```

## Section 5 — Testing + migration

### Tests

**New**: `tests/test_noise_filter.py`
- 3 gates × pass/fail cases
- Profile strictness: SWING strict, MEDIUM lenient, HIGH near-free
- Return format keys present
- Edge cases: empty df, ATR pct 0/100, volume_ratio 0

**New**: `tests/test_prompt_builder.py`
- `build_system_prompt()` returns 6 variants for (SMC_AI, AI_ONLY) × (LOW, MEDIUM, HIGH)
- SMC_AI prompt contains "order blocks" / "FVG" / "CHoCH"
- AI_ONLY prompt contains "first principles" / "INDEPENDENTLY"
- Style block keyword per profile: "days to weeks" (SWING), "hours to days" (DAYTRADE), "minutes to hours" (SCALPING)
- `build_user_prompt()` includes strategy mode + style header

**Extend**: `tests/test_risk_manager.py`
- `effective_min_confidence` returns 0.70 / 0.55 / 0.40 per profile
- `effective_min_risk_reward` returns 2.5 / 1.8 / 1.2 per profile
- `strategy_mode` does not affect risk approval outcome

**Extend**: `tests/test_telegram_bot.py`
- `MENU_STRATEGY_SMC` callback sets `settings.strategy_mode = "SMC_AI"`
- `MENU_STRATEGY_AI` callback sets `settings.strategy_mode = "AI_ONLY"`
- `update_bot_settings` called with `{"strategy_mode": mode}`
- Settings message contains "Daytrade" when profile MEDIUM

**New**: `tests/test_config.py`
- `risk_profile_config` has keys: `style`, `entry_tf`, `hold`, `sl_pips`, `tp_pips`, `min_confidence`, `min_risk_reward`
- `strategy_mode` default `"SMC_AI"`
- Properties: `effective_style`, `effective_entry_tfs`, `effective_hold_time`, `effective_sl_pip_range`, `effective_tp_pip_range`

### Migration

**Supabase**: run `ALTER TABLE bot_settings ADD COLUMN IF NOT EXISTS strategy_mode TEXT NOT NULL DEFAULT 'SMC_AI';` — safe, additive, default preserves old behavior.

**Backward compat**:
- `strategy_mode` defaults to `SMC_AI` = current behavior
- Risk profile mapping changes numeric thresholds (LOW: conf 0.65 → 0.70, rr 2.0 → 2.5). Minor tightening for LOW. MEDIUM/HIGH shift slightly. Existing user settings still work.
- No data migration needed. No destructive change.

**`.env.example`**: add `STRATEGY_MODE=SMC_AI` with comment.

## Files changed summary

| File | Change |
|---|---|
| `app/config.py` | +`strategy_mode` field, profile mapping rewrite, new properties |
| `app/analysis/noise_filter.py` | NEW — 3 gates, profile-aware |
| `app/ai_engine/prompt_builder.py` | composite prompt, 6 variants |
| `app/ai_engine/schemas.py` | +`strategy_mode`, `trading_style` optional fields |
| `app/ai_engine/deepseek_client.py` | fill `strategy_mode` + `trading_style` post-parse |
| `app/services/signal_service.py` | integrate noise filter pre-AI |
| `app/database/repositories.py` | +`strategy_mode` in allowed fields |
| `app/telegram_bot/message_templates.py` | strategy toggle button, settings display, style labels |
| `app/telegram_bot/callbacks.py` | 2 strategy handlers, label updates |
| `supabase/schema.sql` | +column `strategy_mode` |
| `.env.example` | +`STRATEGY_MODE` |
| `tests/test_noise_filter.py` | NEW |
| `tests/test_prompt_builder.py` | NEW |
| `tests/test_config.py` | NEW |
| `tests/test_risk_manager.py` | extend |
| `tests/test_telegram_bot.py` | extend |

## Out of scope

- Heikin-Ashi smoothing (not chosen)
- YAML config-driven prompts (not chosen)
- Risk manager SL/TP range rejection (kept as AI-owned, optional warning only)
- Changing bot_mode (SIGNAL_ONLY / SEMI_AUTO / AUTO_DEMO / LIVE_AUTO) — orthogonal to strategy_mode
- Multi-symbol strategy mode per symbol — strategy_mode is global setting
