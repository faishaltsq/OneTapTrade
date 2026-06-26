# SMC Probability Quality Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic SMC probability scoring, quality filtering, strict DeepSeek review context, and professional Telegram output without changing the core app flow or replacing existing SMC detection.

**Architecture:** Add a focused `smc_probability` helper that computes a rule-based score from existing market payload data. Integrate the score into `signal_service`, `risk_manager`, `prompt_builder`, and Telegram formatting using existing `BUY`/`SELL`/`HOLD` decisions while keeping `BUY_SETUP`/`SELL_SETUP`/`WAIT`/`NO_TRADE` as metadata.

**Tech Stack:** Python 3.13, pytest, pydantic settings, existing DeepSeek/OpenAI client, existing Telegram bot module.

---

## File Structure

- Create `app/analysis/smc_probability.py`: deterministic SMC score engine, profile timeframe model, semantic-to-core decision helpers, fallback decision builder.
- Create `tests/test_smc_probability.py`: pure unit tests for score rules and profile mapping.
- Modify `app/config.py`: optional env fields `min_signal_probability`, `send_no_trade_alert`, `enable_ai_review`.
- Modify `.env.example`: document optional env defaults.
- Modify `README.md`: short enhancement notes.
- Modify `app/services/signal_service.py`: fetch optional M15 candles, run deterministic score, pass score to AI/risk, fallback to score when AI unavailable.
- Modify `app/risk/risk_manager.py`: hard-gate low probability and `NO_TRADE` semantics before execution approval.
- Modify `app/ai_engine/prompt_builder.py`: remove aggressive spread-ignore SMC prompt wording, include deterministic score in compact prompt.
- Modify `app/telegram_bot/message_templates.py`: render SMC analysis block when score exists.
- Modify `app/telegram_bot/bot.py`: suppress `NO_TRADE` and below-threshold Telegram sends safely.
- Modify focused tests already present in `tests/test_config.py`, `tests/test_prompt_builder.py`, `tests/test_telegram_bot.py`, and add integration-style tests in `tests/test_signal_service.py` or `tests/test_risk_manager.py`.

---

### Task 1: Add Optional Config Fields

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config test**

Add to `tests/test_config.py`:

```python
def test_smc_probability_config_defaults():
    from app.config import Settings

    settings = Settings(_env_file=None)

    assert settings.min_signal_probability == 70
    assert settings.send_no_trade_alert is False
    assert settings.enable_ai_review is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_smc_probability_config_defaults -v`

Expected: FAIL with `AttributeError` or pydantic validation error because fields do not exist.

- [ ] **Step 3: Add config fields**

In `app/config.py`, add fields near existing risk and strategy config:

```python
    min_signal_probability: int = 70
    send_no_trade_alert: bool = False
    enable_ai_review: bool = True
```

- [ ] **Step 4: Document env defaults**

Add to `.env.example` near trading/risk config:

```env
# SMC probability quality filter
MIN_SIGNAL_PROBABILITY=70
SEND_NO_TRADE_ALERT=false
ENABLE_AI_REVIEW=true
```

Add to `README.md` configuration section:

```markdown
### SMC Probability Quality Filter

- `MIN_SIGNAL_PROBABILITY` filters weak SMC setups before Telegram/execution. Default: `70`.
- `SEND_NO_TRADE_ALERT` sends suppressed `NO_TRADE` analysis when enabled. Default: `false`.
- `ENABLE_AI_REVIEW` keeps DeepSeek review after deterministic scoring. Default: `true`.
```

- [ ] **Step 5: Verify config test passes**

Run: `pytest tests/test_config.py::test_smc_probability_config_defaults -v`

Expected: PASS.

- [ ] **Step 6: Commit this task**

Run:

```bash
git add app/config.py .env.example README.md tests/test_config.py
git commit -m "feat: add smc probability config"
```

---

### Task 2: Add Deterministic SMC Probability Scorer

**Files:**
- Create: `app/analysis/smc_probability.py`
- Test: `tests/test_smc_probability.py`

- [ ] **Step 1: Write failing scorer tests**

Create `tests/test_smc_probability.py`:

