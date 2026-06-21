import sys
sys.path.insert(0, r'C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade')

from app.ai_engine import (
    AIDecisionResponse, Decision, ConfidenceLabel, MarketRegime, TimeframeBias,
    EntryType, EntryPlan, ExecutionPermission, RiskNotes,
    AIDecisionPartial, DecisionValidationError,
    build_system_prompt, build_user_prompt,
    validate_decision, extract_json_from_response,
    format_decision_for_db, format_decision_for_telegram,
)

# 1. Schemas
resp = AIDecisionResponse(
    decision=Decision.BUY,
    confidence=0.8,
    confidence_label=ConfidenceLabel.HIGH,
    market_regime=MarketRegime.TRENDING_UP,
    higher_timeframe_bias=TimeframeBias.BULLISH,
    entry_timeframe_bias=TimeframeBias.BULLISH,
    main_reason="Strong trend",
    entry_plan=EntryPlan(entry_type=EntryType.LIMIT, stop_loss=2500.0, take_profit_1=2510.0, preferred_entry_price=2505.0),
    execution_permission=ExecutionPermission(ai_allows_execution=True, reason="All checks passed"),
    risk_notes=RiskNotes(main_risk="FOMC in 2h", invalidation_condition="Price below 2490"),
)
print("1. AIDecisionResponse schema OK")

partial = AIDecisionPartial(decision=Decision.HOLD, confidence=0.3)
print("2. AIDecisionPartial schema OK")

# 3. DecisionValidationError
try:
    raise DecisionValidationError("test")
except DecisionValidationError:
    pass
print("3. DecisionValidationError OK")

# 4. Prompt builders
sys_prompt = build_system_prompt()
assert "trading system" in sys_prompt.lower()
payload = {"symbol": "XAUUSD", "bid": 2500.0}
user_prompt = build_user_prompt(payload)
assert "XAUUSD" in user_prompt
print("4. Prompt builders OK")

# 5. Validate BUY with SL/TP passes
validated = validate_decision(resp)
assert validated.decision == Decision.BUY
print("5. validate_decision (BUY valid) OK")

# 6. HOLD auto-corrects entry_type to NONE + ai_allows_execution to False
hold_resp = AIDecisionResponse(
    decision=Decision.HOLD,
    confidence=0.2,
    confidence_label=ConfidenceLabel.LOW,
    market_regime=MarketRegime.UNCLEAR,
    higher_timeframe_bias=TimeframeBias.UNCLEAR,
    entry_timeframe_bias=TimeframeBias.UNCLEAR,
    entry_plan=EntryPlan(entry_type=EntryType.MARKET, stop_loss=2500.0),
    execution_permission=ExecutionPermission(ai_allows_execution=True),
)
corrected = validate_decision(hold_resp)
assert corrected.entry_plan.entry_type == EntryType.NONE
assert not corrected.execution_permission.ai_allows_execution
print("6. HOLD auto-correction OK")

# 7. BUY missing SL -> HOLD
buy_no_sl = AIDecisionResponse(
    decision=Decision.BUY,
    confidence=0.8,
    confidence_label=ConfidenceLabel.HIGH,
    market_regime=MarketRegime.TRENDING_UP,
    higher_timeframe_bias=TimeframeBias.BULLISH,
    entry_timeframe_bias=TimeframeBias.BULLISH,
    entry_plan=EntryPlan(entry_type=EntryType.LIMIT, stop_loss=None, take_profit_1=2510.0),
    execution_permission=ExecutionPermission(ai_allows_execution=True),
)
corrected2 = validate_decision(buy_no_sl)
assert corrected2.decision == Decision.HOLD
print("7. Missing SL -> HOLD auto-correction OK")

# 8. Confidence label mismatch
mismatch = AIDecisionResponse(
    decision=Decision.HOLD,
    confidence=0.8,
    confidence_label=ConfidenceLabel.LOW,
    market_regime=MarketRegime.UNCLEAR,
    higher_timeframe_bias=TimeframeBias.UNCLEAR,
    entry_timeframe_bias=TimeframeBias.UNCLEAR,
)
corrected3 = validate_decision(mismatch)
assert corrected3.confidence_label == ConfidenceLabel.HIGH
print("8. Confidence label auto-correction OK")

# 9. extract_json plain
result = extract_json_from_response('{"decision": "HOLD"}')
assert result["decision"] == "HOLD"
print("9. extract_json plain JSON OK")

# 10. extract_json markdown
md_json = '```json\n{"decision": "BUY"}\n```'
result2 = extract_json_from_response(md_json)
assert result2["decision"] == "BUY"
print("10. extract_json markdown OK")

# 11. extract_json mixed text
mixed = 'Some text before\n{"decision": "SELL"}\nSome text after'
result3 = extract_json_from_response(mixed)
assert result3["decision"] == "SELL"
print("11. extract_json mixed text OK")

