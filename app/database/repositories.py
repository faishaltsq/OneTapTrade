from datetime import datetime, timezone

from app.database.supabase_client import get_supabase
from app.logger import logger


# ── helpers ──────────────────────────────────────────────────────────────────

def _table(name: str):
    client = get_supabase()
    if client is None:
        return None
    return client.table(name)


# ── bot_settings ─────────────────────────────────────────────────────────────

def get_bot_settings() -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        result = supabase.table("bot_settings").select("*").limit(1).execute()
        rows = result.data
        if not rows:
            logger.warning("No bot_settings row found")
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to get bot settings: {e}")
        return None


def update_bot_settings(updates: dict) -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        allowed = {
            "symbol", "enabled", "mode", "is_paused",
            "risk_per_trade_percent", "max_daily_drawdown_percent",
            "max_spread_points", "min_confidence", "min_risk_reward",
            "max_open_positions", "risk_profile", "strategy_mode",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            logger.warning("update_bot_settings: no allowed fields in updates")
            return None

        current = get_bot_settings()
        if current is None:
            logger.warning("Cannot update bot_settings — no existing row")
            return None

        try:
            result = (
                supabase.table("bot_settings")
                .update(filtered)
                .eq("id", current["id"])
                .execute()
            )
        except Exception as e:
            msg = str(e)
            if "PGRST204" in msg and "risk_profile" in msg and "risk_profile" in filtered:
                retry = {k: v for k, v in filtered.items() if k != "risk_profile"}
                logger.warning("bot_settings.risk_profile missing in Supabase schema; applying remaining settings only")
                if not retry:
                    return None
                result = (
                    supabase.table("bot_settings")
                    .update(retry)
                    .eq("id", current["id"])
                    .execute()
                )
            else:
                raise
        rows = result.data
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to update bot settings: {e}")
        return None


def update_bot_mode(mode: str) -> dict | None:
    return update_bot_settings({"mode": mode})


def set_paused(paused: bool) -> dict | None:
    return update_bot_settings({"is_paused": paused})


# ── market_snapshots ─────────────────────────────────────────────────────────

def save_market_snapshot(snapshot: dict) -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        result = supabase.table("market_snapshots").insert(snapshot).execute()
        rows = result.data
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to save market snapshot: {e}")
        return None


def get_latest_snapshot(symbol: str = None) -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        query = supabase.table("market_snapshots").select("*").order("created_at", desc=True).limit(1)
        if symbol:
            query = query.eq("symbol", symbol)
        result = query.execute()
        rows = result.data
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to get latest snapshot: {e}")
        return None


# ── ai_decisions ─────────────────────────────────────────────────────────────

def save_ai_decision(decision_data: dict) -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        result = supabase.table("ai_decisions").insert(decision_data).execute()
        rows = result.data
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to save AI decision: {e}")
        return None


def get_latest_decision(symbol: str = None) -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        query = supabase.table("ai_decisions").select("*").order("created_at", desc=True).limit(1)
        if symbol:
            query = query.eq("symbol", symbol)
        result = query.execute()
        rows = result.data
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to get latest AI decision: {e}")
        return None


def get_decisions(symbol: str = None, limit: int = 10) -> list:
    supabase = get_supabase()
    if supabase is None:
        return []
    try:
        query = supabase.table("ai_decisions").select("*").order("created_at", desc=True).limit(limit)
        if symbol:
            query = query.eq("symbol", symbol)
        result = query.execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get AI decisions: {e}")
        return []


# ── risk_checks ──────────────────────────────────────────────────────────────

def save_risk_check(ai_decision_id: str, approved: bool, reason: str, checks: dict) -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        data = {
            "ai_decision_id": ai_decision_id,
            "approved": approved,
            "reason": reason,
            "checks": checks,
        }
        result = supabase.table("risk_checks").insert(data).execute()
        rows = result.data
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to save risk check: {e}")
        return None


# ── trades ───────────────────────────────────────────────────────────────────

def save_trade(trade_data: dict) -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        result = supabase.table("trades").insert(trade_data).execute()
        rows = result.data
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to save trade: {e}")
        return None


def update_trade_status(trade_id: str, status: str, close_price: float = None, profit: float = None) -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        updates = {"status": status}
        if status.upper() in ("CLOSED", "CANCELLED"):
            updates["closed_at"] = datetime.now(timezone.utc).isoformat()

        if close_price is not None:
            updates["close_price"] = close_price
        if profit is not None:
            updates["profit"] = profit

        result = (
            supabase.table("trades")
            .update(updates)
            .eq("id", trade_id)
            .execute()
        )
        rows = result.data
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to update trade status: {e}")
        return None


def get_open_trades(symbol: str = None) -> list:
    supabase = get_supabase()
    if supabase is None:
        return []
    try:
        query = supabase.table("trades").select("*").eq("status", "OPEN")
        if symbol:
            query = query.eq("symbol", symbol)
        result = query.execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get open trades: {e}")
        return []


def get_trade_by_mt5_ticket(ticket: int) -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        result = (
            supabase.table("trades")
            .select("*")
            .eq("mt5_ticket", ticket)
            .limit(1)
            .execute()
        )
        rows = result.data
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to get trade by MT5 ticket {ticket}: {e}")
        return None


# ── telegram_commands ────────────────────────────────────────────────────────

def log_telegram_command(chat_id: str, command: str, payload: dict = None, result: str = None) -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        data = {
            "chat_id": chat_id,
            "command": command,
            "payload": payload,
            "result": result,
        }
        res = supabase.table("telegram_commands").insert(data).execute()
        rows = res.data
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to log telegram command: {e}")
        return None


# ── bot_events ───────────────────────────────────────────────────────────────

def log_bot_event(event_type: str, message: str = None, payload: dict = None) -> dict | None:
    supabase = get_supabase()
    if supabase is None:
        return None
    try:
        data = {
            "event_type": event_type,
            "message": message,
            "payload": payload,
        }
        res = supabase.table("bot_events").insert(data).execute()
        rows = res.data
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        logger.error(f"Failed to log bot event: {e}")
        return None