```python
from app.analysis.smc_probability import core_decision_from_semantic, score_smc_setup


def _payload(direction="bullish", spread=10, rr=2.0, profile="MEDIUM"):
    filter_trend = "BULLISH" if direction == "bullish" else "BEARISH"
    execution_trend = filter_trend
    return {
        "symbol": "EURUSD.m",
        "current_price": {"bid": 1.1000, "ask": 1.1002, "mid": 1.1001, "spread_points": spread},
        "risk_config": {"risk_profile": profile, "min_risk_reward": 1.5},
        "major_trend": {"bias": "D1_BULLISH" if direction == "bullish" else "D1_BEARISH", "allowed_directions": ["BUY" if direction == "bullish" else "SELL"]},
        "higher_timeframe": {"timeframe": "D1", "market_structure": {"trend": filter_trend}, "current_candle": {"close": 1.1001}},
        "secondary_timeframe": {"timeframe": "H4", "market_structure": {"trend": filter_trend}, "current_candle": {"close": 1.1001}},
        "primary_timeframe": {"timeframe": "H1", "market_structure": {"trend": execution_trend}, "current_candle": {"close": 1.1001}},
        "entry_timeframe": {"timeframe": "M5", "market_structure": {"trend": execution_trend}, "current_candle": {"close": 1.1001}},
        "profile_timeframes": {"M15": {"timeframe": "M15", "market_structure": {"trend": execution_trend}, "current_candle": {"close": 1.1001}}},
        "smc": {
            "choch": {"m5": {"bullish_choch": [{"price": 1.0990}], "bearish_choch": []}},
            "liquidity_levels": [{"type": "low", "price": 1.0985}],
            "fvg_zones": [{"direction": direction, "top": 1.1010, "bottom": 1.1000}],
            "order_blocks": {"demand": [{"low": 1.0980, "high": 1.0990}], "supply": [{"low": 1.1020, "high": 1.1030}]},
            "h1_swings": {"highs": [{"price": 1.1050}], "lows": [{"price": 1.0950}]},
            "m5_swings": {"highs": [{"price": 1.1030}], "lows": [{"price": 1.0980}]},
        },
        "entry_plan_context": {"risk_reward_to_tp1": rr, "entry_available": True, "sl_available": True, "tp_available": True},
    }


def test_aligned_bullish_returns_buy_setup():
    result = score_smc_setup(_payload("bullish"), risk_profile="MEDIUM")

    assert result["pre_ai_decision"] == "BUY_SETUP"
    assert result["bias"] == "bullish"
    assert result["final_score"] >= 70
    assert core_decision_from_semantic(result["pre_ai_decision"]) == "BUY"


def test_structure_conflict_lowers_probability_to_wait():
    payload = _payload("bullish")
    payload["primary_timeframe"]["market_structure"]["trend"] = "BEARISH"

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["final_score"] < 70
    assert result["pre_ai_decision"] in {"WAIT", "NO_TRADE"}
    assert any(adj["factor"] == "structure_conflict" for adj in result["adjustments"])


def test_high_spread_forces_no_trade():
    result = score_smc_setup(_payload("bullish", spread=999), risk_profile="MEDIUM")

    assert result["pre_ai_decision"] == "NO_TRADE"
    assert result["forced_no_trade"] is True
    assert any(adj["factor"] == "spread_high" for adj in result["adjustments"])


def test_low_rr_forces_no_trade():
    result = score_smc_setup(_payload("bullish", rr=1.0), risk_profile="MEDIUM")

    assert result["pre_ai_decision"] == "NO_TRADE"
    assert any(adj["factor"] == "risk_reward_low" for adj in result["adjustments"])


def test_missing_levels_requires_manual_confirmation():
    payload = _payload("bullish")
    payload["entry_plan_context"] = {"risk_reward_to_tp1": None, "entry_available": False, "sl_available": False, "tp_available": False}

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["entry_sl_tp_note"] == "manual confirmation required"
    assert "manual confirmation required" in result["risk_notes"]


def test_high_profile_uses_h1_h4_filter_and_m5_m15_execution():
    result = score_smc_setup(_payload("bullish", profile="HIGH"), risk_profile="HIGH")

    assert result["timeframe_model"]["filter_timeframes"] == ["H1", "H4"]
    assert result["timeframe_model"]["execution_timeframes"] == ["M5", "M15"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_smc_probability.py -v`

Expected: FAIL with import error because `app.analysis.smc_probability` does not exist.

- [ ] **Step 3: Create scorer implementation**

Create `app/analysis/smc_probability.py`:

```python
from __future__ import annotations

from app.config import settings


SEMANTIC_TO_CORE = {
    "BUY_SETUP": "BUY",
    "SELL_SETUP": "SELL",
    "WAIT": "HOLD",
    "NO_TRADE": "HOLD",
}


def core_decision_from_semantic(decision: str) -> str:
    return SEMANTIC_TO_CORE.get(str(decision).upper(), "HOLD")


def _profile_model(profile: str) -> dict:
    profile = str(profile or "MEDIUM").upper()
    if profile == "LOW":
        return {"profile": "LOW", "filter_timeframes": ["D1", "H4"], "execution_timeframes": ["H4", "D1"], "timeframe_fallback": None}
    if profile == "HIGH":
        return {"profile": "HIGH", "filter_timeframes": ["H1", "H4"], "execution_timeframes": ["M5", "M15"], "timeframe_fallback": None}
    return {"profile": "MEDIUM", "filter_timeframes": ["D1", "H4"], "execution_timeframes": ["H1"], "timeframe_fallback": None}


def _section(payload: dict, timeframe: str) -> dict:
    mapping = {
        "D1": "higher_timeframe",
        "H4": "secondary_timeframe",
        "H1": "primary_timeframe",
        "M5": "entry_timeframe",
    }
    if timeframe == "M15":
        return ((payload.get("profile_timeframes") or {}).get("M15") or {})
    return payload.get(mapping.get(timeframe, ""), {}) or {}


def _trend(payload: dict, timeframe: str) -> str:
    section = _section(payload, timeframe)
    ms = section.get("market_structure", {}) if isinstance(section, dict) else {}
    raw = str(ms.get("trend") or ms.get("bias") or "").upper()
    if "BULL" in raw:
        return "bullish"
    if "BEAR" in raw:
        return "bearish"
    return "neutral"


def _add(adjustments: list[dict], factor: str, value: int, reason: str) -> int:
    adjustments.append({"factor": factor, "value": value, "reason": reason})
    return value


def _has_directional_choch(smc: dict, direction: str) -> bool:
    choch = smc.get("choch", {}) if isinstance(smc, dict) else {}
    target = "bullish_choch" if direction == "bullish" else "bearish_choch"
    for tf_data in choch.values() if isinstance(choch, dict) else []:
        if isinstance(tf_data, dict) and tf_data.get(target):
            return True
    return False


def _premium_discount(payload: dict, direction: str) -> tuple[int, str | None]:
    smc = payload.get("smc", {}) or {}
    price = (payload.get("current_price") or {}).get("mid")
    swings = smc.get("h1_swings") or smc.get("m5_swings") or {}
    highs = swings.get("highs") or []
    lows = swings.get("lows") or []
    if price is None or not highs or not lows:
        return 0, None
    high = float(highs[-1].get("price"))
    low = float(lows[-1].get("price"))
    if high <= low:
        return 0, None
    equilibrium = low + ((high - low) / 2)
    is_discount = float(price) <= equilibrium
    if direction == "bullish":
        return (10, "Buy setup occurs in discount/lower equilibrium") if is_discount else (-15, "Buy setup occurs in premium area")
    if direction == "bearish":
        return (10, "Sell setup occurs in premium/upper equilibrium") if not is_discount else (-15, "Sell setup occurs in discount area")
    return 0, None


def _quality(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def score_smc_setup(market_payload: dict, risk_profile: str | None = None) -> dict:
    payload = market_payload or {}
    profile = (risk_profile or (payload.get("risk_config") or {}).get("risk_profile") or settings.risk_profile).upper()
    model = _profile_model(profile)
    adjustments: list[dict] = []
    confluence: list[str] = []
    weaknesses: list[str] = []
    risk_notes: list[str] = []
    score = 50
    forced_no_trade = False

    if "M15" in model["execution_timeframes"] and not _section(payload, "M15"):
        model["timeframe_fallback"] = "M15 unavailable; using M5 with H1/H4 filter"
        weaknesses.append(model["timeframe_fallback"])
        score += _add(adjustments, "timeframe_fallback", -3, model["timeframe_fallback"])

    filter_trends = [_trend(payload, tf) for tf in model["filter_timeframes"]]
    execution_trends = [_trend(payload, tf) for tf in model["execution_timeframes"]]
    bullish_votes = filter_trends.count("bullish") + execution_trends.count("bullish")
    bearish_votes = filter_trends.count("bearish") + execution_trends.count("bearish")
    direction = "bullish" if bullish_votes > bearish_votes else "bearish" if bearish_votes > bullish_votes else "neutral"

    filter_conflict = "bullish" in filter_trends and "bearish" in filter_trends
    execution_conflict = "bullish" in execution_trends and "bearish" in execution_trends
    cross_conflict = direction != "neutral" and any(t not in {direction, "neutral"} for t in filter_trends + execution_trends)
    if filter_conflict or execution_conflict or cross_conflict:
        score += _add(adjustments, "structure_conflict", -25, "Profile filter and execution structures conflict")
        weaknesses.append("Profile filter and execution structures conflict")
    elif direction in {"bullish", "bearish"}:
        score += _add(adjustments, "swing_internal_alignment", 20, f"Profile filter and execution bias align {direction}")
        confluence.append(f"Profile filter and execution bias align {direction}")

    if profile == "HIGH":
        d1 = _trend(payload, "D1")
        if d1 not in {direction, "neutral"} and direction != "neutral":
            score += _add(adjustments, "d1_context_warning", -7, "D1 context conflicts with scalping direction")
            weaknesses.append("D1 context conflicts with scalping direction")

    smc = payload.get("smc", {}) or {}
    has_liquidity = bool(smc.get("liquidity_levels"))
    has_choch = _has_directional_choch(smc, direction)
    if has_choch and has_liquidity:
        score += _add(adjustments, "choch_after_liquidity", 15, "CHoCH appears with liquidity clue")
        confluence.append("CHoCH appears with liquidity clue")
    elif has_choch:
        score += _add(adjustments, "missing_liquidity_sweep", -10, "CHoCH has no liquidity confirmation")
        weaknesses.append("CHoCH has no liquidity confirmation")

    if has_liquidity:
        score += _add(adjustments, "liquidity_clue", 5, "EQH/EQL/liquidity level supports context")
        confluence.append("Liquidity clue supports context")

    fvg = smc.get("fvg_zones") or []
    if any(str(z.get("direction", "")).lower() == direction for z in fvg if isinstance(z, dict)):
        score += _add(adjustments, "aligned_fvg", 5, "Directional FVG supports setup")
        confluence.append("Directional FVG supports setup")

    obs = smc.get("order_blocks", {}) or {}
    aligned_obs = obs.get("demand") if direction == "bullish" else obs.get("supply") if direction == "bearish" else []
    if aligned_obs:
        score += _add(adjustments, "aligned_order_block", 10, "Aligned order block supports setup")
        confluence.append("Aligned order block supports setup")

    pd_value, pd_reason = _premium_discount(payload, direction)
    if pd_reason:
        score += _add(adjustments, "premium_discount", pd_value, pd_reason)
        (confluence if pd_value > 0 else weaknesses).append(pd_reason)
    else:
        weaknesses.append("Premium/discount unavailable from swing range")

    spread = int((payload.get("current_price") or {}).get("spread_points") or 0)
    if spread > settings.max_spread_points:
        score += _add(adjustments, "spread_high", -100, f"Spread {spread} exceeds max {settings.max_spread_points}")
        risk_notes.append(f"Spread {spread} exceeds max {settings.max_spread_points}")
        forced_no_trade = True

    ep = payload.get("entry_plan_context") or {}
    rr = ep.get("risk_reward_to_tp1")
    min_rr = max(float((payload.get("risk_config") or {}).get("min_risk_reward") or settings.effective_min_risk_reward), 1.5)
    if rr is not None and float(rr) < min_rr:
        score += _add(adjustments, "risk_reward_low", -100, f"R:R {rr} below minimum {min_rr}")
        risk_notes.append(f"R:R {rr} below minimum {min_rr}")
        forced_no_trade = True

    levels_available = ep.get("entry_available") and ep.get("sl_available") and ep.get("tp_available")
    entry_note = "levels available" if levels_available else "manual confirmation required"
    if not levels_available:
        risk_notes.append("manual confirmation required")

    final_score = max(0, min(100, int(round(score))))
    if forced_no_trade:
        semantic = "NO_TRADE"
    elif final_score < 40:
        semantic = "NO_TRADE"
    elif final_score < settings.min_signal_probability:
        semantic = "WAIT"
    elif direction == "bullish":
        semantic = "BUY_SETUP"
    elif direction == "bearish":
        semantic = "SELL_SETUP"
    else:
        semantic = "WAIT"

    return {
        "base_score": 50,
        "adjustments": adjustments,
        "final_score": final_score,
        "pre_ai_decision": semantic,
        "bias": direction,
        "setup_quality": _quality(final_score),
        "timeframe_model": model,
        "main_confluence": confluence,
        "weaknesses": weaknesses,
        "risk_notes": risk_notes,
        "entry_sl_tp_note": entry_note,
        "invalidation": "manual confirmation required",
        "forced_no_trade": forced_no_trade,
        "ai_review_used": False,
        "ai_unavailable": False,
    }
```

- [ ] **Step 4: Run scorer tests**

Run: `pytest tests/test_smc_probability.py -v`

Expected: PASS.

- [ ] **Step 5: Commit this task**

Run:

```bash
git add app/analysis/smc_probability.py tests/test_smc_probability.py
git commit -m "feat: add smc probability scorer"
```

---

### Task 3: Integrate Scoring Into Signal Generation

**Files:**
- Modify: `app/services/signal_service.py`
- Test: `tests/test_signal_service.py`

- [ ] **Step 1: Write failing signal integration test**

