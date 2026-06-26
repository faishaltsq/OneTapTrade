import asyncio

from app.config import settings
from app.logger import logger
from app.services.bot_status_service import BotStatusService


def _mt5_to_tv_symbol(mt5_symbol: str) -> str:
    import re
    symbol = mt5_symbol.upper()
    symbol = re.sub(r"\.[A-Z0-9]+$", "", symbol)

    TV_SYMBOL_MAP = {
        "US100": "NAS100",
        "US30": "US30",
        "US500": "PEPPERSTONE:US500",
        "NAS100": "NAS100",
        "GER40": "GER40",
        "BRENT": "FOREXCOM:USOIL",
    }
    return TV_SYMBOL_MAP.get(symbol, symbol)


def _check_closed_trades_for_post_mortem() -> None:
    try:
        from app.database.repositories import get_open_trades, update_trade_status
        from app.mt5_connector.positions import get_open_positions

        open_db_trades = get_open_trades()
        if not open_db_trades:
            return

        mt5_tickets = set()
        try:
            positions = get_open_positions(None)
            mt5_tickets = {p.get("ticket") for p in positions if p.get("ticket")}
        except Exception:
            return

        for trade in open_db_trades:
            ticket = trade.get("mt5_ticket")
            trade_id = trade.get("id")
            if not ticket or not trade_id:
                continue

            if ticket not in mt5_tickets:
                try:
                    import MetaTrader5 as mt5
                    deals = mt5.history_deals_get(ticket=ticket)
                    close_price = None
                    profit = None
                    if deals:
                        for d in deals:
                            if d.entry == mt5.DEAL_ENTRY_OUT:
                                close_price = d.price
                                profit = d.profit
                                break

                    update_trade_status(
                        trade_id=trade_id,
                        status="CLOSED",
                        close_price=close_price,
                        profit=profit,
                    )
                    logger.info(f"Trade {trade_id} closed (ticket {ticket}, profit={profit})")

                    if profit is not None and float(profit) < 0:
                        from app.ai_engine.post_mortem import process_loss_trade
                        updated_trade = {**trade, "close_price": close_price, "profit": profit}
                        process_loss_trade(updated_trade)
                except Exception as e:
                    logger.debug(f"Failed to process closed trade {trade_id}: {e}")
    except Exception as e:
        logger.debug(f"Post-mortem check error: {e}")


