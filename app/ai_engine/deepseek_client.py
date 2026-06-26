import json
import re
from openai import OpenAI
from app.config import settings
from app.logger import logger
from app.ai_engine.schemas import (
    AIDecisionResponse,
    AIDecisionPartial,
    ConfidenceLabel,
    Decision,
    EntryType,
    EntryPlan,
    ExecutionPermission,
    RiskNotes,
    MarketRegime,
    TimeframeBias,
)
from app.ai_engine.prompt_builder import build_system_prompt, build_user_prompt
from app.ai_engine.decision_parser import extract_json_from_response


def _default_hold() -> AIDecisionResponse:
    return AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.0,
        confidence_label=ConfidenceLabel.LOW,
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
        main_reason="AI decision engine failed to produce a valid response",
        entry_plan=EntryPlan(entry_type=EntryType.NONE),
        execution_permission=ExecutionPermission(
            ai_allows_execution=False,
            reason="AI response parsing failed",
        ),
        risk_notes=RiskNotes(
            main_risk="AI engine error",
            invalidation_condition="AI engine error",
            conditions_to_avoid_trade=["AI engine error"],
        ),
        final_comment="Decision engine error — defaulting to HOLD",
    )


_ENTRY_TYPE_ALIASES = {
    "SELL_LIMIT": "LIMIT",
    "BUY_LIMIT": "LIMIT",
    "SELL_STOP": "STOP",
    "BUY_STOP": "STOP",
}


def _normalize_entry_type(data: dict) -> None:
    entry_plan = data.get("entry_plan")
    if not isinstance(entry_plan, dict):
        return
    raw = entry_plan.get("entry_type")
    if isinstance(raw, str):
        normalized = _ENTRY_TYPE_ALIASES.get(raw.upper(), raw)
        if normalized != raw:
            logger.info(f"Normalized entry_type: {raw} -> {normalized}")
            entry_plan["entry_type"] = normalized


