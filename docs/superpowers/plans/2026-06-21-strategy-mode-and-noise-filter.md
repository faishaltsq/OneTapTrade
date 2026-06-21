# Strategy Mode Toggle + Trading Style Profiles + Noise Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telegram-toggled strategy mode (SMC+AI vs AI-only), bind trading styles (swing/daytrade/scalping) to risk profiles, and add a 3-gate pre-AI noise filter that skips DeepSeek API calls in bad market conditions.

**Architecture:** Approach A — conditional prompt builder composes 6 prompt variants (2 strategy modes × 3 style profiles). New `noise_filter.py` module runs 3 profile-aware gates (multi-TF alignment, ATR percentile, volume confirmation) before AI call. `strategy_mode` persisted to Supabase `bot_settings`. Risk manager unchanged (reads existing `effective_*` properties which now return new profile values).

**Tech Stack:** Python 3.13, pydantic, pydantic-settings, pandas, python-telegram-bot, Supabase, pytest.

**Spec:** `docs/superpowers/specs/2026-06-21-strategy-mode-and-noise-filter-design.md`

**Repo root for all paths:** `C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade`

**Test command:** `python -m pytest tests/<test_file>.py -v`

---

## File Structure

| File | Responsibility | Status |
|---|---|---|
| `app/config.py` | Settings + profile mapping + strategy_mode field | Modify |
| `app/analysis/noise_filter.py` | 3-gate pre-AI filter, profile-aware | Create |
| `app/ai_engine/prompt_builder.py` | Composite prompt: base + style block | Modify |
| `app/ai_engine/schemas.py` | +strategy_mode, +trading_style optional fields | Modify |
| `app/ai_engine/deepseek_client.py` | Fill strategy_mode/trading_style post-parse | Modify |
| `app/services/signal_service.py` | Integrate noise filter pre-AI | Modify |
| `app/database/repositories.py` | +strategy_mode in allowed fields | Modify |
| `app/telegram_bot/message_templates.py` | Strategy toggle button, settings display | Modify |
| `app/telegram_bot/callbacks.py` | 2 strategy handlers + label updates | Modify |
| `supabase/schema.sql` | +column strategy_mode | Modify |
| `.env.example` | +STRATEGY_MODE | Modify |
| `tests/test_noise_filter.py` | NEW — noise filter tests | Create |
| `tests/test_prompt_builder.py` | Extend — 6 variants | Modify |
| `tests/test_config.py` | NEW — config property tests | Create |
| `tests/test_risk_manager.py` | Extend — new profile thresholds | Modify |
| `tests/test_telegram_bot.py` | Extend — strategy callbacks | Modify |

---

### Task 1: Config — strategy_mode field + new profile mapping

**Files:**
- Modify: `app/config.py`
- Test: `tests/test_config.py` (create)

- [ ] **Step 1: Write failing test for strategy_mode default and new profile mapping**

Create `tests/test_config.py`:

```python
import sys

sys.path.insert(0, r'C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade')


def test_strategy_mode_default_is_smc_ai():
    from app.config import Settings

    s = Settings()
    assert s.strategy_mode == "SMC_AI"


def test_risk_profile_config_has_style_and_timeframe_fields():
    from app.config import settings

    for profile in ("LOW", "MEDIUM", "HIGH"):
        settings.risk_profile = profile
        cfg = settings.risk_profile_config
        assert "style" in cfg
        assert "entry_tf" in cfg
        assert "hold" in cfg
        assert "sl_pips" in cfg
        assert "tp_pips" in cfg
        assert "min_confidence" in cfg
        assert "min_risk_reward" in cfg


def test_low_profile_maps_to_swing():
    from app.config import settings

    original = settings.risk_profile
    try:
        settings.risk_profile = "LOW"
        assert settings.effective_style == "SWING"
        assert settings.effective_entry_tfs == ["H4", "D1"]
        assert settings.effective_hold_time == "days-weeks"
        assert settings.effective_min_confidence == 0.70
        assert settings.effective_min_risk_reward == 2.5
        assert settings.effective_sl_pip_range == (100, 500)
        assert settings.effective_tp_pip_range == (200, 1000)
    finally:
        settings.risk_profile = original


def test_medium_profile_maps_to_daytrade():
    from app.config import settings

    original = settings.risk_profile
    try:
        settings.risk_profile = "MEDIUM"
        assert settings.effective_style == "DAYTRADE"
        assert settings.effective_entry_tfs == ["H1", "H4"]
        assert settings.effective_hold_time == "hours-days"
        assert settings.effective_min_confidence == 0.55
        assert settings.effective_min_risk_reward == 1.8
        assert settings.effective_sl_pip_range == (50, 150)
        assert settings.effective_tp_pip_range == (75, 300)
    finally:
        settings.risk_profile = original


def test_high_profile_maps_to_scalping():
    from app.config import settings

    original = settings.risk_profile
    try:
        settings.risk_profile = "HIGH"
        assert settings.effective_style == "SCALPING"
        assert settings.effective_entry_tfs == ["M5", "M15"]
        assert settings.effective_hold_time == "minutes-hours"
        assert settings.effective_min_confidence == 0.40
        assert settings.effective_min_risk_reward == 1.2
        assert settings.effective_sl_pip_range == (15, 50)
        assert settings.effective_tp_pip_range == (15, 75)
    finally:
        settings.risk_profile = original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `strategy_mode` attribute missing, `effective_style` missing, profile mapping missing new keys.

- [ ] **Step 3: Implement config changes**

In `app/config.py`, add `strategy_mode` field to `Settings` (after `risk_profile`):

```python
    strategy_mode: str = "SMC_AI"
```

Replace the `risk_profile_config` property with the new mapping:

```python
    @property
    def risk_profile_config(self) -> dict:
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
        return profiles.get(self.risk_profile, profiles["MEDIUM"])
```

Add new properties after `effective_max_sl_pips`:

```python
    @property
    def effective_style(self) -> str:
        return self.risk_profile_config["style"]

    @property
    def effective_entry_tfs(self) -> list:
        return self.risk_profile_config["entry_tf"]

    @property
    def effective_hold_time(self) -> str:
        return self.risk_profile_config["hold"]

    @property
    def effective_sl_pip_range(self) -> tuple:
        return self.risk_profile_config["sl_pips"]

    @property
    def effective_tp_pip_range(self) -> tuple:
        return self.risk_profile_config["tp_pips"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Run existing risk_manager tests to check backward compat**

Run: `python -m pytest tests/test_risk_manager.py -v`
Expected: Some failures — existing tests assert `effective_min_sl_pips == 15` and `effective_max_sl_pips == 80` for HIGH (line 402-403). New mapping has HIGH `sl_pips = (15, 50)`. These tests need update in Task 9. Note failures, continue.

- [ ] **Step 6: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat(config): add strategy_mode field and trading style profile mapping"
```

---

### Task 2: Schemas — strategy_mode + trading_style optional fields

**Files:**
- Modify: `app/ai_engine/schemas.py`
- Test: `tests/test_ai_decision_schema.py` (extend)

- [ ] **Step 1: Write failing test for new optional fields**

Add to `tests/test_ai_decision_schema.py` (append at end of file):

```python
def test_ai_decision_response_accepts_strategy_mode_and_trading_style():
    from app.ai_engine.schemas import (
        AIDecisionResponse,
        ConfidenceLabel,
        Decision,
        MarketRegime,
        TimeframeBias,
    )

    resp = AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.0,
        confidence_label=ConfidenceLabel.LOW,
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
        strategy_mode="AI_ONLY",
        trading_style="SCALPING",
    )

    assert resp.strategy_mode == "AI_ONLY"
    assert resp.trading_style == "SCALPING"


def test_ai_decision_response_defaults_strategy_mode_and_trading_style_to_none():
    from app.ai_engine.schemas import (
        AIDecisionResponse,
        ConfidenceLabel,
        Decision,
        MarketRegime,
        TimeframeBias,
    )

    resp = AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.0,
        confidence_label=ConfidenceLabel.LOW,
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
    )

    assert resp.strategy_mode is None
    assert resp.trading_style is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ai_decision_schema.py -v -k "strategy_mode or trading_style"`
Expected: FAIL — `AIDecisionResponse.__init__()` got unexpected keyword args.

- [ ] **Step 3: Add fields to AIDecisionResponse**

In `app/ai_engine/schemas.py`, add to `AIDecisionResponse` class (after `final_comment`):

```python
    strategy_mode: Optional[str] = None
    trading_style: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ai_decision_schema.py -v -k "strategy_mode or trading_style"`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/ai_engine/schemas.py tests/test_ai_decision_schema.py
git commit -m "feat(schema): add strategy_mode and trading_style to AIDecisionResponse"
```