class TradingLoop:
    def __init__(self):
        self._status_service = BotStatusService()
        self._running = False
        self._interval = settings.effective_loop_interval
        self._last_decision = None
        self._last_risk_result = None
        self._last_decisions = {}

    @property
    def symbol(self) -> str:
        syms = settings.symbols
        return syms[0] if syms else settings.default_symbol

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def status(self) -> BotStatusService:
        return self._status_service

    def start(self):
        self._running = True
        try:
            from app.database.repositories import log_bot_event

            log_bot_event(
                event_type="trading_loop_started",
                message="Trading loop started",
                payload={"mode": self._status_service.mode, "interval": self._interval},
            )
        except Exception as e:
            logger.error(f"Failed to log loop start event: {e}")
        logger.info(f"Trading loop started — mode={self._status_service.mode}, interval={self._interval}s")

    def stop(self):
        self._running = False
        try:
            from app.database.repositories import log_bot_event

            log_bot_event(
                event_type="trading_loop_stopped",
                message="Trading loop stopped",
            )
        except Exception as e:
            logger.error(f"Failed to log loop stop event: {e}")
        logger.info("Trading loop stopped")

    def set_paused(self, paused: bool):
        self._status_service.set_paused(paused)

    def is_paused(self) -> bool:
        return self._status_service.is_paused

    def set_mode(self, mode: str):
        self._status_service.set_mode(mode)

    def get_status(self) -> dict:
        status = self._status_service.get_status()
        status["loop_running"] = self._running
        return status

    async def _fetch_tv_data(self, symbol: str) -> dict:
        from app.tv_connector import get_tv_tools
        from app.logger import logger

        tools = get_tv_tools()
        if tools is None:
            return {}

        from app.services.tv_autochart_service import _quick_cdp_check
        if not await _quick_cdp_check():
            return {}

        tv_symbol = _mt5_to_tv_symbol(symbol)
        result = {"chart": None, "studies": [], "lines": [], "labels": [], "tables": [], "boxes": []}

        try:
            await tools.set_symbol(tv_symbol)
        except Exception as e:
            logger.debug(f"TV set_symbol failed for {symbol}: {e}")

        try:
            chart = await tools.get_chart_state()
            result["chart"] = chart.model_dump() if chart else None
        except Exception as e:
            logger.debug(f"TV get_chart_state failed: {e}")

        try:
            studies = await tools.get_study_values()
            result["studies"] = [s.model_dump() for s in studies]
        except Exception as e:
            logger.debug(f"TV get_study_values failed: {e}")

        try:
            lines = await tools.get_pine_lines()
            result["lines"] = [l.model_dump() for l in lines]
        except Exception as e:
            logger.debug(f"TV get_pine_lines failed: {e}")

        try:
            labels = await tools.get_pine_labels()
            result["labels"] = [l.model_dump() for l in labels]
        except Exception as e:
            logger.debug(f"TV get_pine_labels failed: {e}")

        try:
            tables = await tools.get_pine_tables()
            result["tables"] = tables
        except Exception as e:
            logger.debug(f"TV get_pine_tables failed: {e}")

        try:
            boxes = await tools.get_pine_boxes()
            result["boxes"] = [b.model_dump() for b in boxes]
        except Exception as e:
            logger.debug(f"TV get_pine_boxes failed: {e}")

        return result

    async def run_once(self) -> dict:
        symbols = settings.symbols
        results = []

        try:
            from app.services.breakeven_service import manage_breakeven_stops

            summary = await asyncio.to_thread(manage_breakeven_stops, None)
            if summary.get("modified", 0) > 0:
                logger.info(f"Breakeven management complete: {summary}")
        except Exception as e:
            logger.error(f"Breakeven management failed: {e}")

        try:
            from app.services.pending_order_manager import enforce_pending_order_cap

            for sym in symbols:
                cap_result = await asyncio.to_thread(enforce_pending_order_cap, sym, settings.max_positions_per_symbol)
                if cap_result.get("cancelled", 0) > 0:
                    logger.info(f"Pending order cap enforced for {sym}: {cap_result}")
        except Exception as e:
            logger.error(f"Pending order cap enforcement failed: {e}")

        try:
            await asyncio.to_thread(_check_closed_trades_for_post_mortem)
        except Exception as e:
            logger.debug(f"Post-mortem check failed: {e}")

        for symbol in symbols:
            result = await self._run_symbol(symbol)
            results.append(result)

        return {"symbols": symbols, "results": results}

    async def _run_symbol(self, symbol: str, force: bool = False) -> dict:
        logger.info(f"Starting analysis cycle for {symbol}...")

        if self._status_service.is_paused and not force:
            logger.info("Trading loop is paused — skipping cycle")
            return {"symbol": symbol, "skipped": True, "reason": "Trading paused"}

        from app.services.signal_service import generate_signal

        tv_data = await self._fetch_tv_data(symbol)
        signal_result = await asyncio.to_thread(generate_signal, symbol, tv_data or None)

        if "error" in signal_result:
            logger.error(f"Signal generation failed: {signal_result['error']}")
            return signal_result

        ai_decision = signal_result.get("ai_decision")
        risk_result = signal_result.get("risk_result", {})
        decision_id = signal_result.get("decision_id")

        self._last_decision = ai_decision
        self._last_risk_result = risk_result

        if decision_id:
            self._last_decisions[decision_id] = signal_result

        decision_str = getattr(ai_decision, "decision", None)
        if hasattr(decision_str, "value"):
            decision_str = decision_str.value

        approved = risk_result.get("approved", False)
        mode = self._status_service.mode
        is_hold = (decision_str == "HOLD")

        logger.info(
            f"Analysis result [{symbol}]: decision={decision_str}, "
            f"approved={approved}, mode={mode}"
        )

        if is_hold:
            try:
                from app.telegram_bot.bot import send_trade_signal
                await send_trade_signal(ai_decision, risk_result, decision_id or "", signal_result.get("market_payload"))
            except Exception as e:
                logger.error(f"Failed to send HOLD signal: {e}")
            try:
                from app.database.repositories import log_bot_event
                log_bot_event(event_type="market_update", message=f"HOLD {symbol}")
            except Exception:
                pass
            return signal_result

        if mode == "SIGNAL_ONLY":
            logger.info(f"SIGNAL_ONLY mode — sending signal to Telegram [{symbol}]")
            try:
                from app.telegram_bot.bot import send_trade_signal

                await send_trade_signal(ai_decision, risk_result, decision_id or "", signal_result.get("market_payload"))
            except Exception as e:
                logger.error(f"Failed to send trade signal: {e}")

            try:
                from app.database.repositories import log_bot_event

                log_bot_event(
                    event_type="signal_sent",
                    message=f"Signal sent: {getattr(ai_decision, 'decision', 'N/A')} {symbol}",
                    payload={"decision_id": decision_id},
                )
            except Exception as e:
                logger.error(f"Failed to log signal event: {e}")

            return signal_result

        if mode == "SEMI_AUTO":
            logger.info("SEMI_AUTO mode — sending signal with approve/reject buttons")
            try:
                from app.telegram_bot.bot import send_trade_signal

                await send_trade_signal(ai_decision, risk_result, decision_id or "", signal_result.get("market_payload"))
            except Exception as e:
                logger.error(f"Failed to send semi-auto signal: {e}")

            try:
                from app.database.repositories import log_bot_event

                log_bot_event(
                    event_type="semi_auto_signal",
                    message=f"Semi-auto signal sent: {getattr(ai_decision, 'decision', 'N/A')} {symbol}",
                    payload={"decision_id": decision_id},
                )
            except Exception as e:
                logger.error(f"Failed to log semi-auto event: {e}")

            return signal_result

        if mode == "AUTO_DEMO":
            if not approved:
                logger.info(f"AUTO_DEMO mode — trade rejected by risk: {risk_result.get('reason')}")
                try:
                    from app.telegram_bot.bot import send_trade_signal, notify_trade_rejected
                    await send_trade_signal(ai_decision, risk_result, decision_id or "", signal_result.get("market_payload"))
                    await notify_trade_rejected(risk_result.get("reason", "Risk check failed"), decision=ai_decision)
                except Exception as e:
                    logger.error(f"Failed to send rejection notice: {e}")
                return signal_result

            logger.info("AUTO_DEMO mode — sending signal then executing trade")
            try:
                from app.telegram_bot.bot import send_trade_signal
                await send_trade_signal(ai_decision, risk_result, decision_id or "", signal_result.get("market_payload"))
            except Exception as e:
                logger.error(f"Failed to send signal before execution: {e}")

            exec_result = await self._do_execute(ai_decision, risk_result, symbol, signal_result)

            if exec_result.get("success"):
                try:
                    from app.telegram_bot.bot import notify_trade_executed
                    await notify_trade_executed(exec_result, ai_decision=ai_decision)
                except Exception as e:
                    logger.error(f"Failed to send execution notice: {e}")
            else:
                try:
                    from app.telegram_bot.bot import notify_trade_rejected
                    await notify_trade_rejected(exec_result.get("error", "Execution failed"), decision=ai_decision)
                except Exception as e:
                    logger.error(f"Failed to send rejection notice: {e}")

            return exec_result

        if mode == "LIVE_AUTO":
            if not settings.is_live_allowed:
                logger.warning("LIVE_AUTO mode but live trading is disabled — skipping execution")
                return {"skipped": True, "reason": "Live trading not enabled"}

            if not approved:
                logger.info(f"LIVE_AUTO mode — trade rejected by risk: {risk_result.get('reason')}")
                try:
                    from app.telegram_bot.bot import send_trade_signal, notify_trade_rejected
                    await send_trade_signal(ai_decision, risk_result, decision_id or "", signal_result.get("market_payload"))
                    await notify_trade_rejected(risk_result.get("reason", "Risk check failed"), decision=ai_decision)
                except Exception as e:
                    logger.error(f"Failed to send rejection notice: {e}")
                return signal_result

            logger.info("LIVE_AUTO mode — sending signal then executing on live account")
            try:
                from app.telegram_bot.bot import send_trade_signal
                await send_trade_signal(ai_decision, risk_result, decision_id or "", signal_result.get("market_payload"))
            except Exception as e:
                logger.error(f"Failed to send signal before execution: {e}")

            exec_result = await self._do_execute(ai_decision, risk_result, symbol, signal_result)

            if exec_result.get("success"):
                try:
                    from app.telegram_bot.bot import notify_trade_executed
                    await notify_trade_executed(exec_result, ai_decision=ai_decision)
                except Exception as e:
                    logger.error(f"Failed to send execution notice: {e}")
            else:
                try:
                    from app.telegram_bot.bot import notify_trade_rejected
                    await notify_trade_rejected(exec_result.get("error", "Execution failed"), decision=ai_decision)
                except Exception as e:
                    logger.error(f"Failed to send rejection notice: {e}")

            return exec_result

        return signal_result

    async def _send_market_update(self, ai_decision, symbol: str, market_payload: dict | None = None):
        try:
            from app.telegram_bot.bot import send_message
            from app.telegram_bot.message_templates import format_market_trend_alert

            text = format_market_trend_alert(ai_decision, symbol, market_payload=market_payload)
            await send_message(text)
            return

            conf = getattr(ai_decision, "confidence", 0.0)
            regime = getattr(ai_decision, "market_regime", None)
            htf = getattr(ai_decision, "higher_timeframe_bias", None)
            etf = getattr(ai_decision, "entry_timeframe_bias", None)
            reason = getattr(ai_decision, "main_reason", "")

            regime_str = regime.value if hasattr(regime, "value") else str(regime or "?")
            htf_str = htf.value if hasattr(htf, "value") else str(htf or "?")
            etf_str = etf.value if hasattr(etf, "value") else str(etf or "?")

            text = (
                f"<b>\u26aa Market Update — {symbol}</b>\n\n"
                f"<b>Decision:</b> HOLD\n"
                f"<b>Regime:</b> {regime_str} | D1: {htf_str} | M5: {etf_str}\n"
                f"<b>Confidence:</b> {conf:.0%}"
            )
            if reason:
                text += f"\n<i>{reason}</i>"

            await send_message(text)
        except Exception as e:
            logger.error(f"Failed to send market update: {e}")

    async def _do_execute(self, ai_decision, risk_result, symbol, signal_result) -> dict:
        try:
            from app.mt5_connector.connection import ensure_mt5_connected
            from app.mt5_connector.market_data import get_latest_tick, get_symbol_info
            from app.mt5_connector.account import get_balance

            if not await asyncio.to_thread(ensure_mt5_connected):
                return {"success": False, "error": "MT5 disconnected before execution"}

            tick = await asyncio.to_thread(get_latest_tick, symbol)
            if tick is None:
                return {"success": False, "error": "Cannot get fresh tick for execution"}

            bid = tick.get("bid", 0.0)
            ask = tick.get("ask", 0.0)

            sym_info = await asyncio.to_thread(get_symbol_info, symbol)
            if sym_info is None:
                return {"success": False, "error": "Cannot get symbol info for execution"}

            balance = await asyncio.to_thread(get_balance)
            if balance is None:
                return {"success": False, "error": "Cannot get account balance"}

            from app.services.execution_service import execute_trade

            market_payload = signal_result.get("market_payload")
            return await asyncio.to_thread(execute_trade, ai_decision, risk_result, sym_info, balance, bid, ask, market_payload)

        except Exception as e:
            logger.exception(f"Error during trade execution: {e}")
            return {"success": False, "error": str(e)}

    async def handle_approve_callback(self, decision_id: str) -> dict:
        if decision_id not in self._last_decisions:
            logger.warning(f"handle_approve_callback: decision_id {decision_id} not found")
            return {"success": False, "error": "Decision not found or expired"}

        stored = self._last_decisions[decision_id]
        ai_decision = stored.get("ai_decision")
        symbol = stored.get("symbol", settings.default_symbol)

        logger.info(f"handle_approve_callback: refreshing market data for {symbol}")

        try:
            from app.mt5_connector.connection import ensure_mt5_connected
            from app.mt5_connector.market_data import (
                get_latest_tick,
                get_spread,
                get_symbol_info,
            )
            from app.mt5_connector.account import get_balance, get_daily_drawdown_percent
            from app.mt5_connector.positions import get_open_positions_count
            from app.mt5_connector.orders import get_pending_orders_count

            if not ensure_mt5_connected():
                return {"success": False, "error": "MT5 disconnected"}

            tick = get_latest_tick(symbol)
            if tick is None:
                return {"success": False, "error": "Cannot get fresh tick data"}

            current_bid = tick.get("bid", 0.0)
            current_ask = tick.get("ask", 0.0)
            spread_points = int(get_spread(symbol) or 0)
            open_positions_count = get_open_positions_count(None)
            open_positions_count_symbol = get_open_positions_count(symbol)
            open_orders_count_symbol = open_positions_count_symbol + get_pending_orders_count(symbol)
            daily_drawdown = get_daily_drawdown_percent() or 0.0

            market_context = {
                "symbol": symbol,
                "current_bid": current_bid,
                "current_ask": current_ask,
                "spread_points": spread_points,
                "open_positions_count": open_positions_count,
                "open_positions_count_symbol": open_positions_count_symbol,
                "open_orders_count_symbol": open_orders_count_symbol,
                "has_open_position": open_positions_count_symbol > 0,
                "daily_drawdown_percent": daily_drawdown,
                "mode": self._status_service.mode,
            }

            from app.risk.risk_manager import evaluate_decision

            logger.info("Re-running risk evaluation...")
            risk_result = evaluate_decision(ai_decision, market_context)

            try:
                from app.database.repositories import save_risk_check

                save_risk_check(
                    ai_decision_id=decision_id,
                    approved=risk_result.get("approved", False),
                    reason=risk_result.get("reason", "Unknown"),
                    checks=risk_result.get("checks", {}),
                )
            except Exception as e:
                logger.error(f"Failed to save risk check on approval: {e}")

            if not risk_result.get("approved"):
                reason = risk_result.get("reason", "Risk check failed")
                logger.info(f"handle_approve_callback: trade rejected — {reason}")
                return {"success": False, "error": reason, "risk_result": risk_result}

            sym_info = get_symbol_info(symbol)
            if sym_info is None:
                return {"success": False, "error": "Cannot get symbol info"}

            balance = get_balance()
            if balance is None:
                return {"success": False, "error": "Cannot get account balance"}

            from app.services.execution_service import execute_trade

            exec_result = execute_trade(ai_decision, risk_result, sym_info, balance, current_bid, current_ask, None)

            self._last_decisions.pop(decision_id, None)

            return exec_result

        except Exception as e:
            logger.exception(f"Error in handle_approve_callback: {e}")
            return {"success": False, "error": str(e)}

    async def run_forever(self):
        self.start()
        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                logger.exception(f"Unhandled error in trading loop cycle: {e}")

            current_interval = settings.effective_loop_interval
            if current_interval != self._interval:
                logger.info(f"Loop interval changed: {self._interval}s -> {current_interval}s (profile={settings.risk_profile})")
                self._interval = current_interval
            await asyncio.sleep(self._interval)