Add to `tests/test_signal_service.py`:

```python
from unittest.mock import MagicMock


def test_generate_signal_adds_smc_probability(monkeypatch):
    from app.services import signal_service

    monkeypatch.setattr("app.mt5_connector.connection.ensure_mt5_connected", lambda: True)
    monkeypatch.setattr("app.mt5_connector.market_data.select_symbol", lambda symbol: True)
    monkeypatch.setattr("app.mt5_connector.market_data.get_symbol_info", lambda symbol: {"point": 0.00001})
    monkeypatch.setattr("app.mt5_connector.market_data.get_latest_tick", lambda symbol: {"bid": 1.1, "ask": 1.1002})
    monkeypatch.setattr("app.mt5_connector.market_data.get_spread", lambda symbol: 10)
    monkeypatch.setattr("app.mt5_connector.market_data.get_market_depth", lambda symbol: None)
    monkeypatch.setattr("app.mt5_connector.market_data.get_candles", lambda *args, **kwargs: MagicMock(__len__=lambda self: 100))
    monkeypatch.setattr("app.mt5_connector.account.get_balance", lambda: 1000.0)
    monkeypatch.setattr("app.mt5_connector.account.get_equity", lambda: 1000.0)
    monkeypatch.setattr("app.mt5_connector.account.get_daily_drawdown_percent", lambda: 0.0)
    monkeypatch.setattr("app.mt5_connector.positions.get_open_positions_count", lambda symbol=None: 0)
    monkeypatch.setattr("app.mt5_connector.orders.get_pending_orders_count", lambda symbol=None: 0)
    monkeypatch.setattr("app.database.repositories.save_market_snapshot", lambda snapshot: {"id": "snap-1"})
    monkeypatch.setattr("app.analysis.noise_filter.evaluate_noise_filter", lambda *args: {"passed": True, "blocked_by": [], "hold_reason": ""})
    monkeypatch.setattr("app.ai_engine.deepseek_client.get_ai_decision", lambda payload: _hold_decision())
    monkeypatch.setattr("app.ai_engine.deepseek_client.validate_decision", lambda decision, market_payload=None: decision)
    monkeypatch.setattr("app.database.repositories.save_ai_decision", lambda row: {"id": "decision-1"})
    monkeypatch.setattr("app.database.repositories.save_risk_check", lambda **kwargs: {})
    monkeypatch.setattr("app.risk.risk_manager.evaluate_decision", lambda decision, context: {"approved": False, "symbol": context["symbol"], "reason": "test", "checks": {}})

    monkeypatch.setattr(
        "app.analysis.feature_builder.build_market_payload",
        lambda **kwargs: {
            "symbol": kwargs["symbol"],
            "current_price": {"bid": 1.1, "ask": 1.1002, "mid": 1.1001, "spread_points": 10},
            "risk_config": {"risk_profile": "MEDIUM", "min_risk_reward": 1.5},
            "higher_timeframe": {"timeframe": "D1", "market_structure": {"trend": "BULLISH"}},
            "secondary_timeframe": {"timeframe": "H4", "market_structure": {"trend": "BULLISH"}},
            "primary_timeframe": {"timeframe": "H1", "market_structure": {"trend": "BULLISH"}},
            "entry_timeframe": {"timeframe": "M5", "market_structure": {"trend": "BULLISH"}},
            "smc": {"liquidity_levels": [], "order_blocks": {}, "fvg_zones": [], "choch": {}},
            "major_trend": {"bias": "D1_BULLISH", "allowed_directions": ["BUY"]},
            "open_position_state": {},
            "account_context": {},
        },
    )

    result = signal_service.generate_signal("EURUSD.m")

    assert "smc_probability" in result["market_payload"]
    assert "pre_ai_decision" in result["market_payload"]["smc_probability"]


def _hold_decision():
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, EntryPlan, EntryType, ExecutionPermission, MarketRegime, TimeframeBias

    return AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.0,
        confidence_label=ConfidenceLabel.LOW,
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_plan=EntryPlan(entry_type=EntryType.NONE),
        execution_permission=ExecutionPermission(ai_allows_execution=False, reason="test"),
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_signal_service.py::test_generate_signal_adds_smc_probability -v`

Expected: FAIL because `smc_probability` is missing.

- [ ] **Step 3: Add scoring to `signal_service.py`**

In `generate_signal()`, immediately after this existing line:

```python
        market_payload.setdefault("risk_config", {})["point"] = symbol_info.get("point", 0.01)
```

add:

```python
        entry_plan_context = market_payload.setdefault("entry_plan_context", {})
        entry_plan_context.setdefault("risk_reward_to_tp1", None)
        entry_plan_context.setdefault("entry_available", False)
        entry_plan_context.setdefault("sl_available", False)
        entry_plan_context.setdefault("tp_available", False)

        from app.analysis.smc_probability import score_smc_setup

        smc_probability = score_smc_setup(market_payload, settings.risk_profile)
        market_payload["smc_probability"] = smc_probability
        logger.info(
            f"SMC deterministic score [{sym}]: "
            f"decision={smc_probability.get('pre_ai_decision')} "
            f"score={smc_probability.get('final_score')} "
            f"quality={smc_probability.get('setup_quality')}"
        )
```

When M15 candles are added later, store them as `market_payload["profile_timeframes"]["M15"]`. Do not rename existing timeframe keys.

- [ ] **Step 4: Honor `ENABLE_AI_REVIEW` without removing existing AI path**

Replace:

```python
        ai_decision = get_ai_decision(market_payload)
```

with:

```python
        if settings.enable_ai_review:
            ai_decision = get_ai_decision(market_payload)
        else:
            from app.analysis.smc_probability import build_rule_based_hold_decision
            ai_decision = build_rule_based_hold_decision(market_payload["smc_probability"], market_payload)
```

Add `build_rule_based_hold_decision()` in `app/analysis/smc_probability.py`:

