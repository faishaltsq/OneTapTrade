import pytest
from unittest.mock import patch, MagicMock


def _make_decision_mock(
    decision="BUY",
    confidence=0.8,
    stop_loss=2005.00,
    take_profit_1=2020.00,
    take_profit_2=2030.00,
    risk_reward_to_tp1=2.0,
    ai_allows_execution=True,
    entry_price=2010.00,
) -> MagicMock:
    entry_plan = MagicMock()
    entry_plan.stop_loss = stop_loss
    entry_plan.take_profit_1 = take_profit_1
    entry_plan.take_profit_2 = take_profit_2
    entry_plan.risk_reward_to_tp1 = risk_reward_to_tp1
    entry_plan.preferred_entry_price = entry_price

    exec_perm = MagicMock()
    exec_perm.ai_allows_execution = ai_allows_execution

    mock = MagicMock()
    mock.decision = decision
    mock.confidence = confidence
    mock.entry_plan = entry_plan
    mock.execution_permission = exec_perm
    return mock


def _make_context(
    symbol="XAUUSD",
    bid=2010.0,
    ask=2010.5,
    positions=0,
    drawdown=0.5,
    mode="SEMI_AUTO",
    point=0.01,
) -> dict:
    return {
        "symbol": symbol,
        "current_bid": bid,
        "current_ask": ask,
        "spread_points": 10,
        "open_positions_count": positions,
        "daily_drawdown_percent": drawdown,
        "mode": mode,
        "point": point,
    }


@patch("app.risk.risk_manager.settings")
@patch("app.risk.trade_validator.validate_trade_params")
def test_wide_ai_stop_loss_is_allowed_when_other_checks_pass(mock_validate, mock_settings):
    from app.ai_engine.schemas import (
        AIDecisionResponse,
        ConfidenceLabel,
        Decision,
        EntryPlan,
        EntryType,
        ExecutionPermission,
        MarketRegime,
        TimeframeBias,
    )
    from app.risk.risk_manager import evaluate_decision

    mock_settings.effective_min_confidence = 0.55
    mock_settings.effective_min_risk_reward = 1.5
    mock_settings.effective_min_sl_pips = 30
    mock_settings.effective_max_sl_pips = 100
    mock_settings.max_open_positions = 1
    mock_settings.max_daily_drawdown_percent = 2.0
    mock_settings.live_trading_enabled = False
    mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}
    decision = AIDecisionResponse(
        decision=Decision.SELL,
        confidence=0.65,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_plan=EntryPlan(
            entry_type=EntryType.MARKET,
            preferred_entry_price=4168.262,
            stop_loss=4177.082,
            take_profit_1=4154.0,
            risk_reward_to_tp1=1.5,
        ),
        execution_permission=ExecutionPermission(ai_allows_execution=True),
    )
    context = {
        "symbol": "XAUUSDm",
        "current_bid": 4168.262,
        "current_ask": 4168.5,
        "open_positions_count": 0,
        "daily_drawdown_percent": 0.0,
        "mode": "AUTO_DEMO",
        "point": 0.001,
    }

    result = evaluate_decision(decision, context)

    assert result["approved"] is True
    assert result["checks"]["sl_range_ok"] is True


@patch("app.risk.risk_manager.settings")
@patch("app.risk.trade_validator.validate_trade_params")
def test_low_ai_risk_reward_is_allowed_when_other_checks_pass(mock_validate, mock_settings):
    from app.ai_engine.schemas import (
        AIDecisionResponse,
        ConfidenceLabel,
        Decision,
        EntryPlan,
        EntryType,
        ExecutionPermission,
        MarketRegime,
        TimeframeBias,
    )
    from app.risk.risk_manager import evaluate_decision

    mock_settings.effective_min_confidence = 0.55
    mock_settings.effective_min_risk_reward = 1.5
    mock_settings.effective_min_sl_pips = 30
    mock_settings.effective_max_sl_pips = 100
    mock_settings.max_open_positions = 1
    mock_settings.max_daily_drawdown_percent = 2.0
    mock_settings.live_trading_enabled = False
    mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}
    decision = AIDecisionResponse(
        decision=Decision.SELL,
        confidence=0.65,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_plan=EntryPlan(
            entry_type=EntryType.MARKET,
            preferred_entry_price=1.14468,
            stop_loss=1.14768,
            take_profit_1=1.14268,
            risk_reward_to_tp1=0.67,
        ),
        execution_permission=ExecutionPermission(ai_allows_execution=True),
    )
    context = {
        "symbol": "EURUSDm",
        "current_bid": 1.14468,
        "current_ask": 1.14472,
        "open_positions_count": 0,
        "daily_drawdown_percent": 0.0,
        "mode": "AUTO_DEMO",
        "point": 0.00001,
    }

    result = evaluate_decision(decision, context)

    assert result["approved"] is True
    assert result["checks"]["risk_reward_ok"] is True