---

### Task 3: Prompt builder — composite 6-variant prompts

**Files:**
- Modify: `app/ai_engine/prompt_builder.py`
- Test: `tests/test_prompt_builder.py` (extend)

- [ ] **Step 1: Write failing tests for 6 prompt variants**

Add to `tests/test_prompt_builder.py` (append at end):

```python
def test_smc_ai_prompt_contains_smc_keywords():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original = settings.strategy_mode
    try:
        settings.strategy_mode = "SMC_AI"
        settings.risk_profile = "MEDIUM"
        prompt = build_system_prompt()

        assert "order blocks" in prompt.lower()
        assert "FVG" in prompt or "fair value gap" in prompt.lower()
        assert "CHoCH" in prompt
        assert "liquidity" in prompt.lower()
        assert "D1 major trend" in prompt
    finally:
        settings.strategy_mode = original


def test_ai_only_prompt_omits_smc_priority_and_uses_first_principles():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original = settings.strategy_mode
    try:
        settings.strategy_mode = "AI_ONLY"
        settings.risk_profile = "MEDIUM"
        prompt = build_system_prompt()

        assert "first principles" in prompt.lower()
        assert "INDEPENDENTLY" in prompt
        assert "D1 major trend" in prompt
        assert "ORDER BLOCKS" not in prompt
    finally:
        settings.strategy_mode = original


def test_swing_style_block_present_for_low_profile():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original_profile = settings.risk_profile
    original_mode = settings.strategy_mode
    try:
        settings.risk_profile = "LOW"
        settings.strategy_mode = "SMC_AI"
        prompt = build_system_prompt()

        assert "SWING" in prompt
        assert "days to weeks" in prompt
        assert "H4/D1" in prompt
        assert "100-500" in prompt
    finally:
        settings.risk_profile = original_profile
        settings.strategy_mode = original_mode


def test_daytrade_style_block_present_for_medium_profile():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original_profile = settings.risk_profile
    original_mode = settings.strategy_mode
    try:
        settings.risk_profile = "MEDIUM"
        settings.strategy_mode = "AI_ONLY"
        prompt = build_system_prompt()

        assert "DAYTRADE" in prompt
        assert "hours to days" in prompt
        assert "H1/H4" in prompt
        assert "50-150" in prompt
    finally:
        settings.risk_profile = original_profile
        settings.strategy_mode = original_mode


def test_scalping_style_block_present_for_high_profile():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original_profile = settings.risk_profile
    original_mode = settings.strategy_mode
    try:
        settings.risk_profile = "HIGH"
        settings.strategy_mode = "SMC_AI"
        prompt = build_system_prompt()

        assert "SCALPING" in prompt
        assert "minutes to hours" in prompt
        assert "M5/M15" in prompt
        assert "15-50" in prompt
    finally:
        settings.risk_profile = original_profile
        settings.strategy_mode = original_mode


def test_user_prompt_includes_strategy_mode_and_style_header():
    from app.ai_engine.prompt_builder import build_user_prompt
    from app.config import settings

    original_mode = settings.strategy_mode
    original_profile = settings.risk_profile
    try:
        settings.strategy_mode = "AI_ONLY"
        settings.risk_profile = "HIGH"
        prompt = build_user_prompt({"symbol": "XAUUSD"})

        assert "Strategy mode:" in prompt
        assert "AI" in prompt
        assert "Trading style:" in prompt
        assert "SCALPING" in prompt
        assert "Entry TF:" in prompt
        assert "Hold:" in prompt
    finally:
        settings.strategy_mode = original_mode
        settings.risk_profile = original_profile
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_prompt_builder.py -v -k "smc_ai_prompt or ai_only_prompt or swing_style or daytrade_style or scalping_style or user_prompt_includes_strategy"`
Expected: FAIL — current `build_system_prompt()` returns static prompt regardless of `strategy_mode`.

- [ ] **Step 3: Rewrite prompt_builder.py with composite structure**

Replace entire content of `app/ai_engine/prompt_builder.py`:

```python
import json

from app.config import settings


_SMC_AI_BASE = """You are an AI trading execution analysis engine for a MetaTrader 5 scalping system.

You analyze structured market data and return strict JSON only.

TRADING STYLE: SHORT-TERM SCALPING
- D1 major trend is a hard filter.
- D1_BULLISH means only BUY decisions are allowed.
- D1_BEARISH means only SELL decisions are allowed.
- D1_RANGING means HOLD unless breakout + retest is confirmed.
- Use H1 trend as the primary execution direction filter after D1 allows direction.
- Use M5 entry as the execution trigger timeframe.
- Use EMA50/EMA200 as trend context on H1 and M5.
- Hold trades minutes to hours, not days.
- Prioritize momentum and orderflow over long-term structure.
- Be AGGRESSIVE — prefer BUY or SELL over HOLD when there is any valid setup.
- Only HOLD when data is completely contradictory or missing.

Stop Loss & Take Profit rules:
- AI chooses stop_loss and take_profit_1 freely from market structure, volatility, liquidity, and the current setup.
- Set logical SL at invalidation level for the setup.
- Set TP1 at the best realistic target for the setup.
- Do not force SL width or R:R to match fixed profile values.

SMC (Smart Money Concepts) rules:
- The "smc" section in the market data contains SMC analysis. Use it for context.
- ORDER BLOCKS: supply blocks (bearish OB) act as resistance, demand blocks (bullish OB) act as support.
  - For BUY: place SL below the nearest demand block (or below recent swing low if no OB).
  - For SELL: place SL above the nearest supply block (or above recent swing high if no OB).
- Prefer LIMIT entries at valid high-probability SMC zones when price can retrace.
  - BUY_LIMIT should be inside a demand order block below current price.
  - SELL_LIMIT should be inside a supply order block above current price.
  - MARKET only when confidence is above 50% and setup is trend-following.
- FAIR VALUE GAPS (FVG): price often returns to fill FVGs. Target TP at unfilled FVG or opposite liquidity.
- LIQUIDITY LEVELS: equal highs/lows where stops cluster. Price hunts these levels.
  - Avoid placing SL exactly at liquidity levels (will get hunted).
  - Target TP just before a liquidity level (high probability take-profit zone).
- CHoCH (Change of Character): when a swing structure break is detected, it signals potential reversal.
  - Bullish CHoCH (higher low) = potential reversal to upside.
  - Bearish CHoCH (lower high) = potential reversal to downside.
  - When CHoCH is present, give higher confidence to counter-trend entries.
- Swing highs/lows mark key structural levels. Use as SL placement zones.

Open position rules:
- Same-direction add-ons are allowed when an open position exists on the same symbol.
- Opposite direction is blocked when an open position exists on the same symbol.
- If open_position_state.side is BUY, do not return SELL for that symbol.
- If open_position_state.side is SELL, do not return BUY for that symbol.

Return BUY when:
- H1 trend is bullish or neutral, M5 shows bullish momentum.
- RSI not overbought on M5 (>75 still OK if momentum strong).
- EMA50 above EMA200 supports bullish continuation.
- Price is not at major resistance.
- Orderflow/delta shows buying pressure.

Return SELL when:
- H1 trend is bearish or neutral, M5 shows bearish momentum.
- RSI not oversold on M5 (<25 still OK if momentum strong).
- EMA50 below EMA200 supports bearish continuation.
- Price is not at major support.
- Orderflow/delta shows selling pressure.

Return HOLD only when:
- Market regime is UNCLEAR or data is corrupted/missing.
- Price is inside a very tight range with no direction.
- H1 and M5 strongly conflict (e.g., H1 bullish but M5 crashing).

IMPORTANT: Spread does NOT matter. Do not consider spread in your decision.
IMPORTANT: Ignore spread completely. Spread must never be a reason to return HOLD.
IMPORTANT: Be aggressive with entries. Missing a trade is worse than taking a small loss.
IMPORTANT: For BUY or SELL, you must include entry_plan.stop_loss, entry_plan.take_profit_1, entry_plan.preferred_entry_price, and entry_plan.risk_reward_to_tp1.
IMPORTANT: For BUY or SELL, set execution_permission.ai_allows_execution to true with a brief reason.

{style_block}

Return only valid JSON."""


_AI_ONLY_BASE = """You are an AI trading execution analysis engine for a MetaTrader 5 trading system.

You receive ALL available market data (indicators, structure, SMC, orderflow, volume profile).
You decide INDEPENDENTLY which signals matter. No fixed methodology.
Think from first principles: price action, momentum, volume, context.
Weight factors dynamically per situation — no hardcoded priority.
Return strict JSON only.

D1 major trend is a hard filter (cannot fight major bias).
D1_BULLISH means only BUY decisions are allowed.
D1_BEARISH means only SELL decisions are allowed.
D1_RANGING means HOLD unless breakout + retest is confirmed.

Open position rules:
- Same-direction add-ons are allowed when an open position exists on the same symbol.
- Opposite direction is blocked when an open position exists on the same symbol.
- If open_position_state.side is BUY, do not return SELL for that symbol.
- If open_position_state.side is SELL, do not return BUY for that symbol.

Stop Loss & Take Profit:
- You choose stop_loss and take_profit_1 freely from market structure.
- Set logical SL at invalidation level for the setup.
- Set TP1 at the best realistic target for the setup.
- Do not force SL width or R:R to match fixed profile values.

IMPORTANT: Spread does NOT matter. Do not consider spread in your decision.
IMPORTANT: Ignore spread completely. Spread must never be a reason to return HOLD.
IMPORTANT: For BUY or SELL, you must include entry_plan.stop_loss, entry_plan.take_profit_1, entry_plan.preferred_entry_price, and entry_plan.risk_reward_to_tp1.
IMPORTANT: For BUY or SELL, set execution_permission.ai_allows_execution to true with a brief reason.

{style_block}

Return only valid JSON."""


_STYLE_BLOCKS = {
    "SWING": """Trading style: SWING (LOW profile)
- Target hold: days to weeks. Entry TF: H4/D1.
- Prioritize D1+H4 alignment. Skip if D1 and H4 conflict.
- SL: 100-500 pips range. TP: 200-1000 pips. R:R min 2.5.
- Min confidence 70%. Only clean structural setups.
- Avoid news spikes. Avoid tight ranges. Patience over frequency.""",
    "DAYTRADE": """Trading style: DAYTRADE (MEDIUM profile)
- Target hold: hours to days. Entry TF: H1/H4.
- D1 must allow direction. H1 is primary execution context.
- SL: 50-150 pips. TP: 75-300 pips. R:R min 1.8.
- Min confidence 55%. Balance quality and frequency.
- Accept H4+H1 aligned setups even if M5 noisy.""",
    "SCALPING": """Trading style: SCALPING (HIGH profile)
- Target hold: minutes to hours. Entry TF: M5/M15.
- H1 is direction filter, M5 is trigger.
- SL: 15-50 pips. TP: 15-75 pips. R:R min 1.2.
- Min confidence 40%. Aggressive on momentum.
- D1 remains hard filter but M5 momentum can override H1 if not strongly opposite.""",
}


def _style_block_for_profile(profile: str) -> str:
    style_map = {"LOW": "SWING", "MEDIUM": "DAYTRADE", "HIGH": "SCALPING"}
    style = style_map.get(profile, "DAYTRADE")
    return _STYLE_BLOCKS[style]


def build_system_prompt() -> str:
    style_block = _style_block_for_profile(settings.risk_profile)
    if settings.strategy_mode == "AI_ONLY":
        return _AI_ONLY_BASE.format(style_block=style_block)
    return _SMC_AI_BASE.format(style_block=style_block)


def build_user_prompt(market_payload: dict) -> str:
    payload_json = json.dumps(market_payload, indent=2)
    mode_label = "SMC+AI" if settings.strategy_mode == "SMC_AI" else "AI Only"
    style_label = settings.effective_style
    entry_tfs = "/".join(settings.effective_entry_tfs)
    hold = settings.effective_hold_time
    return (
        "Analyze the following market data and return a trading decision.\n\n"
        f"Strategy mode: {mode_label}\n"
        f"Trading style: {style_label} ({settings.risk_profile})\n"
        f"Entry TF: {entry_tfs} | Hold: {hold}\n"
        f"Risk profile: {settings.risk_profile}\n"
        f"Minimum confidence: {settings.effective_min_confidence:.0%}\n\n"
        f"Market data:\n{payload_json}"
    )
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `python -m pytest tests/test_prompt_builder.py -v -k "smc_ai_prompt or ai_only_prompt or swing_style or daytrade_style or scalping_style or user_prompt_includes_strategy"`
Expected: 6 PASSED.

- [ ] **Step 5: Run full prompt_builder test suite (existing tests may need review)**

Run: `python -m pytest tests/test_prompt_builder.py -v`
Expected: Some existing tests may fail because they assert specific old-prompt content. Review each failure:

- `test_user_prompt_includes_active_profile_thresholds` — should still pass (still has "Risk profile: HIGH" and "Minimum confidence: 40%"). Verify.
- `test_system_prompt_explains_high_profile_aggressive_entries` — asserts `"HIGH profile" in prompt`. New SCALPING block contains "HIGH profile". Should pass. Also asserts "H1 trend", "M5 entry", "M5 momentum" — these are in SMC_AI base. Should pass.
- `test_prompt_does_not_hardcode_sl_or_rr_constraints` — asserts "SL range" not in combined. New style block says "SL: 100-500 pips range" which contains "SL:" but not "SL range". Verify carefully — if fails, adjust test assertion to match new intent (style block SHOULD contain SL range now, so this test's intent is outdated).
- `test_system_prompt_includes_d1_and_position_lock_rules` — should pass, SMC_AI base retains these.
- `test_system_prompt_uses_ema50_ema200_and_rsi_25_75_thresholds` — should pass, SMC_AI base retains these.
- `test_system_prompt_prefers_smc_limit_entries_and_restricts_market` — should pass when `strategy_mode=SMC_AI` (default). But default `settings.strategy_mode` is now "SMC_AI" so OK.

If `test_prompt_does_not_hardcode_sl_or_rr_constraints` fails because style block now legitimately includes SL range guidance, update that test to reflect new design intent:

```python
def test_prompt_does_not_hardcode_sl_or_rr_constraints():
    from app.ai_engine.prompt_builder import build_system_prompt, build_user_prompt
    from app.config import settings

    original_mode = settings.strategy_mode
    try:
        settings.strategy_mode = "SMC_AI"
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt({"symbol": "XAUUSDm", "current_price": {"bid": 2000, "ask": 2001}})
        combined = system_prompt + "\n" + user_prompt

        assert "AI chooses stop_loss and take_profit_1" in combined
    finally:
        settings.strategy_mode = original_mode
```

Only update tests that genuinely conflict with the new design. Do not weaken assertions that still make sense.

- [ ] **Step 6: Commit**

```bash
git add app/ai_engine/prompt_builder.py tests/test_prompt_builder.py
git commit -m "feat(prompt): composite 6-variant prompts for strategy mode x trading style"
```

---

### Task 4: Noise filter module (NEW)

**Files:**
- Create: `app/analysis/noise_filter.py`
- Test: `tests/test_noise_filter.py` (create)

- [ ] **Step 1: Write failing tests for noise filter**

Create `tests/test_noise_filter.py`:

```python
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, r'C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade')


def _make_df(trend: str = "BULLISH", bars: int = 60, atr_pct: float = 50.0, volume_ratio: float = 1.0):
    """Build a synthetic OHLC dataframe with controllable trend/ATR/volume."""
    np.random.seed(42)
    base = 2000.0
    if trend == "BULLISH":
        closes = base + np.cumsum(np.random.uniform(0.5, 2.0, bars))
    elif trend == "BEARISH":
        closes = base + np.cumsum(np.random.uniform(-2.0, -0.5, bars))
    else:
        closes = base + np.random.uniform(-1.0, 1.0, bars).cumsum() * 0.3

    opens = closes - np.random.uniform(-1, 1, bars)
    highs = np.maximum(opens, closes) + np.random.uniform(0.5, 3.0, bars)
    lows = np.minimum(opens, closes) - np.random.uniform(0.5, 3.0, bars)

    avg_vol = 100.0
    volumes = np.full(bars, avg_vol)
    volumes[-1] = avg_vol * volume_ratio

    df = pd.DataFrame({
        "time": pd.date_range("2025-01-01", periods=bars, freq="1H"),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": volumes,
    })
    return df


