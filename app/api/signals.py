import uuid
import traceback

from fastapi import APIRouter, HTTPException, Request

from app.logger import logger
from app.config import settings
from app.database.repositories import get_latest_decision
from app.mt5_connector.connection import is_mt5_connected

router = APIRouter(prefix="")


@router.get("/last-signal")
async def get_last_signal(request: Request):
    loop = request.app.state.trading_loop
    symbol = loop.symbol if loop else settings.default_symbol

    try:
        latest = get_latest_decision(symbol)
        if latest is None:
            return {"signal": None, "message": "No AI decisions found"}

        return {
            "signal": {
                "decision": latest.get("decision"),
                "confidence": latest.get("confidence"),
                "confidence_label": latest.get("confidence_label"),
                "market_regime": latest.get("market_regime"),
                "higher_timeframe_bias": latest.get("higher_timeframe_bias"),
                "entry_timeframe_bias": latest.get("entry_timeframe_bias"),
                "main_reason": latest.get("main_reason"),
                "entry_type": latest.get("entry_type"),
                "entry_area_low": latest.get("entry_area_low"),
                "entry_area_high": latest.get("entry_area_high"),
                "preferred_entry_price": latest.get("preferred_entry_price"),
                "stop_loss": latest.get("stop_loss"),
                "take_profit_1": latest.get("take_profit_1"),
                "take_profit_2": latest.get("take_profit_2"),
                "risk_reward_to_tp1": latest.get("risk_reward_to_tp1"),
                "risk_reward_to_tp2": latest.get("risk_reward_to_tp2"),
                "ai_allows_execution": latest.get("ai_allows_execution"),
                "final_comment": latest.get("final_comment"),
                "created_at": latest.get("created_at"),
            }
        }
    except Exception as e:
        logger.error(f"Failed to fetch last signal: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch last signal")