```python
def build_rule_based_hold_decision(score: dict, market_payload: dict):
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, EntryPlan, EntryType, ExecutionPermission, MarketRegime, RiskNotes, TimeframeBias

    return AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=max(0.0, min(1.0, float(score.get("final_score", 0)) / 100.0)),
        confidence_label=ConfidenceLabel.HIGH if score.get("final_score", 0) >= 75 else ConfidenceLabel.MEDIUM if score.get("final_score", 0) >= 50 else ConfidenceLabel.LOW,
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
        main_reason="Rule-based SMC probability score used without AI review",
        entry_plan=EntryPlan(entry_type=EntryType.NONE),
        execution_permission=ExecutionPermission(ai_allows_execution=False, reason="Manual confirmation required"),
        risk_notes=RiskNotes(main_risk="; ".join(score.get("risk_notes", [])), invalidation_condition=score.get("invalidation", "manual confirmation required")),
        final_comment="AI analysis unavailable, rule-based score used" if score.get("ai_unavailable") else "Rule-based score used",
        strategy_mode=settings.strategy_mode,
        trading_style=settings.effective_style,
    )
```

- [ ] **Step 5: Run signal integration test**

Run: `pytest tests/test_signal_service.py::test_generate_signal_adds_smc_probability -v`

Expected: PASS.

- [ ] **Step 6: Commit this task**

Run:

```bash
git add app/services/signal_service.py app/analysis/smc_probability.py tests/test_signal_service.py
git commit -m "feat: attach smc probability to signals"
```

---

### Task 4: Add Risk Manager Probability Gate

**Files:**
- Modify: `app/risk/risk_manager.py`
- Modify: `app/services/signal_service.py`
- Test: `tests/test_risk_manager.py`

- [ ] **Step 1: Write failing risk tests**

Add to `tests/test_risk_manager.py`:

```python
def test_risk_manager_blocks_no_trade_probability():
    from app.risk.risk_manager import evaluate_decision

    decision = _buy_decision()
    result = evaluate_decision(decision, {"symbol": "EURUSD.m", "smc_probability": {"pre_ai_decision": "NO_TRADE", "final_score": 20}})

    assert result["approved"] is False
    assert "NO_TRADE" in result["reason"]


def test_risk_manager_blocks_below_min_signal_probability(monkeypatch):
    from app.config import settings
    from app.risk.risk_manager import evaluate_decision

    monkeypatch.setattr(settings, "min_signal_probability", 70)

    decision = _buy_decision()
    result = evaluate_decision(decision, {"symbol": "EURUSD.m", "smc_probability": {"pre_ai_decision": "BUY_SETUP", "final_score": 60}})

    assert result["approved"] is False
    assert "below minimum signal probability" in result["reason"]


def _buy_decision():
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, EntryPlan, EntryType, ExecutionPermission, MarketRegime, TimeframeBias

    return AIDecisionResponse(
        decision=Decision.BUY,
        confidence=0.9,
        confidence_label=ConfidenceLabel.HIGH,
        market_regime=MarketRegime.TRENDING_UP,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BULLISH,
        entry_plan=EntryPlan(entry_type=EntryType.LIMIT, preferred_entry_price=1.1, stop_loss=1.095, take_profit_1=1.11, risk_reward_to_tp1=2.0),
        execution_permission=ExecutionPermission(ai_allows_execution=True, reason="test"),
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_risk_manager.py -k "probability" -v`

Expected: FAIL because risk manager ignores `smc_probability`.

- [ ] **Step 3: Pass score into market context**

In `app/services/signal_service.py`, add to `market_context`:

```python
            "smc_probability": market_payload.get("smc_probability", {}),
```

- [ ] **Step 4: Add risk manager gate**

In `app/risk/risk_manager.py`, add check after HOLD check and before confidence check:

```python
        smc_probability = market_context.get("smc_probability") or {}
        semantic_decision = str(smc_probability.get("pre_ai_decision") or "").upper()
        final_score = smc_probability.get("final_score")
        checks["smc_probability_ok"] = True

        if semantic_decision == "NO_TRADE":
            checks["smc_probability_ok"] = False
            return _add_symbol(_reject(checks, "SMC probability decision NO_TRADE"), symbol_name)

        if final_score is not None and float(final_score) < settings.min_signal_probability:
            checks["smc_probability_ok"] = False
            return _add_symbol(_reject(
                checks,
                f"SMC probability {float(final_score):.0f} below minimum signal probability {settings.min_signal_probability}",
            ), symbol_name)
```

- [ ] **Step 5: Run risk tests**

Run: `pytest tests/test_risk_manager.py -k "probability" -v`

Expected: PASS.

- [ ] **Step 6: Commit this task**

Run:

```bash
git add app/risk/risk_manager.py app/services/signal_service.py tests/test_risk_manager.py
git commit -m "feat: gate trades by smc probability"
```

---

### Task 5: Tighten DeepSeek SMC Prompt and Include Score Context

**Files:**
- Modify: `app/ai_engine/prompt_builder.py`
- Test: `tests/test_prompt_builder.py`

- [ ] **Step 1: Write failing prompt tests**

Add to `tests/test_prompt_builder.py`:

```python
def test_smc_prompt_removes_aggressive_spread_ignore_rules(monkeypatch):
    from app.config import settings
    from app.ai_engine.prompt_builder import build_system_prompt

    monkeypatch.setattr(settings, "strategy_mode", "SMC_AI")
    prompt = build_system_prompt("EURUSD.m")

    assert "SMC trading probability analyst" in prompt
    assert "Do not invent price levels" in prompt
    assert "Ignore spread completely" not in prompt
    assert "Missing a trade is worse" not in prompt
    assert "Be AGGRESSIVE" not in prompt


def test_user_prompt_includes_smc_probability():
    from app.ai_engine.prompt_builder import build_user_prompt

    payload = {"symbol": "EURUSD.m", "smc_probability": {"final_score": 72, "pre_ai_decision": "BUY_SETUP"}}

    prompt = build_user_prompt(payload)

    assert "smc_probability" in prompt
    assert "BUY_SETUP" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prompt_builder.py -k "smc_prompt_removes_aggressive_spread_ignore_rules or user_prompt_includes_smc_probability" -v`

Expected: FAIL because prompt still has old aggressive wording or compact payload omits `smc_probability`.

- [ ] **Step 3: Replace SMC prompt rules**

