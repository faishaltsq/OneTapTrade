import json
import re
from app.ai_engine.schemas import AIDecisionResponse


def extract_json_from_response(text: str) -> dict:
    if not text or not text.strip():
        raise ValueError("Empty response text")

    text = text.strip()

    code_block_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)
    matches = code_block_pattern.findall(text)
    if matches:
        for match in matches:
            candidate = match.strip()
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidate = text[first_brace : last_brace + 1]
        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError:
            pass

    first_bracket = text.find("[{")
    last_bracket = text.rfind("}]")
    if first_bracket != -1 and last_bracket != -1:
        json_candidate = text[first_bracket : last_bracket + 2]
        try:
            parsed = json.loads(json_candidate)
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed[0]
        except json.JSONDecodeError:
            pass

    try:
        import ast
        parsed = ast.literal_eval(text)
        if isinstance(parsed, dict):
            return parsed
        elif isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
            return parsed[0]
    except (ValueError, SyntaxError):
        pass

    raise ValueError(f"Could not extract valid JSON from response: {text[:300]}")


def format_decision_for_db(decision: AIDecisionResponse) -> dict:
    return {
        "decision": decision.decision.value,
        "confidence": decision.confidence,
        "entry_type": decision.entry_plan.entry_type.value,
        "stop_loss": decision.entry_plan.stop_loss,
        "take_profit_1": decision.entry_plan.take_profit_1,
        "take_profit_2": decision.entry_plan.take_profit_2,
        "risk_reward_to_tp1": decision.entry_plan.risk_reward_to_tp1,
        "ai_allows_execution": decision.execution_permission.ai_allows_execution,
    }


def format_decision_for_telegram(decision: AIDecisionResponse, risk_result: dict = None) -> str:
    emoji = {
        "BUY": "🟢",
        "SELL": "🔴",
        "HOLD": "⚪",
    }

    e = emoji.get(decision.decision.value, "❓")

    lines = [
        f"{e} *AI Trading Decision* {e}",
        "",
        f"📊 *Symbol:* XAUUSD",
        f"🎯 *Decision:* {decision.decision.value}",
        f"📈 *Confidence:* {decision.confidence:.0%} ({decision.confidence_label.value})",
        f"🌊 *Market Regime:* {decision.market_regime.value}",
        "",
        f"*MTF Bias:*",
        f"  • Higher TF: {decision.higher_timeframe_bias.value}",
        f"  • Entry TF: {decision.entry_timeframe_bias.value}",
        "",
        f"💡 *Reason:* {decision.main_reason}",
    ]

    if decision.decision in ("BUY", "SELL"):
        ep = decision.entry_plan
        lines.append("")
        lines.append(f"📋 *Entry Plan ({ep.entry_type.value}):*")
        if ep.preferred_entry_price is not None:
            lines.append(f"  • Entry: {ep.preferred_entry_price}")
        if ep.entry_area_low is not None and ep.entry_area_high is not None:
            lines.append(f"  • Entry Zone: {ep.entry_area_low} – {ep.entry_area_high}")
        if ep.stop_loss is not None:
            lines.append(f"  • Stop Loss: {ep.stop_loss}")
        if ep.take_profit_1 is not None:
            lines.append(f"  • Take Profit 1: {ep.take_profit_1}")
        if ep.take_profit_2 is not None:
            lines.append(f"  • Take Profit 2: {ep.take_profit_2}")
        if ep.risk_reward_to_tp1 is not None:
            lines.append(f"  • R:R to TP1: {ep.risk_reward_to_tp1:.2f}")
        if ep.risk_reward_to_tp2 is not None:
            lines.append(f"  • R:R to TP2: {ep.risk_reward_to_tp2:.2f}")

    rn = decision.risk_notes
    if rn.main_risk:
        lines.append("")
        lines.append(f"⚠️ *Risk:* {rn.main_risk}")
    if rn.invalidation_condition:
        lines.append(f"🛑 *Invalidation:* {rn.invalidation_condition}")

    exec_perm = decision.execution_permission
    lines.append("")
    lines.append(
        f"✅ *AI Allows Execution:* {'Yes' if exec_perm.ai_allows_execution else 'No'}"
    )
    if exec_perm.reason:
        lines.append(f"  ↳ {exec_perm.reason}")

    if risk_result is not None:
        lines.append("")
        lines.append("🛡 *Risk Manager Result:*")
        passed = risk_result.get("passed", False)
        lines.append(f"  • Passed: {'Yes ✅' if passed else 'No ❌'}")
        if not passed:
            lines.append(f"  • Block Reason: {risk_result.get('block_reason', 'N/A')}")

    if decision.final_comment:
        lines.append("")
        lines.append(f"💬 {decision.final_comment}")

    return "\n".join(lines)
