# Max Positions Per Symbol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable active-position cap per trading pair, defaulting to 5 positions per symbol.

**Architecture:** Add `MAX_POSITIONS_PER_SYMBOL` to settings, pass symbol-specific active-position count from signal generation into risk context, and reject trades in `risk_manager.evaluate_decision()` when the symbol count is at or above the cap. Existing global `MAX_OPEN_POSITIONS` and opposite-direction checks remain intact.

**Tech Stack:** Python, Pydantic Settings, pytest, MetaTrader5 connector helpers.

---

## File Structure

- Modify `app/config.py`: add `max_positions_per_symbol: int = 5` setting mapped from `MAX_POSITIONS_PER_SYMBOL`.
- Modify `app/analysis/feature_builder.py`: expose `max_positions_per_symbol` in `risk_config` payload.
- Modify `app/services/signal_service.py`: call `get_open_positions_count(sym)` and include `open_positions_count_symbol` in account/risk context.
- Modify `app/risk/risk_manager.py`: add per-symbol cap check and rejection reason.
- Modify `tests/test_risk_manager.py`: add tests for per-symbol cap behavior.
- Modify `tests/test_signal_service.py`: assert symbol-specific count is passed into risk context.

## Task 1: Add Config Setting

**Files:**
- Modify: `app/config.py:30-33`
- Modify: `app/analysis/feature_builder.py:158-165`
- Test: `tests/test_feature_builder.py:190-205`

- [ ] **Step 1: Write failing config test**

Add this assertion to existing config keys test in `tests/test_feature_builder.py` near existing `max_open_positions` assertion:

```python
assert "max_positions_per_symbol" in cfg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_feature_builder.py -q`

Expected: FAIL because `max_positions_per_symbol` is not yet present in config output.

- [ ] **Step 3: Add setting and payload key**

Update `app/config.py` so risk settings include the new field:

```python
    risk_per_trade_percent: float = 0.5
    max_daily_drawdown_percent: float = 2.0
    max_open_positions: int = 1
    max_positions_per_symbol: int = 5
    min_confidence: float = 0.65
```

Update `app/analysis/feature_builder.py` so `risk_config` exposes the new setting:

```python
    risk_config = {
        "risk_profile": settings.risk_profile,
        "risk_per_trade_percent": settings.risk_per_trade_percent,
        "min_risk_reward": settings.effective_min_risk_reward,
        "max_open_positions": settings.max_open_positions,
        "max_positions_per_symbol": settings.max_positions_per_symbol,
        "max_daily_drawdown_percent": settings.max_daily_drawdown_percent,
        "min_confidence": settings.effective_min_confidence,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_feature_builder.py -q`

Expected: PASS.

- [ ] **Step 5: Commit policy**

Do not commit unless user explicitly asks. Check status only:

```bash
git status --short
```

## Task 2: Pass Symbol Position Count To Risk Context

**Files:**
- Modify: `app/services/signal_service.py:74-93`
- Modify: `app/services/signal_service.py:277-288`
- Test: `tests/test_signal_service.py:4-87`

- [ ] **Step 1: Write failing signal-service test assertion**

Update `fake_open_positions_count()` in `tests/test_signal_service.py`:

```python
    def fake_open_positions_count(symbol=None):
        return 1 if symbol is None else 4
```

Add this assertion after `assert captured_context["open_positions_count"] == 1`:

```python
    assert captured_context["open_positions_count_symbol"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_signal_service.py::test_generate_signal_uses_global_open_positions_for_max_entry -q`

Expected: FAIL with `KeyError: 'open_positions_count_symbol'`.

- [ ] **Step 3: Add symbol-specific count in service**

Update `app/services/signal_service.py` after global position count:

```python
        open_positions_count = get_open_positions_count(None)
        open_positions_count_symbol = get_open_positions_count(sym)
        has_open = has_open_position(sym)
```

Update `account_context`:

```python
        account_context = {
            "balance": balance,
            "equity": equity,
            "daily_pnl_percent": None,
            "daily_drawdown_percent": daily_drawdown,
            "open_positions_count": open_positions_count,
            "open_positions_count_symbol": open_positions_count_symbol,
            "has_open_position": has_open,
        }
```

Update risk `market_context`:

```python
        market_context = {
            "symbol": sym,
            "current_bid": bid,
            "current_ask": ask,
            "spread_points": spread_points,
            "open_positions_count": open_positions_count,
            "open_positions_count_symbol": open_positions_count_symbol,
            "daily_drawdown_percent": daily_drawdown or 0.0,
            "mode": settings.bot_mode,
            "point": symbol_info.get("point", 0.01) if symbol_info else 0.01,
            "major_trend": market_payload.get("major_trend", {}),
            "open_position_state": market_payload.get("open_position_state", {}),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_signal_service.py::test_generate_signal_uses_global_open_positions_for_max_entry -q`

