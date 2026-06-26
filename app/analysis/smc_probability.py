from __future__ import annotations

from app.config import settings


SEMANTIC_TO_CORE = {
    "BUY_SETUP": "BUY",
    "SELL_SETUP": "SELL",
    "WAIT": "HOLD",
    "NO_TRADE": "HOLD",
}

PROFILE_MIN_RISK_REWARD = {
    "LOW": 2.5,
    "MEDIUM": 1.8,
    "HIGH": 1.5,
}


def core_decision_from_semantic(decision: str) -> str:
    return SEMANTIC_TO_CORE.get(str(decision).upper(), "HOLD")


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


def build_rule_based_hold_decision(score: dict, market_payload: dict):
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

    final_score = int(score.get("final_score") or 0)
    confidence = max(0.0, min(1.0, float(final_score) / 100.0))
    risk_notes = score.get("risk_notes") or []
    _ = market_payload

    return AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=confidence,
        confidence_label=_confidence_label(final_score),
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
        main_reason="Rule-based SMC probability score used without AI review",
        entry_plan=EntryPlan(entry_type=EntryType.NONE),
        execution_permission=ExecutionPermission(
            ai_allows_execution=False,
            reason="Manual confirmation required",
        ),
        risk_notes=RiskNotes(
            main_risk="; ".join(str(note) for note in risk_notes),
            invalidation_condition=score.get("invalidation", "manual confirmation required"),
        ),
        final_comment=(
            "AI analysis unavailable, rule-based score used"
            if score.get("ai_unavailable")
            else "Rule-based score used"
        ),
        strategy_mode=settings.strategy_mode,
        trading_style=settings.effective_style,
    )


def score_smc_setup(market_payload: dict, risk_profile: str | None = None) -> dict:
    payload = market_payload or {}
    profile = str(
        risk_profile
        or (payload.get("risk_config") or {}).get("risk_profile")
        or settings.risk_profile
    ).upper()
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
    cross_conflict = direction != "neutral" and any(
        trend not in {direction, "neutral"} for trend in filter_trends + execution_trends
    )
    if filter_conflict or execution_conflict or cross_conflict:
        forced_no_trade = True
        score += _add(
            adjustments,
            "structure_conflict",
            -25,
            "Profile filter and execution structures conflict",
        )
        weaknesses.append("Profile filter and execution structures conflict")
    elif direction in {"bullish", "bearish"}:
        score += _add(
            adjustments,
            "swing_internal_alignment",
            20,
            f"Profile filter and execution bias align {direction}",
        )
        confluence.append(f"Profile filter and execution bias align {direction}")

    if profile == "HIGH":
        d1 = _trend(payload, "D1")
        if d1 not in {direction, "neutral"} and direction != "neutral":
            score += _add(adjustments, "d1_context_warning", -7, "D1 context conflicts with scalping direction")
            weaknesses.append("D1 context conflicts with scalping direction")

    smc = payload.get("smc", {}) or {}
    support_group_count = 0
    has_liquidity = bool(smc.get("liquidity_levels"))
    has_choch = _has_directional_choch(smc, direction)
    has_bos = _has_directional_bos(smc, direction)
    has_choch_liquidity = has_choch and has_liquidity
    if has_choch_liquidity:
        score += _add(adjustments, "choch_after_liquidity", 15, "CHoCH appears with liquidity clue")
        confluence.append("CHoCH appears with liquidity clue")
    elif has_choch:
        score += _add(adjustments, "missing_liquidity_sweep", -10, "CHoCH has no liquidity confirmation")
        weaknesses.append("CHoCH has no liquidity confirmation")

    if has_bos:
        support_group_count += 1
        score += _add(adjustments, "bos_confirmation", 10, "Directional BOS supports setup")
        confluence.append("Directional BOS supports setup")

    if has_liquidity:
        support_group_count += 1
        score += _add(adjustments, "liquidity_clue", 5, "EQH/EQL/liquidity level supports context")
        confluence.append("Liquidity clue supports context")

    fvg_zones = smc.get("fvg_zones") or []
    if any(str(zone.get("direction", "")).lower() == direction for zone in fvg_zones if isinstance(zone, dict)):
        support_group_count += 1
        score += _add(adjustments, "aligned_fvg", 5, "Directional FVG supports setup")
        confluence.append("Directional FVG supports setup")

    order_blocks = smc.get("order_blocks", {}) or {}
    aligned_order_blocks = (
        order_blocks.get("demand")
        if direction == "bullish"
        else order_blocks.get("supply")
        if direction == "bearish"
        else []
    )
    if aligned_order_blocks:
        support_group_count += 1
        score += _add(adjustments, "aligned_order_block", 10, "Aligned order block supports setup")
        confluence.append("Aligned order block supports setup")

    has_entry_grade_confluence = has_choch_liquidity or support_group_count >= 2

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

    if _is_high_news_risk(payload.get("news_risk")):
        score += _add(adjustments, "news_risk_high", -100, "High news risk blocks SMC setup")
        risk_notes.append("High news risk blocks SMC setup")
        forced_no_trade = True

    entry_plan = payload.get("entry_plan_context") or {}
    rr = entry_plan.get("risk_reward_to_tp1")
    min_rr = _minimum_risk_reward(payload, profile)
    if rr is None:
        score += _add(adjustments, "risk_reward_unknown", -20, "R:R unknown, pending AI entry plan")
        weaknesses.append("R:R unknown, pending AI entry plan")
    else:
        try:
            rr_val = float(rr)
        except (ValueError, TypeError):
            score += _add(adjustments, "risk_reward_unknown", -100, f"R:R value '{rr}' is not numeric")
            risk_notes.append(f"R:R value '{rr}' is not numeric")
            forced_no_trade = True
            rr_val = None
        if rr_val is not None and rr_val < min_rr:
            score += _add(adjustments, "risk_reward_low", -100, f"R:R {rr_val} below minimum {min_rr}")
            risk_notes.append(f"R:R {rr_val} below minimum {min_rr}")
            forced_no_trade = True

    levels_available = (
        entry_plan.get("entry_available")
        and entry_plan.get("sl_available")
        and entry_plan.get("tp_available")
    )
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

    if semantic in {"BUY_SETUP", "SELL_SETUP"} and not has_entry_grade_confluence:
        _add(
            adjustments,
            "missing_smc_confluence",
            0,
            "Executable setup requires at least one real SMC confluence group",
        )
        weaknesses.append("Executable setup requires at least one real SMC confluence group")
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