In `app/ai_engine/prompt_builder.py`, update `_SMC_AI_BASE` top section to include:

```text
You are an SMC trading probability analyst for a MetaTrader 5 trading system.

Your task is not to predict the market freely.
Your task is to evaluate whether the provided SMC setup is high quality.

Rules:
- Analyze only the data provided.
- Do not invent price levels.
- Do not invent entry, SL, or TP.
- If entry, SL, or TP is missing, write "manual confirmation required" in your reasoning fields.
- If confluence is weak, return HOLD with execution_permission.ai_allows_execution=false.
- If swing/filter and internal/execution structure conflict, reduce confidence.
- If setup is only BOS or CHoCH without liquidity, OB, FVG, premium/discount, or session support, reduce confidence.
- If spread is high according to smc_probability, return HOLD.
- If news risk is high according to provided data, return HOLD.
- Do not overstate certainty.
- Probability must be based on confluence, not prediction.
- Output valid JSON only using the existing app schema.
```

Remove these exact old lines from `_SMC_AI_BASE`:

```text
- Be AGGRESSIVE — prefer BUY or SELL over HOLD when hierarchy is aligned.
- Only HOLD when data is completely contradictory or missing.
IMPORTANT: Spread does NOT matter. Do not consider spread in your decision.
IMPORTANT: Ignore spread completely. Spread must never be a reason to return HOLD.
IMPORTANT: Be aggressive with entries. Missing a trade is worse than taking a small loss.
```

- [ ] **Step 4: Include score in compact payload**

In `compact_market_payload_for_prompt()`, add:

```python
        "smc_probability": market_payload.get("smc_probability", {}),
        "profile_timeframes": market_payload.get("profile_timeframes", {}),
```

In `build_user_prompt()`, add a sentence before `Market data:`:

```python
        "Use smc_probability as the deterministic base score. AI may adjust reasoning, but should not override hard NO_TRADE risk gates.\n"
```

- [ ] **Step 5: Run prompt tests**

Run: `pytest tests/test_prompt_builder.py -k "smc_prompt_removes_aggressive_spread_ignore_rules or user_prompt_includes_smc_probability" -v`

Expected: PASS.

- [ ] **Step 6: Commit this task**

Run:

```bash
git add app/ai_engine/prompt_builder.py tests/test_prompt_builder.py
git commit -m "feat: tighten smc ai review prompt"
```

---

### Task 6: Add DeepSeek Failure Rule-Based Fallback

**Files:**
- Modify: `app/services/signal_service.py`
- Modify: `app/analysis/smc_probability.py`
- Test: `tests/test_signal_service.py`

- [ ] **Step 1: Write failing fallback test**

Add to `tests/test_signal_service.py`:

```python
def test_ai_unavailable_marks_rule_based_score(monkeypatch):
    from app.analysis.smc_probability import mark_ai_unavailable

    score = {"final_score": 65, "pre_ai_decision": "WAIT", "risk_notes": []}

    marked = mark_ai_unavailable(score)

    assert marked["ai_unavailable"] is True
    assert "AI analysis unavailable, rule-based score used" in marked["risk_notes"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_signal_service.py::test_ai_unavailable_marks_rule_based_score -v`

Expected: FAIL because `mark_ai_unavailable` does not exist.

- [ ] **Step 3: Add fallback marker helper**

Add to `app/analysis/smc_probability.py`:

```python
def mark_ai_unavailable(score: dict) -> dict:
    updated = dict(score or {})
    notes = list(updated.get("risk_notes") or [])
    message = "AI analysis unavailable, rule-based score used"
    if message not in notes:
        notes.append(message)
    updated["risk_notes"] = notes
    updated["ai_unavailable"] = True
    updated["ai_review_used"] = False
    return updated
```

- [ ] **Step 4: Detect AI engine default HOLD fallback in signal service**

After `ai_decision = get_ai_decision(market_payload)`, add:

```python
            if getattr(ai_decision, "final_comment", "") == "Decision engine error — defaulting to HOLD":
                from app.analysis.smc_probability import build_rule_based_hold_decision, mark_ai_unavailable
                market_payload["smc_probability"] = mark_ai_unavailable(market_payload.get("smc_probability", {}))
                ai_decision = build_rule_based_hold_decision(market_payload["smc_probability"], market_payload)
```

- [ ] **Step 5: Run fallback test**

Run: `pytest tests/test_signal_service.py::test_ai_unavailable_marks_rule_based_score -v`

Expected: PASS.

- [ ] **Step 6: Commit this task**

Run:

```bash
git add app/services/signal_service.py app/analysis/smc_probability.py tests/test_signal_service.py
git commit -m "feat: add smc rule fallback"
```

---

### Task 7: Render Professional SMC Telegram Output and Suppression

**Files:**
- Modify: `app/telegram_bot/message_templates.py`
- Modify: `app/telegram_bot/bot.py`
- Test: `tests/test_telegram_bot.py`

- [ ] **Step 1: Write failing Telegram format test**

Add to `tests/test_telegram_bot.py`:

```python
def test_signal_message_renders_smc_probability_block():
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, EntryPlan, EntryType, ExecutionPermission, MarketRegime, TimeframeBias
    from app.telegram_bot.message_templates import format_signal_message

    decision = AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.72,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.TRENDING_UP,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BULLISH,
        entry_plan=EntryPlan(entry_type=EntryType.NONE),
        execution_permission=ExecutionPermission(ai_allows_execution=False, reason="manual"),
    )
    payload = {
        "current_price": {"bid": 1.1, "ask": 1.1002, "spread_points": 10},
        "smc_probability": {
            "final_score": 72,
            "setup_quality": "medium",
            "pre_ai_decision": "WAIT",
            "bias": "bullish",
            "timeframe_model": {"filter_timeframes": ["D1", "H4"], "execution_timeframes": ["H1"], "timeframe_fallback": None},
            "main_confluence": ["Profile filter and execution bias align bullish"],
            "weaknesses": ["CHoCH has no liquidity confirmation"],
            "risk_notes": ["manual confirmation required"],
            "entry_sl_tp_note": "manual confirmation required",
            "invalidation": "manual confirmation required",
        },
    }

    message = format_signal_message(decision, {"approved": False, "symbol": "EURUSD.m"}, "EURUSD.m", payload)

    assert "EURUSD.m — SMC ANALYSIS" in message
    assert "Probability" in message
    assert "Score: 72%" in message
    assert "Decision" in message
    assert "WAIT" in message
    assert "Manual confirmation required" in message
```