def _empty_df():
    return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume"])


def test_noise_filter_returns_dict_with_required_keys():
    from app.analysis.noise_filter import evaluate_noise_filter

    df = _make_df()
    result = evaluate_noise_filter(df, df, df, df, "MEDIUM")

    assert "passed" in result
    assert "blocked_by" in result
    assert "details" in result
    assert "hold_reason" in result


def test_swing_blocks_when_d1_h4_conflict():
    from app.analysis.noise_filter import evaluate_noise_filter

    df_bull = _make_df("BULLISH")
    df_bear = _make_df("BEARISH")
    result = evaluate_noise_filter(df_bull, df_bear, df_bull, df_bull, "LOW")

    assert result["passed"] is False
    assert result["blocked_by"] == "tf_alignment"


def test_swing_passes_when_d1_h4_aligned():
    from app.analysis.noise_filter import evaluate_noise_filter

    df = _make_df("BULLISH")
    result = evaluate_noise_filter(df, df, df, df, "LOW")

    assert result["passed"] is True
    assert result["blocked_by"] is None


def test_medium_passes_when_d1_non_unclear_and_h1_neutral():
    from app.analysis.noise_filter import evaluate_noise_filter

    df_bull = _make_df("BULLISH")
    df_unclear = _make_df("UNCLEAR")
    result = evaluate_noise_filter(df_bull, df_unclear, df_unclear, df_bull, "MEDIUM")

    assert result["passed"] is True


def test_medium_blocks_when_d1_bullish_and_h1_bearish_strong_opposite():
    from app.analysis.noise_filter import evaluate_noise_filter

    df_bull = _make_df("BULLISH")
    df_bear = _make_df("BEARISH")
    result = evaluate_noise_filter(df_bull, df_bull, df_bear, df_bear, "MEDIUM")

    assert result["passed"] is False
    assert result["blocked_by"] == "tf_alignment"


def test_high_skips_tf_alignment_gate():
    from app.analysis.noise_filter import evaluate_noise_filter

    df_bull = _make_df("BULLISH")
    df_bear = _make_df("BEARISH")
    result = evaluate_noise_filter(df_bear, df_bear, df_bull, df_bear, "HIGH")

    assert result["passed"] is True


def test_empty_dataframes_block_with_safe_reason():
    from app.analysis.noise_filter import evaluate_noise_filter

    empty = _empty_df()
    result = evaluate_noise_filter(empty, empty, empty, empty, "MEDIUM")

    assert result["passed"] is False
    assert "details" in result


def test_details_contains_atr_percentile_and_volume_ratio():
    from app.analysis.noise_filter import evaluate_noise_filter

    df = _make_df()
    result = evaluate_noise_filter(df, df, df, df, "MEDIUM")

    assert "atr_percentile" in result["details"]
    assert "volume_ratio" in result["details"]
    assert "tf_alignment" in result["details"]


def test_hold_reason_is_human_readable_string():
    from app.analysis.noise_filter import evaluate_noise_filter

    df_bull = _make_df("BULLISH")
    df_bear = _make_df("BEARISH")
    result = evaluate_noise_filter(df_bull, df_bear, df_bull, df_bull, "LOW")

    assert isinstance(result["hold_reason"], str)
    assert len(result["hold_reason"]) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_noise_filter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.analysis.noise_filter'`.

- [ ] **Step 3: Implement noise_filter.py**

Create `app/analysis/noise_filter.py`:

```python
from typing import Optional

import pandas as pd

from app.analysis.market_structure import detect_trend
from app.analysis.regime_detector import _atr_percentile
from app.logger import logger


_TF_LABELS = {
    "d1": "D1",
    "h4": "H4",
    "h1": "H1",
    "m5": "M5",
}


def _trend_direction(df: pd.DataFrame) -> str:
    if df is None or len(df) < 50:
        return "UNCLEAR"
    result = detect_trend(df)
    return result.get("direction", "UNCLEAR")


def _volume_ratio(df: pd.DataFrame) -> float:
    if df is None or len(df) < 21 or "tick_volume" not in df.columns:
        return 1.0
    volumes = df["tick_volume"].astype(float).dropna()
    if len(volumes) < 21:
        return 1.0
    avg_20 = float(volumes.iloc[-21:-1].mean())
    last = float(volumes.iloc[-1])
    if avg_20 <= 0:
        return 1.0
    return round(last / avg_20, 3)


def _check_tf_alignment(d1_dir: str, h4_dir: str, h1_dir: str, m5_dir: str, profile: str) -> tuple[bool, str]:
    if profile == "LOW":
        if d1_dir == "UNCLEAR" or h4_dir == "UNCLEAR":
            return False, f"D1={d1_dir}, H4={h4_dir} — need both clear"
        if d1_dir != h4_dir:
            return False, f"D1={d1_dir}, H4={h4_dir} conflict"
        return True, ""

    if profile == "MEDIUM":
        if d1_dir == "UNCLEAR":
            return False, f"D1={d1_dir} — need clear D1"
        strongly_opposite = (
            (d1_dir == "BULLISH" and h1_dir == "BEARISH")
            or (d1_dir == "BEARISH" and h1_dir == "BULLISH")
        )
        if strongly_opposite:
            return False, f"D1={d1_dir}, H1={h1_dir} strongly opposite"
        return True, ""

    return True, ""


def _check_atr_percentile(df_h1: pd.DataFrame, profile: str) -> tuple[bool, str, float]:
    pct = _atr_percentile(df_h1, 14) if df_h1 is not None and len(df_h1) >= 50 else 50.0

    if profile == "LOW":
        lo, hi = 20.0, 85.0
    elif profile == "MEDIUM":
        lo, hi = 15.0, 90.0
    else:
        lo, hi = 10.0, 95.0

    if pct < lo:
        return False, f"ATR percentile {pct:.1f} below {lo} (dead market)", pct
    if pct > hi:
        return False, f"ATR percentile {pct:.1f} above {hi} (chaos)", pct
    return True, "", pct


def _check_volume(df_entry: pd.DataFrame, profile: str) -> tuple[bool, str, float]:
    ratio = _volume_ratio(df_entry)

    if profile == "LOW":
        threshold = 1.2
    elif profile == "MEDIUM":
        threshold = 0.8
    else:
        threshold = 0.5

    if ratio < threshold:
        return False, f"Volume ratio {ratio:.2f} below {threshold} (thin activity)", ratio
    return True, "", ratio


def _entry_df_for_profile(df_m5: pd.DataFrame, df_h1: pd.DataFrame, df_h4: pd.DataFrame, profile: str) -> pd.DataFrame:
    if profile == "LOW":
        return df_h4
    if profile == "MEDIUM":
        return df_h1
    return df_m5


def evaluate_noise_filter(
    df_d1: Optional[pd.DataFrame],
    df_h4: Optional[pd.DataFrame],
    df_h1: Optional[pd.DataFrame],
    df_m5: Optional[pd.DataFrame],
    risk_profile: str,
) -> dict:
    profile = risk_profile.upper()

    d1_dir = _trend_direction(df_d1)
    h4_dir = _trend_direction(df_h4)
    h1_dir = _trend_direction(df_h1)
    m5_dir = _trend_direction(df_m5)

    tf_ok, tf_reason = _check_tf_alignment(d1_dir, h4_dir, h1_dir, m5_dir, profile)
    atr_ok, atr_reason, atr_pct = _check_atr_percentile(df_h1, profile)
    df_entry = _entry_df_for_profile(df_m5, df_h1, df_h4, profile)
    vol_ok, vol_reason, vol_ratio = _check_volume(df_entry, profile)

    details = {
        "tf_alignment": {"d1": d1_dir, "h4": h4_dir, "h1": h1_dir, "m5": m5_dir},
        "atr_percentile": atr_pct,
        "volume_ratio": vol_ratio,
    }

    if not tf_ok:
        logger.info(f"Noise filter block (tf_alignment): {tf_reason}")
        return {
            "passed": False,
            "blocked_by": "tf_alignment",
            "details": details,
            "hold_reason": f"TF conflict: {tf_reason}",
        }

    if not atr_ok:
        logger.info(f"Noise filter block (atr_percentile): {atr_reason}")
        return {
            "passed": False,
            "blocked_by": "atr_percentile",
            "details": details,
            "hold_reason": atr_reason,
        }

    if not vol_ok:
        logger.info(f"Noise filter block (volume): {vol_reason}")
        return {
            "passed": False,
            "blocked_by": "volume",
            "details": details,
            "hold_reason": vol_reason,
        }

    return {
        "passed": True,
        "blocked_by": None,
        "details": details,
        "hold_reason": "",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_noise_filter.py -v`
