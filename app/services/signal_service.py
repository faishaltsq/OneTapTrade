from typing import Optional

from app.config import settings
from app.logger import logger


def generate_signal(symbol: Optional[str] = None) -> dict:
    sym = symbol or settings.default_symbol

    logger.info(f"Generating signal for {sym}...")

    try:
        from app.mt5_connector.connection import ensure_mt5_connected

        if not ensure_mt5_connected():
            logger.error("MT5 not connected, cannot generate signal")
            return {"error": "MT5 not connected"}

        logger.info("Step 1: MT5 connected")
    except Exception as e:
        logger.error(f"MT5 connection check failed: {e}")
        return {"error": f"MT5 connection check failed: {e}"}

    try:
        from app.mt5_connector.market_data import (
            get_candles,
            get_latest_tick,
            get_market_depth,
            get_spread,
            get_symbol_info,
            select_symbol,
        )

        if not select_symbol(sym):
            return {"error": f"Failed to select symbol: {sym} (may be closed or invalid)"}
        logger.info(f"Step 2: Symbol selected: {sym}")

        symbol_info = get_symbol_info(sym)
        if symbol_info is None:
            return {"error": f"Failed to get symbol info for {sym}"}
        logger.info(f"Step 3: Got symbol info for {sym}")

        tick = get_latest_tick(sym)
        if tick is None:
            return {"error": f"Failed to get tick data for {sym}"}
        bid = tick.get("bid", 0.0)
        ask = tick.get("ask", 0.0)
        logger.info(f"Step 4: Got latest tick — bid={bid}, ask={ask}")

        spread = get_spread(sym)
        spread_points = int(spread) if spread is not None else 0
        logger.info(f"Step 5: Spread = {spread_points} pts")

        df_d1 = get_candles(sym, timeframe="D1", count=50)
        df_h4 = get_candles(sym, timeframe="H4", count=100)
        df_h1 = get_candles(sym, timeframe="H1", count=100)
        df_m15 = get_candles(sym, timeframe="M5", count=100)
        logger.info(
            f"Step 6: Fetched candles — D1: {len(df_d1)}, H4: {len(df_h4)}, H1: {len(df_h1)}, M5: {len(df_m15)}"
        )

        depth_data = None
        try:
            depth_data = get_market_depth(sym)
        except Exception as e:
            logger.debug(f"Market depth unavailable: {e}")
        logger.info(f"Step 7: Market depth {'available' if depth_data else 'unavailable'}")

        from app.mt5_connector.account import (
            get_balance,
            get_daily_drawdown_percent,
            get_equity,
        )
        from app.mt5_connector.positions import get_open_positions_count, has_open_position

        balance = get_balance()
        equity = get_equity()
        daily_drawdown = get_daily_drawdown_percent()
        open_positions_count = get_open_positions_count(None)
        has_open = has_open_position(sym)

        account_context = {
            "balance": balance,
            "equity": equity,
            "daily_pnl_percent": None,
            "daily_drawdown_percent": daily_drawdown,
            "open_positions_count": open_positions_count,
            "has_open_position": has_open,
        }
        logger.info(
            f"Step 8: Account context — balance={balance}, equity={equity}, "
            f"dd={daily_drawdown}%, positions={open_positions_count}"
        )

        from app.analysis.feature_builder import build_market_payload

        market_payload = build_market_payload(
            symbol=sym,
            df_d1=df_d1,
            df_h4=df_h4,
            df_h1=df_h1,
            df_m15=df_m15,
            bid=bid,
            ask=ask,
            spread_points=spread_points,
            tick_data=None,
            depth_data=depth_data,
            account_info=account_context,
        )
        market_payload.setdefault("risk_config", {})["point"] = symbol_info.get("point", 0.01)
        logger.info(f"Step 9: Market payload built — regime: {market_payload.get('overall_regime', {}).get('regime')}")

        logger.info("Step 10: Saving market snapshot to DB...")
        snapshot_row = None
        try:
            from app.database.repositories import save_market_snapshot

            entry_timeframe_section = market_payload.get("entry_timeframe", {})
            current_price = market_payload.get("current_price", {})

            technical = {
                "H4": {
                    "indicators": market_payload.get("higher_timeframe", {}).get("indicators", {}),
                    "market_structure": market_payload.get("higher_timeframe", {}).get("market_structure", {}),
                },
                "H1": {
                    "indicators": market_payload.get("primary_timeframe", {}).get("indicators", {}),
                    "market_structure": market_payload.get("primary_timeframe", {}).get("market_structure", {}),
                },
                "M5": {
                    "indicators": market_payload.get("entry_timeframe", {}).get("indicators", {}),
                    "market_structure": market_payload.get("entry_timeframe", {}).get("market_structure", {}),
                },
            }

            volume_profile_data = entry_timeframe_section.get("volume_profile", {})
            orderflow_data = market_payload.get("orderflow_proxy", {})

            close_candle = entry_timeframe_section.get("current_candle", {})
            close_price = close_candle.get("close")

            snapshot = {
                "symbol": sym,
                "timeframe": "M5",
                "bid": bid,
                "ask": ask,
                "spread_points": spread_points,
                "close_price": close_price,
                "technical": technical,
                "volume_profile": volume_profile_data,
                "orderflow": orderflow_data,
                "raw_payload": market_payload,
            }

            snapshot_row = save_market_snapshot(snapshot)
            if snapshot_row:
                logger.info(f"Market snapshot saved: {snapshot_row.get('id')}")
            else:
                logger.warning("Market snapshot save returned None (DB unavailable)")
        except Exception as e:
            logger.error(f"Failed to save market snapshot: {e}")

        snapshot_id = snapshot_row.get("id") if snapshot_row else None

        from app.ai_engine.deepseek_client import get_ai_decision, validate_decision

        logger.info("Step 11: Requesting AI decision...")
        ai_decision = get_ai_decision(market_payload)
        logger.info("Step 12: Validating AI decision...")
        ai_decision = validate_decision(ai_decision, market_payload=market_payload)
        logger.info(
            f"AI decision: {ai_decision.decision.value} | "
            f"conf={ai_decision.confidence:.2f} | allows_exec={ai_decision.execution_permission.ai_allows_execution}"
        )

        logger.info("Step 13: Saving AI decision to DB...")
        decision_row = None
        try:
            from app.ai_engine.decision_parser import format_decision_for_db
            from app.database.repositories import save_ai_decision

            decision_db = format_decision_for_db(ai_decision)
            decision_db["symbol"] = sym
            decision_db["market_snapshot_id"] = snapshot_id
            decision_db["model_name"] = settings.deepseek_model
            decision_db["input_json"] = market_payload
            decision_db["output_json"] = ai_decision.model_dump()

            decision_row = save_ai_decision(decision_db)
            if decision_row:
                logger.info(f"AI decision saved: {decision_row.get('id')}")
            else:
                logger.warning("AI decision save returned None (DB unavailable)")
        except Exception as e:
            logger.error(f"Failed to save AI decision: {e}")

        decision_id = decision_row.get("id") if decision_row else None

        market_context = {
            "symbol": sym,
            "current_bid": bid,
            "current_ask": ask,
            "spread_points": spread_points,
            "open_positions_count": open_positions_count,
            "daily_drawdown_percent": daily_drawdown or 0.0,
            "mode": settings.bot_mode,
            "point": symbol_info.get("point", 0.01) if symbol_info else 0.01,
            "major_trend": market_payload.get("major_trend", {}),
            "open_position_state": market_payload.get("open_position_state", {}),
        }
        logger.info(f"Step 14: Market context built for risk eval")

        from app.risk.risk_manager import evaluate_decision

        logger.info("Step 15: Running risk manager...")
        risk_result = evaluate_decision(ai_decision, market_context)

        logger.info("Step 16: Saving risk check to DB...")
        try:
            from app.database.repositories import save_risk_check

            if decision_id:
                save_risk_check(
                    ai_decision_id=decision_id,
                    approved=risk_result.get("approved", False),
                    reason=risk_result.get("reason", "Unknown"),
                    checks=risk_result.get("checks", {}),
                )
        except Exception as e:
            logger.error(f"Failed to save risk check: {e}")

        logger.info(
            f"Signal generation complete for {sym}: "
            f"decision={ai_decision.decision.value}, "
            f"risk_approved={risk_result.get('approved')}"
        )

        return {
            "symbol": sym,
            "ai_decision": ai_decision,
            "risk_result": risk_result,
            "market_payload": market_payload,
            "snapshot_id": snapshot_id,
            "decision_id": decision_id,
        }

    except Exception as e:
        logger.exception(f"Unexpected error generating signal for {sym}: {e}")
        return {"error": f"Signal generation failed: {e}"}
