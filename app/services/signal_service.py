from typing import Optional

from app.config import settings
from app.logger import logger


def generate_signal(symbol: Optional[str] = None) -> dict:
    sym = symbol or settings.default_symbol

    logger.info(f"Generating signal for {sym}...")

    try:
        from app.market_data.providers import get_market_data_provider, neutral_account_context

        provider = get_market_data_provider()
        logger.info(f"Step 1: Market data provider ready — source={settings.market_data_source}")

        symbol_info = provider.get_symbol_info(sym)
        if symbol_info is None:
            return {"error": f"Failed to get symbol info for {sym}"}
        logger.info(f"Step 2: Got symbol info for {sym}")

        price = provider.get_latest_price(sym)
        bid = price.get("bid") or price.get("last") or 0.0
        ask = price.get("ask") or price.get("last") or bid
        logger.info(f"Step 3: Got latest TradingView price — bid={bid}, ask={ask}")

        spread_points = 0
        logger.info(f"Step 5: Spread = {spread_points} pts")

        timeframes = settings.daytrade_timeframe_list
        df_d1 = provider.get_candles(sym, timeframe=timeframes[0], count=50)
        df_h4 = provider.get_candles(sym, timeframe=timeframes[1], count=100)
        df_h1 = provider.get_candles(sym, timeframe=timeframes[2], count=100)
        df_m15 = provider.get_candles(sym, timeframe=timeframes[3], count=100)
        logger.info(
            f"Step 6: Fetched candles — {timeframes[0]}: {len(df_d1)}, {timeframes[1]}: {len(df_h4)}, "
            f"{timeframes[2]}: {len(df_h1)}, {timeframes[3]}: {len(df_m15)}"
        )

        depth_data = None
        logger.info("Step 7: Market depth unavailable in TradingView signal-only mode")

        account_context = neutral_account_context()
        daily_drawdown = account_context["daily_drawdown_percent"]
        open_positions_count = account_context["open_positions_count"]
        logger.info(
            f"Step 8: Neutral account context — dd={daily_drawdown}%, positions={open_positions_count}"
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
        market_payload["market_data_source"] = settings.market_data_source.upper()
        market_payload["daytrade_timeframes"] = timeframes
        logger.info(f"Step 9: Market payload built — regime: {market_payload.get('overall_regime', {}).get('regime')}")

        logger.info("Step 10: Saving market snapshot to DB...")
        snapshot_row = None
        try:
            from app.database.repositories import save_market_snapshot

            entry_timeframe_section = market_payload.get("entry_timeframe", {})
            current_price = market_payload.get("current_price", {})

            technical = {
                timeframes[1]: {
                    "indicators": market_payload.get("higher_timeframe", {}).get("indicators", {}),
                    "market_structure": market_payload.get("higher_timeframe", {}).get("market_structure", {}),
                },
                timeframes[2]: {
                    "indicators": market_payload.get("primary_timeframe", {}).get("indicators", {}),
                    "market_structure": market_payload.get("primary_timeframe", {}).get("market_structure", {}),
                },
                timeframes[3]: {
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
                "timeframe": timeframes[3],
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

        from app.analysis.noise_filter import evaluate_noise_filter

        noise_result = evaluate_noise_filter(df_d1, df_h4, df_h1, df_m15, settings.risk_profile)
        logger.info(f"Noise filter result: passed={noise_result['passed']}, blocked_by={noise_result['blocked_by']}")

        if not noise_result["passed"]:
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

            regime_raw = market_payload.get("overall_regime", {}).get("regime", "UNCLEAR")
            try:
                regime_enum = MarketRegime(regime_raw)
            except ValueError:
                regime_enum = MarketRegime.UNCLEAR

            hold_decision = AIDecisionResponse(
                decision=Decision.HOLD,
                confidence=0.0,
                confidence_label=ConfidenceLabel.LOW,
                market_regime=regime_enum,
                higher_timeframe_bias=TimeframeBias.UNCLEAR,
                entry_timeframe_bias=TimeframeBias.UNCLEAR,
                main_reason=f"Noise filter: {noise_result['hold_reason']}",
                entry_plan=EntryPlan(entry_type=EntryType.NONE),
                execution_permission=ExecutionPermission(
                    ai_allows_execution=False,
                    reason=f"Noise filter: {noise_result['hold_reason']}",
                ),
                risk_notes=RiskNotes(
                    main_risk=noise_result["hold_reason"],
                    invalidation_condition="Wait for noise filter conditions to clear",
                    conditions_to_avoid_trade=[noise_result["hold_reason"]],
                ),
                final_comment=f"HOLD (noise filter) — {noise_result['hold_reason']}",
                strategy_mode=settings.strategy_mode,
                trading_style=settings.effective_style,
            )

            try:
                from app.ai_engine.decision_parser import format_decision_for_db
                from app.database.repositories import save_ai_decision

                decision_db = format_decision_for_db(hold_decision)
                decision_db["symbol"] = sym
                decision_db["market_snapshot_id"] = snapshot_id
                decision_db["model_name"] = "noise_filter"
                decision_db["input_json"] = {**market_payload, "noise_filter": noise_result}
                decision_db["output_json"] = hold_decision.model_dump()

                decision_row = save_ai_decision(decision_db)
            except Exception as e:
                logger.error(f"Failed to save noise-filter HOLD decision: {e}")
                decision_row = None

            return {
                "symbol": sym,
                "ai_decision": hold_decision,
                "risk_result": {
                    "approved": False,
                    "reason": f"Noise filter: {noise_result['hold_reason']}",
                    "checks": {},
                    "decision_summary": f"NOISE_FILTER | {noise_result['hold_reason']}",
                },
                "market_payload": market_payload,
                "snapshot_id": snapshot_id,
                "decision_id": decision_row.get("id") if decision_row else None,
                "noise_filter": noise_result,
            }

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
