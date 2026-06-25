import asyncio
import os
from typing import Optional

from app.config import settings
from app.logger import logger


class TVMCPProcessManager:
    def __init__(self):
        self._healthy: bool = False
        self._retry_count: int = 0
        self._max_retries: int = settings.tv_mcp_max_retries
        self._stop_requested: bool = False
        self._client_ref: Optional[object] = None

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def set_client(self, client: object) -> None:
        self._client_ref = client

    async def start(self) -> bool:
        server_path = os.path.abspath(settings.tv_mcp_server_path)
        if not os.path.exists(server_path):
            logger.error(f"TV MCP server not found at: {server_path}")
            return False
        logger.info("TV MCP process manager ready")
        self._retry_count = 0
        return True

    async def stop(self) -> None:
        self._stop_requested = True
        self._healthy = False
        self._client_ref = None
        logger.info("TV MCP process manager stopped")

    async def health_check(self) -> bool:
        return self._healthy

    def mark_healthy(self) -> None:
        self._healthy = True
        self._retry_count = 0

    def mark_unhealthy(self) -> None:
        self._healthy = False

    async def restart_if_needed(self) -> bool:
        if self._stop_requested:
            return False
        if self.is_healthy:
            return True
        if self._retry_count >= self._max_retries:
            logger.error(f"TV MCP max retries ({self._max_retries}) exhausted, degrading")
            return False

        self._retry_count += 1
        logger.warning(f"TV MCP restart attempt {self._retry_count}/{self._max_retries}")
        return False
