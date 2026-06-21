import pytest
from pydantic import ValidationError

from app.ai_engine.schemas import (
    AIDecisionResponse,
    AIDecisionPartial,
    Decision,
    ConfidenceLabel,
    MarketRegime,
    TimeframeBias,
    EntryType,
    EntryPlan,
    ExecutionPermission,
    RiskNotes,
)


class TestAIDecisionResponse:

    def test_valid_data_passes(self):
        data = {
            "decision": Decision.BUY,
            "confidence": 0.8,
            "confidence_label": ConfidenceLabel.HIGH,
            "market_regime": MarketRegime.TRENDING_UP,
            "higher_timeframe_bias": TimeframeBias.BULLISH,
            "entry_timeframe_bias": TimeframeBias.BULLISH,
            "main_reason": "Strong trend on H4",
            "entry_plan": EntryPlan(
                entry_type=EntryType.MARKET,
                preferred_entry_price=2010.00,
                stop_loss=2000.00,
                take_profit_1=2020.00,
                take_profit_2=2030.00,
                risk_reward_to_tp1=2.0,
                risk_reward_to_tp2=4.0,
            ),
            "execution_permission": ExecutionPermission(
                ai_allows_execution=True,
                reason="All conditions met",
            ),
            "risk_notes": RiskNotes(
                main_risk="FOMC meeting today",
                invalidation_condition="H4 close below 2000",
                conditions_to_avoid_trade=["Spread > 30 points"],
            ),
            "final_comment": "Good risk-to-reward setup",
        }

        obj = AIDecisionResponse(**data)

        assert obj.decision == Decision.BUY
        assert obj.confidence == 0.8
        assert obj.entry_plan.stop_loss == 2000.00
        assert obj.execution_permission.ai_allows_execution is True

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            AIDecisionResponse(
                decision=Decision.BUY,
            )

    def test_invalid_decision_enum_raises(self):
        with pytest.raises(ValidationError):
            AIDecisionResponse(
                decision="INVALID",
                confidence=0.8,
                confidence_label=ConfidenceLabel.HIGH,
                market_regime=MarketRegime.TRENDING_UP,
                higher_timeframe_bias=TimeframeBias.BULLISH,
                entry_timeframe_bias=TimeframeBias.BULLISH,
            )

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError):
            AIDecisionResponse(
                decision=Decision.HOLD,
                confidence=-0.1,
                confidence_label=ConfidenceLabel.LOW,
                market_regime=MarketRegime.RANGING,
                higher_timeframe_bias=TimeframeBias.NEUTRAL,
                entry_timeframe_bias=TimeframeBias.NEUTRAL,
            )

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            AIDecisionResponse(
                decision=Decision.HOLD,
                confidence=1.5,
                confidence_label=ConfidenceLabel.HIGH,
                market_regime=MarketRegime.RANGING,
                higher_timeframe_bias=TimeframeBias.NEUTRAL,
                entry_timeframe_bias=TimeframeBias.NEUTRAL,
            )

    def test_confidence_boundary_zero_valid(self):
        obj = AIDecisionResponse(
            decision=Decision.HOLD,
            confidence=0.0,
            confidence_label=ConfidenceLabel.LOW,
            market_regime=MarketRegime.UNCLEAR,
            higher_timeframe_bias=TimeframeBias.UNCLEAR,
            entry_timeframe_bias=TimeframeBias.UNCLEAR,
        )
        assert obj.confidence == 0.0

    def test_confidence_boundary_one_valid(self):
        obj = AIDecisionResponse(
            decision=Decision.BUY,
            confidence=1.0,
            confidence_label=ConfidenceLabel.HIGH,
            market_regime=MarketRegime.TRENDING_UP,
            higher_timeframe_bias=TimeframeBias.BULLISH,
            entry_timeframe_bias=TimeframeBias.BULLISH,
        )
        assert obj.confidence == 1.0

    def test_minimal_hold_valid(self):
        obj = AIDecisionResponse(
            decision=Decision.HOLD,
            confidence=0.3,
            confidence_label=ConfidenceLabel.LOW,
            market_regime=MarketRegime.UNCLEAR,
            higher_timeframe_bias=TimeframeBias.UNCLEAR,
            entry_timeframe_bias=TimeframeBias.UNCLEAR,
        )
        assert obj.decision == Decision.HOLD
        assert obj.entry_plan.entry_type == EntryType.NONE
        assert obj.execution_permission.ai_allows_execution is False

    def test_default_entry_plan_values(self):
        obj = AIDecisionResponse(
            decision=Decision.HOLD,
            confidence=0.5,
            confidence_label=ConfidenceLabel.MEDIUM,
            market_regime=MarketRegime.RANGING,
            higher_timeframe_bias=TimeframeBias.NEUTRAL,
            entry_timeframe_bias=TimeframeBias.NEUTRAL,
        )
        assert obj.entry_plan.stop_loss is None
        assert obj.entry_plan.take_profit_1 is None

    def test_seLL_valid(self):
        obj = AIDecisionResponse(
            decision=Decision.SELL,
            confidence=0.75,
            confidence_label=ConfidenceLabel.HIGH,
            market_regime=MarketRegime.TRENDING_DOWN,
            higher_timeframe_bias=TimeframeBias.BEARISH,
            entry_timeframe_bias=TimeframeBias.BEARISH,
            entry_plan=EntryPlan(
                entry_type=EntryType.MARKET,
                preferred_entry_price=2020.00,
                stop_loss=2030.00,
                take_profit_1=2000.00,
            ),
            execution_permission=ExecutionPermission(
                ai_allows_execution=True,
            ),
        )
        assert obj.decision == Decision.SELL


class TestAIDecisionPartial:

    def test_empty_partial_valid(self):
        obj = AIDecisionPartial()
        assert obj.decision is None
        assert obj.confidence is None

    def test_partial_fields(self):
        obj = AIDecisionPartial(
            decision=Decision.BUY,
            confidence=0.9,
        )
        assert obj.decision == Decision.BUY
        assert obj.confidence == 0.9
        assert obj.market_regime is None

    def test_partial_confidence_validation(self):
        obj = AIDecisionPartial(confidence=0.5)
        assert obj.confidence == 0.5

        with pytest.raises(ValidationError):
            AIDecisionPartial(confidence=1.5)

    def test_partial_invalid_enum(self):
        with pytest.raises(ValidationError):
            AIDecisionPartial(decision="UNKNOWN")

    def test_partial_with_nested_entry_plan(self):
        obj = AIDecisionPartial(
            entry_plan=EntryPlan(
                stop_loss=2000.00,
                take_profit_1=2020.00,
            ),
        )
        assert obj.entry_plan is not None
        assert obj.entry_plan.stop_loss == 2000.00
        assert obj.entry_plan.take_profit_1 == 2020.00


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
