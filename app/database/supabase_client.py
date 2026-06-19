from supabase import create_client, Client
from app.config import settings
from app.logger import logger

_client: Client | None = None


def get_supabase() -> Client | None:
    global _client
    if _client is not None:
        return _client

    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.warning("Supabase URL or service role key not configured — database unavailable")
        return None

    try:
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        logger.info("Supabase client connected")
        return _client
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None


def supabase_available() -> bool:
    return get_supabase() is not None