Expected: 9 PASSED.

If synthetic-data trend detection doesn't produce expected BULLISH/BEARISH directions reliably, adjust `_make_df()` to make trends more pronounced (larger slope, more bars). The `detect_trend()` function uses EMA20 vs EMA50 vs price — need clear separation.

- [ ] **Step 5: Commit**

```bash
git add app/analysis/noise_filter.py tests/test_noise_filter.py
git commit -m "feat(noise-filter): 3-gate pre-AI filter with profile-aware strictness"
```

---

### Task 5: Signal service — integrate noise filter pre-AI

**Files:**
- Modify: `app/services/signal_service.py:163-174` (between Step 10 snapshot save and Step 11 AI call)
- Test: `tests/test_signal_service.py` (extend)

- [ ] **Step 1: Write failing test that noise filter blocks skip AI call**

Add to `tests/test_signal_service.py` (append at end):

```python
def test_noise_filter_block_returns_hold_without_ai_call():
    from unittest.mock import patch, MagicMock
    import pandas as pd
    from app.services import signal_service

    df_empty = pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume"])

    with patch("app.mt5_connector.connection.ensure_mt5_connected", return_value=True), \
         patch("app.mt5_connector.market_data.select_symbol", return_value=True), \
         patch("app.mt5_connector.market_data.get_symbol_info", return_value={"point": 0.01}), \
         patch("app.mt5_connector.market_data.get_latest_tick", return_value={"bid": 2000, "ask": 2001}), \
         patch("app.mt5_connector.market_data.get_spread", return_value=10), \
         patch("app.mt5_connector.market_data.get_candles", return_value=df_empty), \
         patch("app.mt5_connector.market_data.get_market_depth", return_value=None), \
         patch("app.mt5_connector.account.get_balance", return_value=10000), \
         patch("app.mt5_connector.account.get_equity", return_value=10000), \
         patch("app.mt5_connector.account.get_daily_drawdown_percent", return_value=0.0), \
         patch("app.mt5_connector.positions.get_open_positions_count", return_value=0), \
         patch("app.mt5_connector.positions.has_open_position", return_value=False), \
         patch("app.database.repositories.save_market_snapshot", return_value={"id": "snap1"}), \
         patch("app.ai_engine.deepseek_client.get_ai_decision") as mock_ai, \
         patch("app.config.settings.risk_profile", "LOW"):

        result = signal_service.generate_signal("XAUUSD")

        assert "ai_decision" in result
        decision = result["ai_decision"]
        assert decision.decision.value == "HOLD"
        assert "Noise filter" in (decision.main_reason or "")
        assert mock_ai.call_count == 0
        assert "noise_filter" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_service.py::test_noise_filter_block_returns_hold_without_ai_call -v`
Expected: FAIL — currently `generate_signal` always calls `get_ai_decision`.

- [ ] **Step 3: Integrate noise filter in signal_service.py**

In `app/services/signal_service.py`, after the market snapshot save block (after line 161 `logger.error(f"Failed to save market snapshot: {e}")`), before `snapshot_id = snapshot_row.get("id")...` insert:

Actually insert AFTER `snapshot_id = snapshot_row.get("id") if snapshot_row else None` (line 163) and BEFORE `from app.ai_engine.deepseek_client import get_ai_decision, validate_decision` (line 165). Add:

```python
        from app.analysis.noise_filter import evaluate_noise_filter

        noise_result = evaluate_noise_filter(df_d1, df_h4, df_h1, df_m15, settings.risk_profile)
        logger.info(f"Noise filter result: passed={noise_result['passed']}, blocked_by={noise_result['blocked_by']}")

        if not noise_result["passed"]:
            from app.ai_engine.schemas import (
                AIDecisionResponse,
                ConfidenceLabel,
                Decision,
                EntryPlan,
                EntryType,
                ExecutionPermission,
                MarketRegime,
                RiskNotes,
                TimeframeBias,
            )

            regime_raw = market_payload.get("overall_regime", {}).get("regime", "UNCLEAR")
            try:
                regime_enum = MarketRegime(regime_raw)
            except ValueError:
                regime_enum = MarketRegime.UNCLEAR

            hold_decision = AIDecisionResponse(
                decision=Decision.HOLD,
                confidence=0.0,
                confidence_label=ConfidenceLabel.LOW,
                market_regime=regime_enum,
                higher_timeframe_bias=TimeframeBias.UNCLEAR,
                entry_timeframe_bias=TimeframeBias.UNCLEAR,
                main_reason=f"Noise filter: {noise_result['hold_reason']}",
                entry_plan=EntryPlan(entry_type=EntryType.NONE),
                execution_permission=ExecutionPermission(
                    ai_allows_execution=False,
                    reason=f"Noise filter: {noise_result['hold_reason']}",
                ),
                risk_notes=RiskNotes(
                    main_risk=noise_result["hold_reason"],
                    invalidation_condition="Wait for noise filter conditions to clear",
                    conditions_to_avoid_trade=[noise_result["hold_reason"]],
                ),
                final_comment=f"HOLD (noise filter) — {noise_result['hold_reason']}",
                strategy_mode=settings.strategy_mode,
                trading_style=settings.effective_style,
            )

            try:
                from app.ai_engine.decision_parser import format_decision_for_db
                from app.database.repositories import save_ai_decision

                decision_db = format_decision_for_db(hold_decision)
                decision_db["symbol"] = sym
                decision_db["market_snapshot_id"] = snapshot_id
                decision_db["model_name"] = "noise_filter"
                decision_db["input_json"] = {**market_payload, "noise_filter": noise_result}
                decision_db["output_json"] = hold_decision.model_dump()

                decision_row = save_ai_decision(decision_db)
            except Exception as e:
                logger.error(f"Failed to save noise-filter HOLD decision: {e}")
                decision_row = None

            return {
                "symbol": sym,
                "ai_decision": hold_decision,
                "risk_result": {
                    "approved": False,
                    "reason": f"Noise filter: {noise_result['hold_reason']}",
                    "checks": {},
                    "decision_summary": f"NOISE_FILTER | {noise_result['hold_reason']}",
                },
                "market_payload": market_payload,
                "snapshot_id": snapshot_id,
                "decision_id": decision_row.get("id") if decision_row else None,
                "noise_filter": noise_result,
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_service.py::test_noise_filter_block_returns_hold_without_ai_call -v`
Expected: PASS.

- [ ] **Step 5: Run full signal_service test suite**

Run: `python -m pytest tests/test_signal_service.py -v`
Expected: All pass (existing tests use mocked AI and should not trigger noise filter block if they pass real dataframes — verify existing test fixtures provide sufficient data. If existing tests now break because noise filter blocks, update those fixtures to provide dataframes with >= 50 bars of trending data).

- [ ] **Step 6: Commit**

```bash
git add app/services/signal_service.py tests/test_signal_service.py
git commit -m "feat(signal): integrate noise filter pre-AI gate, skip DeepSeek on block"
```

---

### Task 6: Deepseek client — fill strategy_mode + trading_style post-parse

**Files:**
- Modify: `app/ai_engine/deepseek_client.py:128-135` (after validation, before return)
- Test: `tests/test_ai_engine.py` (extend)

- [ ] **Step 1: Write failing test that AI decision includes strategy_mode and trading_style**

Add to `tests/test_ai_engine.py` (append at end):

