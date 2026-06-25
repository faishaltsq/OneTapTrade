import asyncio
import os
from typing import Optional

from app.config import settings
from app.logger import logger
from app.tv_connector.errors import TVMCPProcessError


class TVMCPProcessManager:
    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._healthy: bool = False
        self._retry_count: int = 0
        self._max_retries: int = settings.tv_mcp_max_retries
        self._stop_requested: bool = False

    @property
    def is_healthy(self) -> bool:
        return self._healthy and self._process is not None and self._process.returncode is None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> bool:
        server_path = os.path.abspath(settings.tv_mcp_server_path)
        if not os.path.exists(server_path):
            logger.error(f"TV MCP server not found at: {server_path}")
            return False

        logger.info(f"Starting TV MCP server: node {server_path}")
        try:
            self._process = await asyncio.create_subprocess_exec(
                settings.tv_mcp_node_cmd,
                server_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.sleep(1.0)
            if self._process.returncode is not None:
                stderr = await self._process.stderr.read()
                logger.error(f"TV MCP process exited early: {stderr.decode(errors='replace')[:500]}")
                self._healthy = False
                return False

            self._healthy = True
            self._retry_count = 0
            logger.info("TV MCP server process started")
            return True
        except Exception as e:
            logger.error(f"Failed to start TV MCP server: {e}")
            self._healthy = False
            return False

    async def stop(self) -> None:
        self._stop_requested = True
        self._healthy = False
        if self._process is None:
            return

        logger.info("Stopping TV MCP server process")
        try:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("TV MCP process did not terminate, killing")
                self._process.kill()
                await self._process.wait()
        except Exception as e:
            logger.error(f"Error stopping TV MCP process: {e}")
        self._process = None
        logger.info("TV MCP server process stopped")

    async def health_check(self) -> bool:
        if not self.is_running:
            return False
        try:
            self._healthy = self._process.returncode is None
            return self._healthy
        except Exception:
            self._healthy = False
            return False

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
        await self.stop()
        await asyncio.sleep(2.0)
        return await self.start()
