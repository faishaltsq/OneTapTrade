from app.config import settings
from app.logger import logger


def evaluate_decision(ai_decision, market_context: dict) -> dict:
    try:
        decision = getattr(ai_decision, "decision", None)
        decision_value = str(getattr(decision, "value", decision)).upper()
        confidence = getattr(ai_decision, "confidence", 0.0)
        symbol_name = market_context.get("symbol", "UNKNOWN")

        entry_plan = getattr(ai_decision, "entry_plan", None)
        stop_loss = getattr(entry_plan, "stop_loss", None) if entry_plan else None
        take_profit_1 = getattr(entry_plan, "take_profit_1", None) if entry_plan else None
        risk_reward_to_tp1 = getattr(entry_plan, "risk_reward_to_tp1", None) if entry_plan else None

        exec_perm = getattr(ai_decision, "execution_permission", None)
        ai_allows_execution = getattr(exec_perm, "ai_allows_execution", True) if exec_perm else True

        checks = {
            "is_hold": False,
            "smc_probability_ok": True,
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

        logger.info(
            f"Evaluating decision: {decision}, confidence={confidence}, "
            f"symbol={symbol_name}"
        )

        if decision_value == "HOLD":
            checks["is_hold"] = True
            return _add_symbol(_reject(checks, "AI decided HOLD - no trade to execute"), symbol_name)

        smc_probability = market_context.get("smc_probability") or {}
        semantic_decision = str(smc_probability.get("pre_ai_decision") or "").upper()
        final_score = smc_probability.get("final_score")
        checks["smc_probability_ok"] = True

        if smc_probability and semantic_decision in {"NO_TRADE", "WAIT"}:
            checks["smc_probability_ok"] = False
            return _add_symbol(_reject(checks, f"SMC probability decision {semantic_decision}"), symbol_name)

        if smc_probability and not semantic_decision:
            checks["smc_probability_ok"] = False
            return _add_symbol(_reject(checks, "SMC probability score missing"), symbol_name)

        if final_score is not None and float(final_score) < settings.min_signal_probability:
            checks["smc_probability_ok"] = False
            return _add_symbol(_reject(
                checks,
                f"SMC probability {float(final_score):.0f} below minimum signal probability {settings.min_signal_probability}",
            ), symbol_name)

        if confidence < settings.effective_min_confidence:
            checks["confidence_ok"] = False
            return _add_symbol(_reject(
                checks,
                f"Confidence {confidence:.2f} below minimum {settings.effective_min_confidence}",
            ), symbol_name)

        open_position_state = market_context.get("open_position_state") or {}
        open_position_side = str(open_position_state.get("side") or "").upper()
        is_same_direction_addon = open_position_side == decision_value
        if open_position_side and open_position_side != decision_value:
            checks["position_direction_ok"] = False
            return _add_symbol(_reject(
                checks,
                f"Open {open_position_side} position blocks {decision_value} on same symbol",
            ), symbol_name)

        major_trend = market_context.get("major_trend") or {}
        trend_bias = major_trend.get("bias")
        allowed_directions = major_trend.get("allowed_directions") or []
        if trend_bias == "D1_RANGING" and not major_trend.get("breakout_retest_confirmed", False):
            checks["major_trend_ok"] = False
            return _add_symbol(_reject(checks, "D1 ranging requires breakout and retest confirmation"), symbol_name)
        if allowed_directions and decision_value not in allowed_directions:
            checks["major_trend_ok"] = False
            return _add_symbol(_reject(
                checks,
                f"D1 major trend {trend_bias} allows {allowed_directions}, blocks {decision_value}",
            ), symbol_name)

        open_positions_count = market_context.get("open_positions_count", 0)
        if not is_same_direction_addon and open_positions_count >= settings.max_open_positions:
            checks["positions_ok"] = False
            return _add_symbol(_reject(
                checks,
                f"Open positions ({open_positions_count}) at or above max ({settings.max_open_positions})",
            ), symbol_name)

        open_orders_count_symbol = market_context.get(
            "open_orders_count_symbol",
            market_context.get("open_positions_count_symbol", 0),
        )
        if open_orders_count_symbol >= settings.max_positions_per_symbol:
            checks["positions_per_symbol_ok"] = False
            return _add_symbol(_reject(
                checks,
                f"{symbol_name} orders ({open_orders_count_symbol}) "
                f"at or above per-symbol max ({settings.max_positions_per_symbol})",
            ), symbol_name)

        daily_drawdown_percent = market_context.get("daily_drawdown_percent", 0.0)
        if daily_drawdown_percent >= settings.max_daily_drawdown_percent:
            checks["drawdown_ok"] = False
            return _add_symbol(_reject(
                checks,
                f"Daily drawdown {daily_drawdown_percent:.2f}% reaches/exceeds max {settings.max_daily_drawdown_percent}%",
            ), symbol_name)

        if stop_loss is None:
            checks["sl_provided"] = False
            return _add_symbol(_reject(checks, "Stop loss is not provided"), symbol_name)

        if take_profit_1 is None:
            checks["tp_provided"] = False
            return _add_symbol(_reject(checks, "Take profit 1 is not provided"), symbol_name)

        from app.risk.trade_validator import validate_trade_params

        current_bid = market_context.get("current_bid", 0.0)
        current_ask = market_context.get("current_ask", 0.0)

        trade_validation = validate_trade_params(
            ai_decision, symbol_name, current_bid, current_ask
        )
        if not trade_validation["valid"]:
            checks["trade_params_valid"] = False
            error_detail = "; ".join(trade_validation["errors"])
            return _add_symbol(_reject(checks, f"Trade params invalid: {error_detail}"), symbol_name)

        if not ai_allows_execution:
            checks["ai_allows"] = False
            return _add_symbol(_reject(checks, "AI blocked execution"), symbol_name)

        mode = market_context.get("mode", "")
        if mode == "LIVE_AUTO" and not settings.live_trading_enabled:
            checks["live_mode_allowed"] = False
            return _add_symbol(_reject(checks, "LIVE_AUTO mode but live trading is disabled"), symbol_name)

        reason = "All checks passed - trade approved"
        logger.info(f"Decision APPROVED: {decision} {symbol_name} (confidence={confidence:.2f})")

        return {
            "approved": True,
            "symbol": symbol_name,
            "reason": reason,
            "checks": checks,
            "decision_summary": (
                f"APPROVED | {decision} {symbol_name} | "
                f"Conf: {confidence:.2f} | R:R: {risk_reward_to_tp1} | "
                f"SL: {stop_loss} | TP1: {take_profit_1}"
            ),
        }

    except Exception as e:
        logger.exception(f"Risk evaluation error: {e}")
        return {
            "approved": False,
            "symbol": market_context.get("symbol", "UNKNOWN"),
            "reason": f"Risk evaluation failed: {str(e)}",
            "checks": {},
            "decision_summary": "ERROR during risk evaluation",
        }


def _reject(checks: dict, reason: str) -> dict:
    logger.info(f"Decision REJECTED: {reason}")
    return {
        "approved": False,
        "reason": reason,
        "checks": checks,
        "decision_summary": f"REJECTED | {reason}",
    }


def _add_symbol(result: dict, symbol: str) -> dict:
    result["symbol"] = symbol
    return result