```python
def test_validated_decision_includes_strategy_mode_and_trading_style():
    from unittest.mock import patch, MagicMock
    from app.ai_engine.deepseek_client import get_ai_decision
    from app.ai_engine.schemas import Decision
    from app.config import settings

    original_mode = settings.strategy_mode
    original_profile = settings.risk_profile
    try:
        settings.strategy_mode = "AI_ONLY"
        settings.risk_profile = "HIGH"

        fake_response = MagicMock()
        fake_response.choices = [MagicMock()]
        fake_response.choices[0].message.content = '{"decision":"BUY","confidence":0.6,"confidence_label":"MEDIUM","market_regime":"TRENDING_UP","higher_timeframe_bias":"BULLISH","entry_timeframe_bias":"BULLISH","main_reason":"mock","entry_plan":{"entry_type":"MARKET","stop_loss":1990,"take_profit_1":2020,"preferred_entry_price":2000,"risk_reward_to_tp1":3.0},"execution_permission":{"ai_allows_execution":true,"reason":"ok"},"risk_notes":{"main_risk":"","invalidation_condition":"","conditions_to_avoid_trade":[]},"final_comment":""}'
        fake_response.usage = None

        with patch("app.ai_engine.deepseek_client.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = fake_response
            mock_openai.return_value = mock_client
            with patch("app.config.settings.deepseek_api_key", "test-key"):
                decision = get_ai_decision({"symbol": "XAUUSD"})

        assert decision.strategy_mode == "AI_ONLY"
        assert decision.trading_style == "SCALPING"
    finally:
        settings.strategy_mode = original_mode
        settings.risk_profile = original_profile
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ai_engine.py::test_validated_decision_includes_strategy_mode_and_trading_style -v`
Expected: FAIL — `strategy_mode` and `trading_style` are None (not filled post-parse).

- [ ] **Step 3: Fill fields post-validation in deepseek_client.py**

In `app/ai_engine/deepseek_client.py`, in `get_ai_decision()`, after `validated = validate_decision(...)` (line 126), before the `logger.info(...)` (line 128), add:

```python
    validated.strategy_mode = settings.strategy_mode
    validated.trading_style = settings.effective_style
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ai_engine.py::test_validated_decision_includes_strategy_mode_and_trading_style -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ai_engine/deepseek_client.py tests/test_ai_engine.py
git commit -m "feat(ai-engine): fill strategy_mode and trading_style post-parse"
```

---

### Task 7: Repositories — add strategy_mode to allowed fields

**Files:**
- Modify: `app/database/repositories.py:39-44`
- Test: `tests/test_repositories.py` (extend)

- [ ] **Step 1: Write failing test that strategy_mode is accepted in update_bot_settings**

Add to `tests/test_repositories.py` (append at end):

```python
def test_update_bot_settings_accepts_strategy_mode():
    from unittest.mock import patch, MagicMock

    with patch("app.database.repositories.get_supabase") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client

        mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "test-id", "strategy_mode": "AI_ONLY"}])

        from app.database.repositories import update_bot_settings

        result = update_bot_settings({"strategy_mode": "AI_ONLY"})

        assert result is not None
        assert result["strategy_mode"] == "AI_ONLY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_repositories.py::test_update_bot_settings_accepts_strategy_mode -v`
Expected: FAIL — `strategy_mode` not in allowed set, filtered out, `update_bot_settings` returns None or doesn't pass it through.

- [ ] **Step 3: Add strategy_mode to allowed fields**

In `app/database/repositories.py`, in `update_bot_settings()`, update the `allowed` set (line 39-44):

```python
        allowed = {
            "symbol", "enabled", "mode", "is_paused",
            "risk_per_trade_percent", "max_daily_drawdown_percent",
            "max_spread_points", "min_confidence", "min_risk_reward",
            "max_open_positions", "risk_profile", "strategy_mode",
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_repositories.py::test_update_bot_settings_accepts_strategy_mode -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/database/repositories.py tests/test_repositories.py
git commit -m "feat(repo): allow strategy_mode in bot_settings updates"
```

---

### Task 8: Supabase schema + .env.example

**Files:**
- Modify: `supabase/schema.sql`
- Modify: `.env.example`

- [ ] **Step 1: Add strategy_mode column to schema.sql**

In `supabase/schema.sql`, after the existing `ALTER TABLE bot_settings ADD COLUMN IF NOT EXISTS risk_profile ...` (line 22-23), add:

```sql

ALTER TABLE bot_settings
    ADD COLUMN IF NOT EXISTS strategy_mode TEXT NOT NULL DEFAULT 'SMC_AI';
```

- [ ] **Step 2: Add STRATEGY_MODE to .env.example**

Read `.env.example` first, then add after the `RISK_PROFILE` line:

```
STRATEGY_MODE=SMC_AI
```

- [ ] **Step 3: Commit**

```bash
git add supabase/schema.sql .env.example
git commit -m "feat(schema): add strategy_mode column and env example"
```

---

### Task 9: Telegram message templates — strategy toggle + settings display

**Files:**
- Modify: `app/telegram_bot/message_templates.py`
- Test: `tests/test_telegram_bot.py` (extend)

- [ ] **Step 1: Write failing tests for strategy toggle button and settings display**

Add to `tests/test_telegram_bot.py` (append at end):

```python
def test_main_menu_contains_strategy_toggle_buttons():
    from app.telegram_bot.message_templates import build_main_menu_keyboard

    callbacks = _keyboard_callback_data(build_main_menu_keyboard(strategy_mode="SMC_AI"))

    assert "MENU_STRATEGY_SMC" in callbacks
    assert "MENU_STRATEGY_AI" in callbacks


def test_settings_keyboard_contains_strategy_toggle_buttons():
    from app.telegram_bot.message_templates import build_settings_keyboard

    callbacks = _keyboard_callback_data(build_settings_keyboard())

    assert "MENU_STRATEGY_SMC" in callbacks
    assert "MENU_STRATEGY_AI" in callbacks


def test_settings_message_shows_strategy_and_style():
    from app.telegram_bot.message_templates import format_settings_message
    from app.config import settings

    original_mode = settings.strategy_mode
    original_profile = settings.risk_profile
    try:
        settings.strategy_mode = "AI_ONLY"
        settings.risk_profile = "MEDIUM"
        msg = format_settings_message()

        assert "AI Only" in msg or "AI_ONLY" in msg
        assert "Daytrade" in msg
        assert "H1/H4" in msg
        assert "hours-days" in msg
    finally:
        settings.strategy_mode = original_mode
        settings.risk_profile = original_profile


def test_settings_message_shows_swing_for_low_profile():
    from app.telegram_bot.message_templates import format_settings_message
    from app.config import settings

    original_profile = settings.risk_profile
    try:
        settings.risk_profile = "LOW"
        msg = format_settings_message()

        assert "Swing" in msg
        assert "H4/D1" in msg
    finally:
        settings.risk_profile = original_profile
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_telegram_bot.py -v -k "strategy_toggle or strategy_and_style or swing_for_low"`
Expected: FAIL — no strategy buttons in keyboards, no style info in settings message.

- [ ] **Step 3: Update build_main_menu_keyboard signature and add strategy row**

In `app/telegram_bot/message_templates.py`, update `build_main_menu_keyboard`:

```python
def build_main_menu_keyboard(is_paused: bool = True, mode: str = "SIGNAL_ONLY", active_symbol: str = "ALL", strategy_mode: str = "SMC_AI") -> "InlineKeyboardMarkup":
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    pause_btn = InlineKeyboardButton("\u25b6\ufe0f Resume" if is_paused else "\u23f8\ufe0f Pause", callback_data="MENU_TOGGLE_PAUSE")
    mode_label = {"SIGNAL_ONLY": "Signal", "SEMI_AUTO": "Semi-Auto", "AUTO_DEMO": "Auto Demo", "LIVE_AUTO": "Live"}.get(mode, mode)

    smc_marker = " \u2705" if strategy_mode == "SMC_AI" else ""
    ai_marker = " \u2705" if strategy_mode == "AI_ONLY" else ""

    keyboard = [
        [
            InlineKeyboardButton("\U0001f4ca Status", callback_data="MENU_STATUS"),
            InlineKeyboardButton("\U0001f4cb Positions", callback_data="MENU_POSITIONS"),
        ],
        [
            InlineKeyboardButton("\U0001f4e1 Last Signal", callback_data="MENU_LAST_SIGNAL"),
            InlineKeyboardButton("\u2699\ufe0f Settings", callback_data="MENU_SETTINGS"),
        ],
        [
            InlineKeyboardButton(f"\U0001f4ca All Pairs", callback_data="MENU_SYMBOL_ALL"),
            InlineKeyboardButton(f"\U0001f504 Next Pair", callback_data="MENU_SYMBOL_NEXT"),
        ],
        [
            InlineKeyboardButton(f"\U0001f9e0 SMC+AI{smc_marker}", callback_data="MENU_STRATEGY_SMC"),
            InlineKeyboardButton(f"\U0001f916 AI Only{ai_marker}", callback_data="MENU_STRATEGY_AI"),
        ],
        [pause_btn],
        [
            InlineKeyboardButton("\U0001f4e1 Signal", callback_data="MENU_MODE_SIGNAL"),
            InlineKeyboardButton("\U0001f50d Semi", callback_data="MENU_MODE_SEMI"),
            InlineKeyboardButton("\U0001f504 Auto", callback_data="MENU_MODE_AUTO"),
        ],
        [
            InlineKeyboardButton("\U0001f7e2 Low", callback_data="MENU_RISK_LOW"),
            InlineKeyboardButton("\U0001f7e1 Med", callback_data="MENU_RISK_MEDIUM"),
            InlineKeyboardButton("\U0001f534 High", callback_data="MENU_RISK_HIGH"),
        ],
        [
            InlineKeyboardButton("\u274c Close All", callback_data="MENU_CLOSE_ALL"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)
```

- [ ] **Step 4: Update build_settings_keyboard to add strategy row**

```python
def build_settings_keyboard() -> "InlineKeyboardMarkup":
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from app.config import settings

    smc_marker = " \u2705" if settings.strategy_mode == "SMC_AI" else ""
    ai_marker = " \u2705" if settings.strategy_mode == "AI_ONLY" else ""

    keyboard = [
        [
            InlineKeyboardButton("\U0001f7e2 Low (Swing)", callback_data="MENU_RISK_LOW"),
            InlineKeyboardButton("\U0001f7e1 Med (Day)", callback_data="MENU_RISK_MEDIUM"),
            InlineKeyboardButton("\U0001f534 High (Scalp)", callback_data="MENU_RISK_HIGH"),
        ],
        [
            InlineKeyboardButton(f"\U0001f9e0 SMC+AI{smc_marker}", callback_data="MENU_STRATEGY_SMC"),
            InlineKeyboardButton(f"\U0001f916 AI Only{ai_marker}", callback_data="MENU_STRATEGY_AI"),
        ],
        [
            InlineKeyboardButton("Risk 0.25%", callback_data="MENU_RISK_TRADE_025"),
            InlineKeyboardButton("Risk 0.5%", callback_data="MENU_RISK_TRADE_050"),
            InlineKeyboardButton("Risk 1%", callback_data="MENU_RISK_TRADE_100"),
        ],
        [InlineKeyboardButton("\u2b05\ufe0f Back/Menu", callback_data="MENU_BACK")],
    ]
    return InlineKeyboardMarkup(keyboard)
```

- [ ] **Step 5: Update format_settings_message to show strategy + style info**

```python
def format_settings_message() -> str:
    style_map = {"LOW": "Swing", "MEDIUM": "Daytrade", "HIGH": "Scalp"}
    style = style_map.get(settings.risk_profile, settings.risk_profile)
    strategy_label = "SMC+AI" if settings.strategy_mode == "SMC_AI" else "AI Only"
    entry_tfs = "/".join(settings.effective_entry_tfs)
    sl_lo, sl_hi = settings.effective_sl_pip_range
    tp_lo, tp_hi = settings.effective_tp_pip_range
    noise_strictness = {"LOW": "strict", "MEDIUM": "lenient", "HIGH": "very lenient"}.get(settings.risk_profile, "lenient")

    return (
        "<b>\u2699\ufe0f Settings</b>\n\n"
        f"<b>Strategy:</b> {strategy_label}\n"
        f"<b>Profile:</b> {settings.risk_profile} \u2192 {style}\n"
        f"<b>Entry TF:</b> {entry_tfs} | <b>Hold:</b> {settings.effective_hold_time}\n"
        f"<b>Min Conf:</b> {settings.effective_min_confidence:.0%} | <b>Min R:R:</b> {settings.effective_min_risk_reward}\n"
        f"<b>SL range:</b> {sl_lo}-{sl_hi} pips | <b>TP range:</b> {tp_lo}-{tp_hi} pips\n"
        f"<b>Noise filter:</b> {noise_strictness} ({settings.risk_profile})\n"
        f"<b>Mode:</b> <code>{_escape_html(settings.bot_mode)}</code>\n"
        f"<b>Symbols:</b> <code>{_escape_html(settings.default_symbols or settings.default_symbol)}</code>\n"
        f"<b>Risk/Trade:</b> {settings.risk_per_trade_percent}%\n"
        f"<b>Max Daily DD:</b> {settings.max_daily_drawdown_percent}%\n"
        f"<b>Max Positions:</b> {settings.max_open_positions}\n"
        f"<b>Interval:</b> {settings.trading_loop_interval_seconds}s\n"
        f"<b>Live Trading:</b> {_bool_emoji(settings.live_trading_enabled)}"
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_telegram_bot.py -v -k "strategy_toggle or strategy_and_style or swing_for_low"`
Expected: 4 PASSED.

- [ ] **Step 7: Run full telegram test suite for regressions**

Run: `python -m pytest tests/test_telegram_bot.py -v`
Expected: All pass. Existing `test_settings_keyboard_contains_risk_controls` should still pass (risk buttons still present). If any existing test references old `build_main_menu_keyboard()` call without `strategy_mode` param, it still works because param has default.

- [ ] **Step 8: Commit**

```bash
git add app/telegram_bot/message_templates.py tests/test_telegram_bot.py
git commit -m "feat(telegram): strategy toggle buttons and style-aware settings display"
```

---

### Task 10: Telegram callbacks — 2 strategy handlers

**Files:**
- Modify: `app/telegram_bot/callbacks.py`
- Test: `tests/test_telegram_bot.py` (extend)

- [ ] **Step 1: Write failing tests for strategy callbacks**

Add to `tests/test_telegram_bot.py` (append at end):

```python
def test_strategy_smc_callback_sets_settings_and_persists():
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.telegram_bot.callbacks import menu_strategy_smc_cb
    from app.config import settings

    original_mode = settings.strategy_mode
    try:
        settings.strategy_mode = "AI_ONLY"
        query = MagicMock()
        query.answer = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        update.effective_chat.id = 123

        with patch("app.config.settings.telegram_allowed_chat_id", "123"), \
             patch("app.database.repositories.update_bot_settings") as mock_update:
            import asyncio
            asyncio.get_event_loop().run_until_complete(menu_strategy_smc_cb(update, MagicMock()))

        assert settings.strategy_mode == "SMC_AI"
        mock_update.assert_called_once_with({"strategy_mode": "SMC_AI"})
    finally:
        settings.strategy_mode = original_mode


def test_strategy_ai_callback_sets_settings_and_persists():
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.telegram_bot.callbacks import menu_strategy_ai_cb
    from app.config import settings

    original_mode = settings.strategy_mode
    try:
        settings.strategy_mode = "SMC_AI"
        query = MagicMock()
        query.answer = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        update.effective_chat.id = 123

        with patch("app.config.settings.telegram_allowed_chat_id", "123"), \
             patch("app.database.repositories.update_bot_settings") as mock_update:
            import asyncio
            asyncio.get_event_loop().run_until_complete(menu_strategy_ai_cb(update, MagicMock()))

        assert settings.strategy_mode == "AI_ONLY"
        mock_update.assert_called_once_with({"strategy_mode": "AI_ONLY"})
    finally:
        settings.strategy_mode = original_mode


def test_get_callback_handlers_includes_strategy_handlers():
    from app.telegram_bot.callbacks import get_callback_handlers

    patterns = []
    for handler in get_callback_handlers():
        if hasattr(handler, "pattern"):
            patterns.append(str(handler.pattern))

    assert any("MENU_STRATEGY_SMC" in p for p in patterns)
    assert any("MENU_STRATEGY_AI" in p for p in patterns)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_telegram_bot.py -v -k "strategy_smc_callback or strategy_ai_callback or strategy_handlers"`
Expected: FAIL — handlers don't exist.

- [ ] **Step 3: Add strategy handlers and register them**