- [ ] **Step 2: Write failing Telegram suppression test**

Add to `tests/test_telegram_bot.py`:

```python
@pytest.mark.asyncio
async def test_send_trade_signal_suppresses_no_trade_alert(monkeypatch):
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, MarketRegime, TimeframeBias
    from app.config import settings
    from app.telegram_bot import bot as bot_module

    decision = AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.2,
        confidence_label=ConfidenceLabel.LOW,
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
    )
    original_token = settings.telegram_bot_token
    original_chat_id = settings.telegram_allowed_chat_id
    original_send_no_trade = settings.send_no_trade_alert
    original_application = bot_module._application
    try:
        settings.telegram_bot_token = "token"
        settings.telegram_allowed_chat_id = "123"
        settings.send_no_trade_alert = False
        bot_module._application = MagicMock(bot=object())
        monkeypatch.setattr("app.telegram_bot.bot.send_message", AsyncMock(return_value=True))

        sent = await bot_module.send_trade_signal(
            decision,
            {"symbol": "EURUSD.m", "approved": False},
            "decision-1",
            {"smc_probability": {"pre_ai_decision": "NO_TRADE", "final_score": 20}},
        )

        assert sent is False
    finally:
        settings.telegram_bot_token = original_token
        settings.telegram_allowed_chat_id = original_chat_id
        settings.send_no_trade_alert = original_send_no_trade
        bot_module._application = original_application
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_telegram_bot.py -k "smc_probability_block or suppresses_no_trade_alert" -v`

Expected: FAIL because formatter and suppression logic do not exist.

- [ ] **Step 4: Add SMC block formatter**

In `app/telegram_bot/message_templates.py`, add helper before `format_market_trend_alert()`:

```python
def _format_smc_probability_block(symbol: str, payload: dict, risk_result: dict) -> list[str]:
    score = (payload or {}).get("smc_probability") or {}
    if not score:
        return []
    model = score.get("timeframe_model") or {}
    confluence = score.get("main_confluence") or []
    weaknesses = score.get("weaknesses") or []
    risk_notes = score.get("risk_notes") or []
    quality = str(score.get("setup_quality") or "low").title()
    decision = score.get("pre_ai_decision") or "WAIT"
    entry_note = score.get("entry_sl_tp_note") or "manual confirmation required"
    invalidation = score.get("invalidation") or "manual confirmation required"
    price = (payload or {}).get("current_price") or {}
    filter_tfs = "/".join(model.get("filter_timeframes") or []) or "N/A"
    execution_tfs = "/".join(model.get("execution_timeframes") or []) or "N/A"

    lines = [
        f"{_decision_emoji('BUY' if decision == 'BUY_SETUP' else 'SELL' if decision == 'SELL_SETUP' else 'HOLD')} <b>{_escape_html(symbol)} — SMC ANALYSIS</b>",
        "",
        "<b>Bias:</b>",
        f"HTF/Swing: {_escape_html(filter_tfs)}",
        f"Internal: {_escape_html(execution_tfs)}",
        f"Direction: {_escape_html(str(score.get('bias') or 'neutral'))}",
        "",
        "<b>SMC Event:</b>",
        f"Event: {_escape_html(decision)}",
        f"Timeframe: {_escape_html(execution_tfs)}",
        f"Premium/Discount: {_escape_html(_first_matching_reason(score, 'premium_discount') or 'manual confirmation required')}",
        "",
        "<b>Confluence:</b>",
    ]
    lines.extend([f"✅ {_escape_html(item)}" for item in confluence[:4]])
    lines.extend([f"⚠️ {_escape_html(item)}" for item in weaknesses[:4]])
    lines.extend([
        "",
        "<b>Probability:</b>",
        f"Score: {int(score.get('final_score') or 0)}%",
        f"Quality: {_escape_html(quality)}",
        "",
        "<b>Decision:</b>",
        _escape_html(decision),
        "",
        "<b>Risk:</b>",
        f"Spread: {_fmt_num(price.get('spread_points'))} pts",
        f"News: {_escape_html(str((payload or {}).get('news_risk', 'unknown')))}",
        f"RR: {_escape_html(str(((payload or {}).get('entry_plan_context') or {}).get('risk_reward_to_tp1', 'manual confirmation required')))}",
        "",
        "<b>Entry/SL/TP:</b>",
        _escape_html(entry_note).capitalize(),
        "",
        "<b>Invalidation:</b>",
        _escape_html(invalidation),
    ])
    if risk_notes:
        lines.append("")
        lines.append("<b>Notes:</b> " + _escape_html("; ".join(str(n) for n in risk_notes[:3])))
    return lines


def _first_matching_reason(score: dict, factor: str) -> str | None:
    for adjustment in score.get("adjustments") or []:
        if adjustment.get("factor") == factor:
            return adjustment.get("reason")
    return None
```

At the start of `format_market_trend_alert()` after payload/risk setup, add:

```python
    smc_probability_lines = _format_smc_probability_block(symbol, payload, risk_result)
    if smc_probability_lines:
        return "\n".join(smc_probability_lines)
```

- [ ] **Step 5: Add Telegram suppression**

In `app/telegram_bot/bot.py`, immediately after this existing line:

```python
        symbol = risk_result.get("symbol", settings.default_symbol)
```

add:

```python
        smc_probability = (market_payload or {}).get("smc_probability") or {}
        semantic_decision = str(smc_probability.get("pre_ai_decision") or "").upper()
        final_score = smc_probability.get("final_score")
        if semantic_decision == "NO_TRADE" and not settings.send_no_trade_alert:
            logger.info(f"Telegram signal suppressed for {symbol}: NO_TRADE and SEND_NO_TRADE_ALERT=false")
            return False
        if final_score is not None and float(final_score) < settings.min_signal_probability and semantic_decision != "NO_TRADE":
            logger.info(
                f"Telegram signal suppressed for {symbol}: probability {float(final_score):.0f} "
                f"below {settings.min_signal_probability}"
            )
            return False
```

