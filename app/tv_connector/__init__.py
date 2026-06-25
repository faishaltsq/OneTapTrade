from typing import Optional

from app.tv_connector.errors import (
    TVConnectionError,
    TVMCPProcessError,
    TVNotRunningError,
    TVToolError,
)
from app.tv_connector.mcp_client import TVMCPClient
from app.tv_connector.process_manager import TVMCPProcessManager
from app.tv_connector.tools import TVTools

_tv_process_manager: Optional[TVMCPProcessManager] = None
_tv_client: Optional[TVMCPClient] = None
_tv_tools: Optional[TVTools] = None
_tv_enabled: bool = False

__all__ = [
    "TVConnectionError",
    "TVMCPProcessError",
    "TVNotRunningError",
    "TVToolError",
    "start_tv_mcp",
    "stop_tv_mcp",
    "get_tv_tools",
    "is_tv_available",
]


async def start_tv_mcp() -> bool:
    from app.config import settings
    global _tv_process_manager, _tv_client, _tv_tools, _tv_enabled
    from app.logger import logger

    if not settings.tv_enabled:
        logger.info("TV integration disabled in config")
        return False

    _tv_process_manager = TVMCPProcessManager()
    if not await _tv_process_manager.start():
        logger.warning("TV MCP process failed to start — TV integration unavailable")
        _tv_enabled = False
        return False

    _tv_client = TVMCPClient(_tv_process_manager)
    if not await _tv_client.connect():
        logger.warning("TV MCP client failed to connect — TV integration unavailable")
        await _tv_process_manager.stop()
        _tv_enabled = False
        return False

    _tv_tools = TVTools(_tv_client)
    _tv_enabled = True
    logger.info("TV MCP integration active")
    return True


async def stop_tv_mcp() -> None:
    global _tv_client, _tv_process_manager, _tv_tools, _tv_enabled
    from app.logger import logger

    _tv_enabled = False
    _tv_tools = None

    if _tv_client:
        await _tv_client.disconnect()
        _tv_client = None

    if _tv_process_manager:
        await _tv_process_manager.stop()
        _tv_process_manager = None

    logger.info("TV MCP integration stopped")


def get_tv_tools() -> Optional[TVTools]:
    if not _tv_enabled or _tv_tools is None:
        return None
    if _tv_client is None or not _tv_client.is_connected:
        return None
    return _tv_tools


def is_tv_available() -> bool:
    if not _tv_enabled or _tv_tools is None:
        return False
    if _tv_client is None or not _tv_client.is_connected:
        return False
    return True