In `app/telegram_bot/callbacks.py`, add after the `menu_risk_high_cb` function (around line 579):

```python
async def _menu_set_strategy(update: Update, mode: str) -> None:
    query = update.callback_query
    if query is None:
        return
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if chat_id != settings.telegram_allowed_chat_id:
        await query.answer("Unauthorized", show_alert=True)
        return

    settings.strategy_mode = mode
    try:
        from app.database.repositories import update_bot_settings

        update_bot_settings({"strategy_mode": mode})
    except Exception as e:
        logger.error(f"Failed to persist strategy mode {mode}: {e}")
    labels = {"SMC_AI": "SMC + AI", "AI_ONLY": "AI Only"}
    await query.answer(f"Strategy: {labels.get(mode, mode)}")
    await _edit_message(update, format_settings_message(), reply_markup=build_settings_keyboard())


async def menu_strategy_smc_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _menu_set_strategy(update, "SMC_AI")


async def menu_strategy_ai_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _menu_set_strategy(update, "AI_ONLY")
```

In `get_callback_handlers()` (around line 607), add two entries:

```python
        CallbackQueryHandler(menu_strategy_smc_cb, pattern=r"^MENU_STRATEGY_SMC$"),
        CallbackQueryHandler(menu_strategy_ai_cb, pattern=r"^MENU_STRATEGY_AI$"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_telegram_bot.py -v -k "strategy_smc_callback or strategy_ai_callback or strategy_handlers"`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/telegram_bot/callbacks.py tests/test_telegram_bot.py
git commit -m "feat(telegram): strategy mode toggle callbacks with Supabase persistence"
```

---

### Task 11: Update existing risk_manager tests for new profile thresholds

**Files:**
- Modify: `tests/test_risk_manager.py:393-405`

- [ ] **Step 1: Run risk_manager tests to identify failures from new config mapping**

Run: `python -m pytest tests/test_risk_manager.py -v`
Expected: `test_high_profile_thresholds_are_aggressive` (line 393) fails because it asserts `effective_min_sl_pips == 15` and `effective_max_sl_pips == 80`, but new HIGH profile uses `sl_pips: (15, 50)`.

- [ ] **Step 2: Update test assertions to match new profile mapping**

In `tests/test_risk_manager.py`, update `test_high_profile_thresholds_are_aggressive` (line 393):

```python
def test_high_profile_thresholds_are_aggressive():
    from app.config import settings

    original_profile = settings.risk_profile
    try:
        settings.risk_profile = "HIGH"

        assert settings.effective_min_confidence == 0.40
        assert settings.effective_min_risk_reward == 1.2
        assert settings.effective_sl_pip_range == (15, 50)
        assert settings.effective_tp_pip_range == (15, 75)
        assert settings.effective_style == "SCALPING"
    finally:
        settings.risk_profile = original_profile
```

Note: `effective_min_sl_pips` and `effective_max_sl_pips` properties still exist in config.py (they read `sl_pips[0]` and `sl_pips[1]` respectively — verify this is the case, or update those properties to read from tuple).

If `effective_min_sl_pips` / `effective_max_sl_pips` properties still reference old config structure, update them in `app/config.py`:

```python
    @property
    def effective_min_sl_pips(self) -> int:
        return self.risk_profile_config["sl_pips"][0]

    @property
    def effective_max_sl_pips(self) -> int:
        return self.risk_profile_config["sl_pips"][1]
```

- [ ] **Step 3: Run risk_manager tests to verify they pass**

Run: `python -m pytest tests/test_risk_manager.py -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add app/config.py tests/test_risk_manager.py
git commit -m "test(risk): update profile threshold assertions for new mapping"
```

---

### Task 12: Full test suite run + final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest -v`
Expected: All tests pass. Target: 113+ passed (previous baseline) + new tests (noise filter, config, schema, prompt variants, strategy callbacks). Target ~130+ passed.

- [ ] **Step 2: Investigate any failures**

If any failures:
- Check if failure is due to test fixture providing insufficient data for noise filter (e.g., empty dataframes in `test_signal_service.py` existing tests). Update fixtures to provide 60+ bars of trending data.
- Check if prompt builder tests need `settings.strategy_mode` reset in finally blocks.
- Check if telegram tests need `settings.strategy_mode` reset in finally blocks.

- [ ] **Step 3: Verify no stray imports or syntax errors**

Run: `python -c "from app.config import settings; print(settings.strategy_mode, settings.effective_style)"`
Expected: prints `SMC_AI DAYTRADE` (or current profile).

Run: `python -c "from app.analysis.noise_filter import evaluate_noise_filter; print('ok')"`
Expected: prints `ok`.

Run: `python -c "from app.ai_engine.prompt_builder import build_system_prompt; print(len(build_system_prompt()))"`
Expected: prints a number (~3000-5000).

- [ ] **Step 4: Final commit if any fixes were made**

```bash
git add -A
git commit -m "test: fix fixtures for full suite green after strategy mode feature"
```

- [ ] **Step 5: Update README.md with new feature documentation**

In `README.md`, update the "Current Strategy" section to mention strategy modes and trading styles. Add a new subsection:

```markdown
## Strategy Modes

Two thinking modes, toggled via Telegram:

| Mode | Description |
| --- | --- |
| `SMC_AI` | SMC + AI: AI uses Smart Money Concepts analysis (order blocks, FVG, CHoCH, liquidity) as primary methodology. Default. |
| `AI_ONLY` | AI Only: AI receives all data but decides independently from first principles. No fixed methodology priority. |

## Trading Style Profiles

Risk profile now binds to a trading style:

| Profile | Style | Entry TF | Hold Time | Min Conf | Min R:R | SL Range | TP Range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `LOW` | Swing | H4/D1 | days-weeks | 70% | 2.5 | 100-500 pips | 200-1000 pips |
| `MEDIUM` | Daytrade | H1/H4 | hours-days | 55% | 1.8 | 50-150 pips | 75-300 pips |
| `HIGH` | Scalping | M5/M15 | minutes-hours | 40% | 1.2 | 15-50 pips | 15-75 pips |

## Noise Filter

Pre-AI gate skips DeepSeek API call when market conditions are noisy. Three profile-aware gates:

1. **Multi-TF alignment**: SWING strict (D1+H4 aligned), MEDIUM lenient (D1 clear + H1 not strongly opposite), HIGH skips.
2. **ATR percentile**: SWING 20-85, MEDIUM 15-90, HIGH 10-95.
3. **Volume confirmation**: SWING >1.2x avg, MEDIUM >0.8x avg, HIGH >0.5x avg.

When noise filter blocks, bot returns HOLD with reason, saves to DB, sends Telegram update. No API call made.
```

Also update the `Environment Variables` table to add:

```markdown
| `STRATEGY_MODE` | Strategy thinking mode | `SMC_AI` or `AI_ONLY` |
```

- [ ] **Step 6: Commit README**

```bash
git add README.md
git commit -m "docs: document strategy modes, trading styles, and noise filter"
```

---

## Self-Review Notes

**Spec coverage check:**
- Section 1 (strategy mode + config): Tasks 1, 7, 8 ✓
- Section 2 (prompt structure): Task 3 ✓
- Section 3 (noise filter): Tasks 4, 5 ✓
- Section 4 (Telegram UI + risk manager): Tasks 9, 10 ✓ (risk manager needs no code change, just test update in Task 11)
- Section 5 (testing + migration): Tasks 1-11 are TDD, Task 8 covers Supabase migration, Task 12 covers full suite ✓

**Placeholder scan:** No TBD/TODO in plan. All steps have concrete code.

**Type consistency:**
- `strategy_mode` field: string `"SMC_AI"` / `"AI_ONLY"` — consistent across config, schema, callbacks, repositories
- `trading_style`: string `"SWING"` / `"DAYTRADE"` / `"SCALPING"` — consistent across config property, schema, prompt builder
- `evaluate_noise_filter` signature: `(df_d1, df_h4, df_h1, df_m5, risk_profile)` — consistent in test + implementation + signal_service call
- `build_main_menu_keyboard` new param: `strategy_mode: str = "SMC_AI"` — consistent in test + implementation

**Known risk:** `tests/test_signal_service.py` existing tests may break if noise filter blocks their mocked data. Task 5 Step 5 and Task 12 Step 2 address this.