- [ ] **Step 6: Run Telegram tests**

Run: `pytest tests/test_telegram_bot.py -k "smc_probability_block or suppresses_no_trade_alert" -v`

Expected: PASS.

- [ ] **Step 7: Commit this task**

Run:

```bash
git add app/telegram_bot/message_templates.py app/telegram_bot/bot.py tests/test_telegram_bot.py
git commit -m "feat: render smc probability alerts"
```

---

### Task 8: Add Optional M15 Context Without Renaming Existing Payload Keys

**Files:**
- Modify: `app/analysis/feature_builder.py`
- Modify: `app/services/signal_service.py`
- Test: `tests/test_feature_builder.py`

- [ ] **Step 1: Write failing feature builder test**

Add to `tests/test_feature_builder.py`:

```python
def test_build_market_payload_accepts_optional_profile_timeframes():
    from app.analysis.feature_builder import build_market_payload

    payload = build_market_payload(
        symbol="EURUSD.m",
        df_d1=None,
        df_h4=None,
        df_h1=None,
        df_m15=None,
        bid=1.1,
        ask=1.1002,
        spread_points=10,
        profile_timeframes={"M15": None},
    )

    assert "profile_timeframes" in payload
    assert "M15" in payload["profile_timeframes"]
    assert payload["higher_timeframe"]["timeframe"] == "D1"
    assert payload["entry_timeframe"]["timeframe"] == "M5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_feature_builder.py::test_build_market_payload_accepts_optional_profile_timeframes -v`

Expected: FAIL because `build_market_payload()` does not accept `profile_timeframes`.

- [ ] **Step 3: Add optional profile timeframe support**

In `app/analysis/feature_builder.py`, update signature:

```python
    profile_timeframes: Optional[dict[str, Optional[pd.DataFrame]]] = None,
```

Before `payload = {`, add:

```python
    profile_tf_sections: dict[str, Any] = {}
    if profile_timeframes:
        for tf_name, tf_df in profile_timeframes.items():
            profile_tf_sections[tf_name] = _build_timeframe_section(tf_df, tf_name, include_orderflow=(tf_name == "M15"))
```

In payload dict, add:

```python
        "profile_timeframes": profile_tf_sections,
```

- [ ] **Step 4: Fetch M15 only as optional context**

In `app/services/signal_service.py`, after existing M5 candles fetch, add:

```python
        df_m15_profile = None
        try:
            df_m15_profile = get_candles(sym, timeframe="M15", count=100)
        except Exception as e:
            logger.debug(f"Optional M15 profile candles unavailable for {sym}: {e}")
```

In `build_market_payload()` call, add:

```python
            profile_timeframes={"M15": df_m15_profile},
```

- [ ] **Step 5: Run feature builder test**

Run: `pytest tests/test_feature_builder.py::test_build_market_payload_accepts_optional_profile_timeframes -v`

Expected: PASS.

- [ ] **Step 6: Commit this task**

Run:

```bash
git add app/analysis/feature_builder.py app/services/signal_service.py tests/test_feature_builder.py
git commit -m "feat: add optional m15 profile context"
```

---

### Task 9: Final Verification

**Files:**
- No new code unless failures expose bugs.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
pytest tests/test_smc_probability.py tests/test_config.py tests/test_prompt_builder.py tests/test_risk_manager.py tests/test_telegram_bot.py -k "smc or probability or signal_probability or no_trade or prompt" -v
```

Expected: all selected tests PASS. If pre-existing unrelated tests are selected and fail, narrow with exact test names and document the known unrelated failure.

- [ ] **Step 2: Run signal path tests**

Run:

```bash
pytest tests/test_signal_service.py tests/test_feature_builder.py -v
```

Expected: PASS. If old fixture assumptions fail because of existing project drift, fix only issues caused by this feature.

- [ ] **Step 3: Manual prompt sanity check**

Run:

```bash
python -c "from app.ai_engine.prompt_builder import build_system_prompt; p=build_system_prompt('EURUSD.m'); print('Ignore spread completely' in p, 'SMC trading probability analyst' in p)"
```

Expected output contains `False True`.

- [ ] **Step 4: Manual config sanity check**

Run:

```bash
python -c "from app.config import settings; print(settings.min_signal_probability, settings.send_no_trade_alert, settings.enable_ai_review)"
```

Expected output starts with `70 False True` unless local `.env` overrides it.

- [ ] **Step 5: Restart app if implementation runs in this workspace**

Run:

```bash
$proc = Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%run.py%'" | Where-Object { $_.CommandLine -like '*python*' } | Select-Object -First 1
if ($proc) { Stop-Process -Id $proc.ProcessId }
Start-Process -FilePath "C:\Python313\python.exe" -ArgumentList "run.py" -WorkingDirectory "C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade" -PassThru
```

Expected: new process starts.

- [ ] **Step 6: Verify runtime status**

Run:

```bash
Invoke-RestMethod -Uri "http://127.0.0.1:8000/status" -Method Get | ConvertTo-Json -Depth 6
```

Expected: JSON includes `loop_running`, `mode`, and `is_paused`.

- [ ] **Step 7: Final commit**

Run:

```bash
git status --short
git diff --check
git add app tests .env.example README.md docs/superpowers/specs/2026-06-26-smc-probability-quality-filter-design.md docs/superpowers/plans/2026-06-26-smc-probability-quality-filter.md
git commit -m "feat: add smc probability quality filter"
```

Expected: commit succeeds only when user explicitly requested commits during execution. If user did not request commits, skip commit and report changed files.

---

## Self-Review Notes

- Spec coverage: deterministic scoring, confluence filter, risk filter, prompt tightening, Telegram format, fallback, logging, optional env, and profile timeframe rules are covered by tasks 1-8.
- Compatibility: core enum remains `BUY`/`SELL`/`HOLD`; semantic decisions stay in `smc_probability` metadata.
- Existing payload keys remain stable; M15 is optional under `profile_timeframes`.
- Testing: plan uses TDD per task and includes focused verification commands.