def _profile_model(profile: str) -> dict:
    profile = str(profile or "MEDIUM").upper()
    if profile == "LOW":
        return {
            "profile": "LOW",
            "filter_timeframes": ["D1", "H4"],
            "execution_timeframes": ["H4", "D1"],
            "timeframe_fallback": None,
        }
    if profile == "HIGH":
        return {
            "profile": "HIGH",
            "filter_timeframes": ["H1", "H4"],
            "execution_timeframes": ["M5", "M15"],
            "timeframe_fallback": None,
        }
    return {
        "profile": "MEDIUM",
        "filter_timeframes": ["D1", "H4"],
        "execution_timeframes": ["H1"],
        "timeframe_fallback": None,
    }


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
    market_structure = section.get("market_structure", {}) if isinstance(section, dict) else {}
    raw = str(market_structure.get("trend") or market_structure.get("bias") or "").upper()
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
    for timeframe_data in choch.values() if isinstance(choch, dict) else []:
        if isinstance(timeframe_data, dict) and timeframe_data.get(target):
            return True
    return False


def _has_directional_bos(smc: dict, direction: str) -> bool:
    bos = smc.get("bos") or smc.get("break_of_structure") if isinstance(smc, dict) else {}
    target = "bullish_bos" if direction == "bullish" else "bearish_bos"
    if isinstance(bos, dict):
        if bos.get(target):
            return True
        for timeframe_data in bos.values():
            if isinstance(timeframe_data, dict) and timeframe_data.get(target):
                return True
    return False


def _minimum_risk_reward(payload: dict, profile: str) -> float:
    profile_floor = PROFILE_MIN_RISK_REWARD.get(
        str(profile or "MEDIUM").upper(),
        PROFILE_MIN_RISK_REWARD["MEDIUM"],
    )
    configured_min_rr = (payload.get("risk_config") or {}).get("min_risk_reward")
    if configured_min_rr is not None:
        return max(float(configured_min_rr), profile_floor, 1.5)
    return max(profile_floor, 1.5)


def _is_high_news_risk(news_risk) -> bool:
    if isinstance(news_risk, dict):
        raw = news_risk.get("level") or news_risk.get("risk")
    else:
        raw = news_risk
    return str(raw or "").lower() == "high"


def _premium_discount(payload: dict, direction: str) -> tuple[int, str | None]:
    smc = payload.get("smc", {}) or {}
    price = (payload.get("current_price") or {}).get("mid")
    swings = smc.get("h1_swings") or smc.get("m5_swings") or {}
    highs = swings.get("highs") or []
    lows = swings.get("lows") or []
    if price is None or not highs or not lows:
        return 0, None

    high_elem = highs[-1]
    low_elem = lows[-1]
    if not isinstance(high_elem, dict) or not isinstance(low_elem, dict):
        return 0, None
    high_price = high_elem.get("price")
    low_price = low_elem.get("price")
    if high_price is None or low_price is None:
        return 0, None

    high = float(high_price)
    low = float(low_price)
    if high <= low:
        return 0, None

    equilibrium = low + ((high - low) / 2)
    is_discount = float(price) <= equilibrium
    if direction == "bullish":
        if is_discount:
            return 10, "Buy setup occurs in discount/lower equilibrium"
        return -15, "Buy setup occurs in premium area"
    if direction == "bearish":
        if not is_discount:
            return 10, "Sell setup occurs in premium/upper equilibrium"
        return -15, "Sell setup occurs in discount area"
    return 0, None


def _quality(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def _confidence_label(score: int):
    from app.ai_engine.schemas import ConfidenceLabel

    if score >= 75:
        return ConfidenceLabel.HIGH
    if score >= 50:
        return ConfidenceLabel.MEDIUM
    return ConfidenceLabel.LOW