def get_ai_decision(market_payload: dict) -> AIDecisionResponse:
    if not settings.deepseek_api_key:
        logger.error("DeepSeek API key not configured")
        return _default_hold()

    client = OpenAI(
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        timeout=45,
    )

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(market_payload)

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=settings.deepseek_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=4000,
            )
        except Exception as e:
            logger.error(f"DeepSeek API call attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                continue
            return _default_hold()

    usage = getattr(response, "usage", None)
    if usage:
        logger.debug(
            f"DeepSeek token usage — prompt: {usage.prompt_tokens}, "
            f"completion: {usage.completion_tokens}, total: {usage.total_tokens}"
        )

    raw_text = response.choices[0].message.content or ""
    logger.info(f"DeepSeek response length: {len(raw_text)} chars")
    logger.info(f"DeepSeek response preview: {raw_text[:200]}")

    if not raw_text.strip():
        logger.error("DeepSeek returned empty response")
        return _default_hold()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("AI response was not valid JSON, attempting extraction from markdown")
    try:
        data = extract_json_from_response(raw_text)
    except ValueError as e:
        logger.error(f"Failed to extract JSON from AI response: {e}")
        logger.debug(f"Raw AI response: {raw_text[:500]}")
        return _default_hold()

    _normalize_entry_type(data)

    if "confidence" in data and data["confidence"] is not None:
        try:
            conf_val = float(data["confidence"])
            if conf_val > 1.0:
                data["confidence"] = conf_val / 100.0
                logger.info(f"Normalized confidence: {conf_val} -> {data['confidence']}")
        except (ValueError, TypeError):
            pass

    try:
        partial = AIDecisionPartial(**data)
    except Exception as e:
        logger.error(f"Failed to parse AI response into AIDecisionPartial: {e}")
        return _default_hold()

    parsed = partial.model_dump(exclude_none=True)

    required_defaults = {
        "decision": Decision.HOLD,
        "confidence": 0.0,
        "confidence_label": ConfidenceLabel.LOW,
        "market_regime": MarketRegime.UNCLEAR,
        "higher_timeframe_bias": TimeframeBias.UNCLEAR,
        "entry_timeframe_bias": TimeframeBias.UNCLEAR,
        "entry_plan": EntryPlan(entry_type=EntryType.NONE),
        "execution_permission": ExecutionPermission(ai_allows_execution=False, reason=""),
        "risk_notes": RiskNotes(),
    }

    for key, default in required_defaults.items():
        if key not in parsed:
            parsed[key] = default

    validated = validate_decision(AIDecisionResponse(**parsed), market_payload=market_payload)

    validated.strategy_mode = settings.strategy_mode
    validated.trading_style = settings.effective_style

    logger.info(
        f"AI decision: {validated.decision.value} | "
        f"confidence: {validated.confidence:.2f} ({validated.confidence_label.value}) | "
        f"regime: {validated.market_regime.value} | "
        f"allows_execution: {validated.execution_permission.ai_allows_execution}"
    )

    return validated


def validate_decision(decision: AIDecisionResponse, market_payload: dict | None = None) -> AIDecisionResponse:
    modified = False

    if decision.decision == Decision.HOLD:
        if decision.entry_plan.entry_type != EntryType.NONE:
            logger.warning(
                f"HOLD decision has entry_type={decision.entry_plan.entry_type.value}, forcing to NONE"
            )
            decision.entry_plan = EntryPlan(entry_type=EntryType.NONE)
            modified = True
        if decision.execution_permission.ai_allows_execution:
            logger.warning("HOLD decision has ai_allows_execution=True, forcing to False")
            decision.execution_permission.ai_allows_execution = False
            decision.execution_permission.reason = decision.execution_permission.reason or ""
            modified = True
        decision.entry_plan.stop_loss = None
        decision.entry_plan.take_profit_1 = None
        decision.entry_plan.take_profit_2 = None
        decision.entry_plan.risk_reward_to_tp1 = None
        decision.entry_plan.risk_reward_to_tp2 = None

    if decision.decision in (Decision.BUY, Decision.SELL):
        if decision.entry_plan.stop_loss is None:
            logger.warning(f"{decision.decision.value} decision missing stop_loss, switching to HOLD")
            decision.decision = Decision.HOLD
            decision.entry_plan = EntryPlan(entry_type=EntryType.NONE)
            decision.execution_permission.ai_allows_execution = False
            modified = True
        elif decision.entry_plan.take_profit_1 is None:
            logger.warning(f"{decision.decision.value} decision missing take_profit_1, switching to HOLD")
            decision.decision = Decision.HOLD
            decision.entry_plan = EntryPlan(entry_type=EntryType.NONE)
            decision.execution_permission.ai_allows_execution = False
            modified = True
        elif not decision.execution_permission.ai_allows_execution:
            logger.warning(f"{decision.decision.value} decision has ai_allows_execution=False, forcing to True")
            decision.execution_permission.ai_allows_execution = True
            decision.execution_permission.reason = decision.execution_permission.reason or "Auto-corrected from AI false"
            modified = True

    expected_label = _confidence_to_label(decision.confidence)
    if decision.confidence_label != expected_label:
        logger.warning(
            f"Confidence label mismatch: {decision.confidence_label.value} for "
            f"confidence={decision.confidence:.2f}, expected {expected_label.value}. Auto-correcting."
        )
        decision.confidence_label = expected_label
        modified = True

    if modified:
        if decision.final_comment:
            decision.final_comment += " "
        decision.final_comment += "[AUTO-CORRECTED BY VALIDATOR]"

    return decision


def _confidence_to_label(confidence: float) -> ConfidenceLabel:
    if confidence >= 0.75:
        return ConfidenceLabel.HIGH
    elif confidence >= 0.5:
        return ConfidenceLabel.MEDIUM
    else:
        return ConfidenceLabel.LOW