# 12. extract_json raises on garbage
try:
    extract_json_from_response("no json here at all")
    assert False, "Should have raised"
except ValueError:
    pass
print("12. extract_json ValueError on garbage OK")

# 13. format_decision_for_db
db_dict = format_decision_for_db(resp)
assert db_dict["decision"] == "BUY"
assert db_dict["stop_loss"] == 2500.0
assert db_dict["entry_type"] == "LIMIT"
print("13. format_decision_for_db OK")

# 14. format_decision_for_telegram BUY
tg_msg = format_decision_for_telegram(resp)
assert chr(0x1F7E2) in tg_msg  # green circle
assert "XAUUSD" in tg_msg
print("14. format_decision_for_telegram BUY OK")

# 15. format_decision_for_telegram SELL
sell_resp = AIDecisionResponse(
    decision=Decision.SELL,
    confidence=0.75,
    confidence_label=ConfidenceLabel.HIGH,
    market_regime=MarketRegime.TRENDING_DOWN,
    higher_timeframe_bias=TimeframeBias.BEARISH,
    entry_timeframe_bias=TimeframeBias.BEARISH,
    main_reason="Downtrend",
    entry_plan=EntryPlan(entry_type=EntryType.STOP, stop_loss=2520.0, take_profit_1=2490.0, risk_reward_to_tp1=2.0),
    execution_permission=ExecutionPermission(ai_allows_execution=True, reason="Clear setup"),
)
tg_sell = format_decision_for_telegram(sell_resp)
assert chr(0x1F534) in tg_sell  # red circle
print("15. format_decision_for_telegram SELL OK")

# 16. format_decision_for_telegram HOLD
hold_resp2 = AIDecisionResponse(
    decision=Decision.HOLD,
    confidence=0.3,
    confidence_label=ConfidenceLabel.LOW,
    market_regime=MarketRegime.UNCLEAR,
    higher_timeframe_bias=TimeframeBias.UNCLEAR,
    entry_timeframe_bias=TimeframeBias.UNCLEAR,
    main_reason="Unclear trend",
)
tg_hold = format_decision_for_telegram(hold_resp2)
assert chr(0x26AA) in tg_hold  # white circle
print("16. format_decision_for_telegram HOLD OK")

# 17. format with risk result
tg_risk = format_decision_for_telegram(resp, {"passed": True, "block_reason": None})
assert "Risk Manager" in tg_risk
print("17. format_decision_for_telegram with risk OK")

# 18. format with failed risk
tg_fail = format_decision_for_telegram(resp, {"passed": False, "block_reason": "Max drawdown"})
assert "Block Reason" in tg_fail
print("18. format_decision_for_telegram failed risk OK")

print()
print("ALL 18 TESTS PASSED")


def test_validate_decision_does_not_generate_missing_sl_tp():
    decision = AIDecisionResponse(
        decision=Decision.BUY,
        confidence=0.5,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.TRENDING_UP,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BULLISH,
        entry_plan=EntryPlan(entry_type=EntryType.MARKET),
        execution_permission=ExecutionPermission(ai_allows_execution=True),
    )
    payload = {
        "current_price": {"bid": 2010.0, "ask": 2010.5},
        "entry_timeframe": {"indicators": {"atr_14": 1.5}},
        "risk_config": {"point": 0.01},
    }

    corrected = validate_decision(decision, market_payload=payload)

    assert corrected.decision == Decision.HOLD
    assert corrected.entry_plan.entry_type == EntryType.NONE
    assert corrected.entry_plan.stop_loss is None
    assert corrected.entry_plan.take_profit_1 is None
    assert corrected.execution_permission.ai_allows_execution is False


def test_validate_decision_corrects_ai_allows_execution_false_on_buy_sell():
    decision = AIDecisionResponse(
        decision=Decision.SELL,
        confidence=0.75,
        confidence_label=ConfidenceLabel.HIGH,
        market_regime=MarketRegime.TRENDING_DOWN,
        higher_timeframe_bias=TimeframeBias.BEARISH,
        entry_timeframe_bias=TimeframeBias.BEARISH,
        entry_plan=EntryPlan(
            entry_type=EntryType.MARKET,
            preferred_entry_price=4168.262,
            stop_loss=4165.5,
            take_profit_1=4145.0,
            risk_reward_to_tp1=2.2,
        ),
        execution_permission=ExecutionPermission(ai_allows_execution=False, reason=""),
    )

    corrected = validate_decision(decision)

    assert corrected.decision == Decision.SELL
    assert corrected.execution_permission.ai_allows_execution is True


def test_validated_decision_includes_strategy_mode_and_trading_style():
    from unittest.mock import patch, MagicMock
    from app.ai_engine.deepseek_client import get_ai_decision
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