class TestEvaluateDecision:

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_hold_rejected(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(decision="HOLD")
        context = _make_context()

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert "HOLD" in result["reason"]

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_low_confidence_rejected(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(confidence=0.30)
        context = _make_context()

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["confidence_ok"] is False

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_ai_stop_loss_tighter_than_min_is_allowed(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(entry_price=2010.00, stop_loss=2009.90)
        context = _make_context()

        result = evaluate_decision(decision, context)

        assert result["approved"] is True
        assert result["checks"]["sl_range_ok"] is True

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_ai_risk_reward_below_minimum_is_allowed(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(risk_reward_to_tp1=0.5)
        context = _make_context()

        result = evaluate_decision(decision, context)

        assert result["approved"] is True
        assert result["checks"]["risk_reward_ok"] is True

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_max_positions_reached_rejected(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock()
        context = _make_context(positions=3)

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["positions_ok"] is False

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_drawdown_rejected(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock()
        context = _make_context(drawdown=5.0)

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["drawdown_ok"] is False

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_missing_sl_rejected(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(stop_loss=None)
        context = _make_context()

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["sl_provided"] is False

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_missing_tp_rejected(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(take_profit_1=None)
        context = _make_context()

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["tp_provided"] is False

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_valid_buy_approved(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(decision="BUY")
        context = _make_context(mode="AUTO_DEMO")

        result = evaluate_decision(decision, context)

        assert result["approved"] is True
        assert result["checks"]["live_mode_allowed"] is True
        assert result["checks"]["confidence_ok"] is True

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_valid_sell_approved(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(
            decision="SELL",
            stop_loss=2015.00,
            take_profit_1=2000.00,
            risk_reward_to_tp1=2.0,
            entry_price=2010.00,
        )
        context = _make_context(bid=2008.0, ask=2008.5, mode="AUTO_DEMO")

        result = evaluate_decision(decision, context)

        assert result["approved"] is True

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_live_auto_blocked_when_disabled(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.65
        mock_settings.effective_min_risk_reward = 1.5
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock()
        context = _make_context(mode="LIVE_AUTO")

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["live_mode_allowed"] is False


def test_high_profile_thresholds_are_aggressive():
    from app.config import settings

    original_profile = settings.risk_profile
    try:
        settings.risk_profile = "HIGH"

        assert settings.effective_min_confidence == 0.40
        assert settings.effective_min_risk_reward == 1.2
        assert settings.effective_min_sl_pips == 15
        assert settings.effective_max_sl_pips == 80
    finally:
        settings.risk_profile = original_profile


class TestHighProfileAggressiveEntry:

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_high_profile_approves_tp_at_one_point_two_r(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.40
        mock_settings.effective_min_risk_reward = 1.2
        mock_settings.effective_min_sl_pips = 15
        mock_settings.effective_max_sl_pips = 80
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(
            confidence=0.40,
            entry_price=2010.00,
            stop_loss=2008.50,
            take_profit_1=2011.82,
            risk_reward_to_tp1=1.2,
        )
        context = _make_context(point=0.01)

        result = evaluate_decision(decision, context)

        assert result["approved"] is True

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_high_profile_allows_tp_below_one_point_two_r(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.40
        mock_settings.effective_min_risk_reward = 1.2
        mock_settings.effective_min_sl_pips = 15
        mock_settings.effective_max_sl_pips = 80
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(
            confidence=0.40,
            entry_price=2010.00,
            stop_loss=2008.50,
            take_profit_1=2011.70,
            risk_reward_to_tp1=1.1,
        )
        context = _make_context(point=0.01)

        result = evaluate_decision(decision, context)

        assert result["approved"] is True
        assert result["checks"]["risk_reward_ok"] is True

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_high_profile_allows_sl_below_fifteen_pips(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.40
        mock_settings.effective_min_risk_reward = 1.2
        mock_settings.effective_min_sl_pips = 15
        mock_settings.effective_max_sl_pips = 80
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(
            confidence=0.40,
            entry_price=2010.00,
            stop_loss=2008.60,
            take_profit_1=2011.80,
            risk_reward_to_tp1=1.2,
        )

        result = evaluate_decision(decision, _make_context(point=0.01))

        assert result["approved"] is True
        assert result["checks"]["sl_range_ok"] is True


class TestDirectionLockAndMajorTrend:

    def _settings(self, mock_settings):
        mock_settings.effective_min_confidence = 0.40
        mock_settings.max_open_positions = 99
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_open_buy_rejects_sell(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        self._settings(mock_settings)
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}
        decision = _make_decision_mock(decision="SELL", stop_loss=2015.0, take_profit_1=2000.0)
        context = _make_context()
        context["open_position_state"] = {"side": "BUY", "symbol": "XAUUSD"}

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["position_direction_ok"] is False

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_open_buy_allows_buy_addon(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        self._settings(mock_settings)
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}
        decision = _make_decision_mock(decision="BUY")
        context = _make_context()
        context["open_position_state"] = {"side": "BUY", "symbol": "XAUUSD"}
        context["major_trend"] = {"bias": "D1_BULLISH", "allowed_directions": ["BUY"]}

        result = evaluate_decision(decision, context)

        assert result["approved"] is True

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_d1_bullish_rejects_sell(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        self._settings(mock_settings)
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}
        decision = _make_decision_mock(decision="SELL", stop_loss=2015.0, take_profit_1=2000.0)
        context = _make_context()
        context["major_trend"] = {"bias": "D1_BULLISH", "allowed_directions": ["BUY"]}

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["major_trend_ok"] is False

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_d1_bearish_rejects_buy(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        self._settings(mock_settings)
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}
        decision = _make_decision_mock(decision="BUY")
        context = _make_context()
        context["major_trend"] = {"bias": "D1_BEARISH", "allowed_directions": ["SELL"]}

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["major_trend_ok"] is False

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_d1_ranging_rejects_without_breakout_retest(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        self._settings(mock_settings)
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}
        decision = _make_decision_mock(decision="BUY")
        context = _make_context()
        context["major_trend"] = {"bias": "D1_RANGING", "breakout_retest_confirmed": False, "allowed_directions": []}

        result = evaluate_decision(decision, context)

        assert result["approved"] is False
        assert result["checks"]["major_trend_ok"] is False

    @patch("app.risk.risk_manager.settings")
    @patch("app.risk.trade_validator.validate_trade_params")
    def test_high_profile_allows_sl_above_eighty_pips(self, mock_validate, mock_settings):
        from app.risk.risk_manager import evaluate_decision

        mock_settings.effective_min_confidence = 0.40
        mock_settings.effective_min_risk_reward = 1.2
        mock_settings.effective_min_sl_pips = 15
        mock_settings.effective_max_sl_pips = 80
        mock_settings.max_open_positions = 1
        mock_settings.max_daily_drawdown_percent = 2.0
        mock_settings.live_trading_enabled = False
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        decision = _make_decision_mock(
            confidence=0.40,
            entry_price=2010.00,
            stop_loss=2001.90,
            take_profit_1=2019.72,
            risk_reward_to_tp1=1.2,
        )

        result = evaluate_decision(decision, _make_context(point=0.01))

        assert result["approved"] is True
        assert result["checks"]["sl_range_ok"] is True
