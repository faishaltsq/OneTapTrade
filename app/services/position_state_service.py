from datetime import datetime, timezone
from uuid import uuid4

from app.logger import logger

_OPEN_POSITION_STATE: dict[str, list[dict]] = {}


def _side_from_position_type(position_type) -> str:
    return "BUY" if int(position_type or 0) == 0 else "SELL"


def clear_position_state() -> None:
    _OPEN_POSITION_STATE.clear()


def get_open_position_state(symbol: str | None = None):
    if symbol:
        positions = _OPEN_POSITION_STATE.get(symbol, [])
        if not positions:
            return None
        return positions[0]
    return _OPEN_POSITION_STATE


def has_opposite_position(symbol: str, decision: str) -> bool:
    decision_side = str(decision).upper()
    for position in _OPEN_POSITION_STATE.get(symbol, []):
        side = position.get("side")
        if side in ("BUY", "SELL") and decision_side in ("BUY", "SELL") and side != decision_side:
            return True
    return False


def sync_open_positions_from_mt5() -> dict:
    summary = {"live_positions": 0, "saved_trades": 0, "existing_trades": 0, "errors": 0}
    clear_position_state()

    try:
        from app.mt5_connector.positions import get_open_positions

        positions = get_open_positions(None)
        summary["live_positions"] = len(positions)
    except Exception as e:
        logger.error(f"Failed to read MT5 positions during startup sync: {e}")
        summary["errors"] += 1
        return summary

    for position in positions:
        try:
            side = _side_from_position_type(position.get("type"))
            symbol = position.get("symbol")
            ticket = position.get("ticket")
            state = {
                "symbol": symbol,
                "side": side,
                "ticket": ticket,
                "entry_price": position.get("price_open"),
                "sl": position.get("sl"),
                "tp": position.get("tp"),
                "volume": position.get("volume"),
                "profit": position.get("profit"),
            }
            _OPEN_POSITION_STATE.setdefault(symbol, []).append(state)

            try:
                from app.database.repositories import get_trade_by_mt5_ticket, save_trade

                existing = get_trade_by_mt5_ticket(ticket)
                if existing:
                    summary["existing_trades"] += 1
                else:
                    trade_data = {
                        "id": str(uuid4()),
                        "symbol": symbol,
                        "mt5_ticket": ticket,
                        "side": side,
                        "lot": position.get("volume"),
                        "entry_price": position.get("price_open"),
                        "stop_loss": position.get("sl"),
                        "take_profit": position.get("tp"),
                        "status": "OPEN",
                        "opened_at": datetime.now(timezone.utc).isoformat(),
                    }
                    if save_trade(trade_data):
                        summary["saved_trades"] += 1
            except Exception as e:
                logger.warning(f"Position DB sync skipped for ticket={ticket}: {e}")
        except Exception as e:
            logger.error(f"Failed to sync position state: {e}")
            summary["errors"] += 1

    logger.info(f"Startup position sync: {summary}")
    return summary