Expected: PASS.

- [ ] **Step 5: Commit policy**

Do not commit unless user explicitly asks. Check status only:

```bash
git status --short
```

## Task 3: Enforce Per-Symbol Cap In Risk Manager

**Files:**
- Modify: `app/risk/risk_manager.py:19-33`
- Modify: `app/risk/risk_manager.py:74-82`
- Test: `tests/test_risk_manager.py:246-266`

- [ ] **Step 1: Write failing risk-manager tests**

Add these tests after `test_max_positions_reached_rejected` in `tests/test_risk_manager.py`:

```python
    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_max_positions_per_symbol_reached_rejected(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 30
        mock_settings.max_positions_per_symbol = 5
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock()
        context = _make_context(positions=10)
        context["open_positions_count_symbol"] = 5

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["positions_per_symbol_ok"] is False
        assert "XAUUSD positions (5) at or above per-symbol max (5)" in result["reason"]

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_symbol_cap_allows_when_global_count_is_higher_but_symbol_below_cap(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 30
        mock_settings.max_positions_per_symbol = 5
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock()
        context = _make_context(positions=10)
        context["open_positions_count_symbol"] = 4

        result = evaluate_decision(decision, context)

        assert result["approved"] is True
        assert result["checks"]["positions_per_symbol_ok"] is True
```

- [ ] **Step 2: Run tests to verify first one fails**

Run: `pytest tests/test_risk_manager.py::TestEvaluateDecision::test_max_positions_per_symbol_reached_rejected tests/test_risk_manager.py::TestEvaluateDecision::test_symbol_cap_allows_when_global_count_is_higher_but_symbol_below_cap -q`

Expected: FAIL because `positions_per_symbol_ok` does not exist and risk manager does not reject by symbol cap yet.

- [ ] **Step 3: Add check default**

Update `checks` dict in `app/risk/risk_manager.py`:

```python
        checks = {
            "is_hold": False,
            "confidence_ok": True,
            "risk_reward_ok": True,
            "sl_range_ok": True,
            "positions_ok": True,
            "positions_per_symbol_ok": True,
            "position_direction_ok": True,
            "major_trend_ok": True,
            "drawdown_ok": True,
            "sl_provided": True,
            "tp_provided": True,
            "trade_params_valid": True,
            "ai_allows": True,
            "live_mode_allowed": True,
        }
```

- [ ] **Step 4: Add risk gate implementation**

Add this block immediately after existing global max-open-positions block:

```python
        open_positions_count_symbol = market_context.get("open_positions_count_symbol", 0)
        if open_positions_count_symbol >= settings.max_positions_per_symbol:
            checks["positions_per_symbol_ok"] = False
            return _reject(
                checks,
                f"{market_context.get('symbol', 'UNKNOWN')} positions ({open_positions_count_symbol}) "
                f"at or above per-symbol max ({settings.max_positions_per_symbol})",
            )
```

- [ ] **Step 5: Run risk-manager tests**

Run: `pytest tests/test_risk_manager.py -q`

Expected: PASS.

- [ ] **Step 6: Commit policy**

Do not commit unless user explicitly asks. Check status only:

```bash
git status --short
```

## Task 4: Full Verification

**Files:**
- Verify: all changed files

- [ ] **Step 1: Run focused tests**

Run: `pytest tests/test_signal_service.py tests/test_risk_manager.py tests/test_feature_builder.py -q`

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run: `pytest -q`

Expected: PASS with existing warning count only.

- [ ] **Step 3: Inspect final diff**

Run: `git diff -- app/config.py app/analysis/feature_builder.py app/services/signal_service.py app/risk/risk_manager.py tests/test_risk_manager.py tests/test_signal_service.py tests/test_feature_builder.py docs/superpowers/specs/2026-06-22-max-positions-per-symbol-design.md docs/superpowers/plans/2026-06-22-max-positions-per-symbol.md`

Expected: diff only contains per-symbol active-position cap, tests, and docs.

- [ ] **Step 4: Commit policy**

Do not commit unless user explicitly asks. If user requests commit, run these checks first:

```bash
git status --short
git diff -- app/config.py app/analysis/feature_builder.py app/services/signal_service.py app/risk/risk_manager.py tests/test_risk_manager.py tests/test_signal_service.py tests/test_feature_builder.py docs/superpowers/specs/2026-06-22-max-positions-per-symbol-design.md docs/superpowers/plans/2026-06-22-max-positions-per-symbol.md
git log --oneline -10
```