@router.post("/generate-signal")
async def generate_signal(request: Request):
    if not is_mt5_connected():
        raise HTTPException(status_code=503, detail="MT5 not connected")

    loop = request.app.state.trading_loop
    symbol = loop.symbol if loop else settings.default_symbol

    try:
        from app.mt5_connector.market_data import get_candles, get_latest_tick, get_spread, get_symbol_info
        from app.mt5_connector.account import get_balance, get_equity, get_daily_drawdown_percent
        from app.mt5_connector.positions import get_open_positions_count
        from app.analysis.feature_builder import build_market_payload
        from app.ai_engine.deepseek_client import get_ai_decision
        from app.ai_engine.decision_parser import format_decision_for_telegram

        tick = get_latest_tick(symbol)
        if tick is None:
            raise HTTPException(status_code=503, detail="Cannot fetch market tick data")

        bid = tick.get("bid", 0.0)
        ask = tick.get("ask", 0.0)
        spread_points = int(get_spread(symbol) or 0)
        symbol_info = get_symbol_info(symbol) or {}

        df_d1 = get_candles(symbol, "D1", 50)
        df_h4 = get_candles(symbol, "H4", 100)
        df_h1 = get_candles(symbol, "H1", 100)
        df_m15 = get_candles(symbol, "M5", 100)

        open_positions_count = get_open_positions_count(None)
        open_positions_count_symbol = get_open_positions_count(symbol)
        account_info = {
            "balance": get_balance(),
            "equity": get_equity(),
            "daily_drawdown_percent": get_daily_drawdown_percent(),
            "open_positions_count": open_positions_count,
            "open_positions_count_symbol": open_positions_count_symbol,
            "has_open_position": open_positions_count_symbol > 0,
        }

        market_payload = build_market_payload(
            symbol=symbol,
            df_d1=df_d1,
            df_h4=df_h4,
            df_h1=df_h1,
            df_m15=df_m15,
            bid=bid,
            ask=ask,
            spread_points=spread_points,
            account_info=account_info,
        )
        market_payload.setdefault("risk_config", {})["point"] = symbol_info.get("point", 0.01)

        ai_decision = get_ai_decision(market_payload)

        from app.risk.risk_manager import evaluate_decision

        market_context = {
            "symbol": symbol,
            "current_bid": bid,
            "current_ask": ask,
            "spread_points": spread_points,
            "open_positions_count": account_info.get("open_positions_count", 0),
            "open_positions_count_symbol": account_info.get("open_positions_count_symbol", 0),
            "has_open_position": open_positions_count_symbol > 0,
            "daily_drawdown_percent": account_info.get("daily_drawdown_percent", 0.0) or 0.0,
            "mode": settings.bot_mode,
            "point": symbol_info.get("point", 0.01),
        }
        risk_result = evaluate_decision(ai_decision, market_context)

        formatted = format_decision_for_telegram(ai_decision, risk_result)

        from app.database.repositories import save_ai_decision, save_risk_check
        from app.ai_engine.decision_parser import format_decision_for_db

        decision_data = format_decision_for_db(ai_decision)
        saved_decision = save_ai_decision(decision_data)

        decision_id = ""
        if saved_decision:
            decision_id = saved_decision.get("id", "")
            save_risk_check(
                ai_decision_id=decision_id,
                approved=risk_result.get("approved", False),
                reason=risk_result.get("reason", "Unknown"),
                checks=risk_result.get("checks", {}),
            )

        return {
            "signal": {
                "decision": ai_decision.decision.value,
                "confidence": ai_decision.confidence,
                "confidence_label": ai_decision.confidence_label.value,
                "market_regime": ai_decision.market_regime.value,
                "entry_type": ai_decision.entry_plan.entry_type.value,
                "stop_loss": ai_decision.entry_plan.stop_loss,
                "take_profit_1": ai_decision.entry_plan.take_profit_1,
                "take_profit_2": ai_decision.entry_plan.take_profit_2,
                "risk_reward_to_tp1": ai_decision.entry_plan.risk_reward_to_tp1,
            },
            "risk": {
                "approved": risk_result.get("approved", False),
                "reason": risk_result.get("reason", "Unknown"),
                "checks": risk_result.get("checks", {}),
            },
            "decision_id": decision_id,
            "telegram_preview": formatted,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate signal: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to generate signal: {str(e)}")


@router.post("/approve/{decision_id}")
async def approve_signal(request: Request, decision_id: str):
    from app.telegram_bot.bot import _pending_decisions, _decision_symbols, _trading_loop_ref

    if decision_id not in _pending_decisions:
        raise HTTPException(status_code=404, detail="Decision not found or already expired")

    decision = _pending_decisions[decision_id]

    try:
        from app.mt5_connector.market_data import get_latest_tick, get_spread, get_symbol_info
        from app.mt5_connector.account import get_balance, get_equity, get_daily_drawdown_percent
        from app.mt5_connector.positions import get_open_positions_count
        from app.mt5_connector.execution import build_order_request, send_order

        stored_decision = None
        last_decisions = getattr(_trading_loop_ref, "_last_decisions", {}) if _trading_loop_ref else {}
        if decision_id in last_decisions:
            stored_decision = last_decisions[decision_id]
        symbol = _decision_symbols.get(decision_id, (stored_decision or {}).get("symbol", settings.default_symbol))
        tick = get_latest_tick(symbol)
        if tick is None:
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            raise HTTPException(status_code=503, detail="Cannot fetch market data")

        current_bid = tick.get("bid", 0.0)
        current_ask = tick.get("ask", 0.0)
        spread_points = get_spread(symbol) or 0

        open_positions_count = get_open_positions_count(None)
        open_positions_count_symbol = get_open_positions_count(symbol)
        market_context = {
            "symbol": symbol,
            "current_bid": current_bid,
            "current_ask": current_ask,
            "spread_points": spread_points,
            "open_positions_count": open_positions_count,
            "open_positions_count_symbol": open_positions_count_symbol,
            "has_open_position": open_positions_count_symbol > 0,
            "daily_drawdown_percent": get_daily_drawdown_percent() or 0.0,
            "mode": settings.bot_mode,
        }

        from app.risk.risk_manager import evaluate_decision

        risk_result = evaluate_decision(decision, market_context)

        from app.database.repositories import save_risk_check

        save_risk_check(
            ai_decision_id=decision_id,
            approved=risk_result.get("approved", False),
            reason=risk_result.get("reason", "Unknown"),
            checks=risk_result.get("checks", {}),
        )

        if not risk_result.get("approved"):
            reason = risk_result.get("reason", "Risk check failed")
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return {"status": "rejected", "reason": reason}

        decision_str = getattr(decision, "decision", "HOLD")
        if hasattr(decision_str, "value"):
            decision_str = decision_str.value

        entry_plan = getattr(decision, "entry_plan", None)
        stop_loss = getattr(entry_plan, "stop_loss", None) if entry_plan else None
        tp1 = getattr(entry_plan, "take_profit_1", None) if entry_plan else None
        entry_type_val = getattr(entry_plan, "entry_type", None) if entry_plan else None
        is_limit = False
        if entry_type_val and hasattr(entry_type_val, "value"):
            is_limit = entry_type_val.value in ("LIMIT", "STOP")
        entry_price = getattr(entry_plan, "preferred_entry_price", None) if entry_plan else None

        from app.risk.position_sizing import calculate_lot_size

        balance = get_balance()
        sym_info = get_symbol_info(symbol)
        if balance is None or sym_info is None:
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            raise HTTPException(status_code=500, detail="Cannot fetch balance or symbol info")

        sl_distance = abs(entry_price - stop_loss) if entry_price and stop_loss else 0.0
        sl_points = sl_distance / sym_info.get("point", 0.01) if sym_info.get("point", 0) else sl_distance * 100

        sizing = calculate_lot_size(balance, sl_points, sym_info)
        if not sizing.get("is_valid"):
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return {"status": "rejected", "reason": f"Position sizing failed: {sizing.get('reason')}"}

        order_request = build_order_request(
            symbol=symbol,
            order_type=decision_str,
            lot=sizing["lot"],
            sl=stop_loss,
            tp=tp1,
            comment="AI_Approved_API",
            is_limit=is_limit,
            price=entry_price if is_limit else None,
        )

        order_result = send_order(order_request)
        if order_result is None:
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            raise HTTPException(status_code=500, detail="Order send failed")

        retcode = order_result.get("retcode", -1)
        if retcode != 10009:
            _decision_symbols.pop(decision_id, None)
            _pending_decisions.pop(decision_id, None)
            return {"status": "failed", "retcode": retcode, "comment": order_result.get("comment", "")}

        ticket = order_result.get("order")
        order_price = order_result.get("price", entry_price)

        from app.database.repositories import save_trade

        trade_data = {
            "id": str(uuid.uuid4()),
            "ai_decision_id": decision_id,
            "symbol": symbol,
            "side": decision_str,
            "lot": sizing["lot"],
            "entry_price": order_price,
            "stop_loss": stop_loss,
            "take_profit": tp1,
            "mt5_ticket": ticket,
            "status": "OPEN",
        }
        save_trade(trade_data)

        _decision_symbols.pop(decision_id, None)
        _pending_decisions.pop(decision_id, None)
        logger.info(f"Trade executed via API approval: {decision_str} {symbol} ticket={ticket}")

        return {"status": "executed", "ticket": ticket, "lot": sizing["lot"], "price": order_price}

    except HTTPException:
        _decision_symbols.pop(decision_id, None)
        _pending_decisions.pop(decision_id, None)
        raise
    except Exception as e:
        _decision_symbols.pop(decision_id, None)
        _pending_decisions.pop(decision_id, None)
        logger.error(f"Error in API approve: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reject/{decision_id}")
async def reject_signal(request: Request, decision_id: str):
    from app.telegram_bot.bot import _pending_decisions, _decision_symbols

    if decision_id not in _pending_decisions:
        raise HTTPException(status_code=404, detail="Decision not found or already expired")

    _decision_symbols.pop(decision_id, None)
    _pending_decisions.pop(decision_id, None)

    from app.database.repositories import log_bot_event

    log_bot_event(
        event_type="trade_rejected",
        message=f"Trade decision {decision_id} rejected via API",
        payload={"decision_id": decision_id},
    )

    logger.info(f"Trade rejected via API: decision_id={decision_id}")
    return {"status": "rejected", "message": "Trade rejected"}
