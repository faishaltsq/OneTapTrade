import asyncio
import json
import os
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings
from app.logger import logger
from app.tv_connector.errors import TVConnectionError, TVToolError
from app.tv_connector.process_manager import TVMCPProcessManager


class TVMCPClient:
    def __init__(self, process_manager: TVMCPProcessManager):
        self._pm: TVMCPProcessManager = process_manager
        self._session: Optional[ClientSession] = None
        self._stdio_ctx = None
        self._read = None
        self._write = None
        self._connected: bool = False
        self._tools: dict[str, dict] = {}

    @property
    def is_connected(self) -> bool:
        return self._connected and self._session is not None

    async def connect(self) -> bool:
        server_params = StdioServerParameters(
            command=settings.tv_mcp_node_cmd,
            args=[os.path.abspath(settings.tv_mcp_server_path)],
            env=None,
        )

        try:
            self._stdio_ctx = stdio_client(server_params)
            self._read, self._write = await self._stdio_ctx.__aenter__()
            self._session = ClientSession(self._read, self._write)
            await self._session.__aenter__()
            await self._session.initialize()
            tools_result = await self._session.list_tools()
            self._tools = {t.name: {"description": t.description, "inputSchema": t.inputSchema} for t in tools_result.tools}
            self._connected = True
            self._pm.mark_healthy()
            logger.info(f"TV MCP connected — {len(self._tools)} tools available")
            return True
        except asyncio.TimeoutError:
            logger.error("TV MCP connection timeout")
            self._connected = False
            await self._cleanup_resources()
            return False
        except Exception as e:
            logger.error(f"TV MCP connection error: {e}")
            self._connected = False
            await self._cleanup_resources()
            return False

    async def disconnect(self) -> None:
        self._connected = False
        self._pm.mark_unhealthy()
        await self._cleanup_resources()

    async def _cleanup_resources(self) -> None:
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error closing MCP session: {e}")
            self._session = None
        self._read = None
        self._write = None
        if self._stdio_ctx:
            try:
                await self._stdio_ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error closing stdio context: {e}")
            self._stdio_ctx = None

    async def call_tool(self, name: str, arguments: dict = None) -> Any:
        if not self.is_connected:
            raise TVConnectionError("TV MCP client not connected")
        try:
            result = await self._session.call_tool(name, arguments or {})
            if getattr(result, "isError", False):
                error_text = ""
                if isinstance(result.content, list) and len(result.content) > 0:
                    first = result.content[0]
                    if hasattr(first, "text"):
                        raw = first.text
                        import json as _json
                        try:
                            parsed = _json.loads(raw)
                            error_text = parsed.get("error", raw[:200])
                        except Exception:
                            error_text = raw[:200]
                    else:
                        error_text = str(first)[:200]
                raise TVToolError(error_text)
            content = result.content
            if isinstance(content, list) and len(content) > 0:
                first = content[0]
                if hasattr(first, "text"):
                    text = first.text
                    try:
                        return json.loads(text)
                    except (json.JSONDecodeError, TypeError):
                        return text
                return str(first)
            if hasattr(content, "text"):
                try:
                    return json.loads(content.text)
                except (json.JSONDecodeError, TypeError):
                    return content.text
            if hasattr(result, "structuredContent") and result.structuredContent is not None:
                return result.structuredContent
            return content
        except TVConnectionError:
            raise
        except TVToolError:
            raise
        except Exception as e:
            raise TVToolError(f"Tool '{name}' failed: {type(e).__name__}: {e}") from e

    async def try_call_tool(self, name: str, arguments: dict = None, timeout: float = 5.0) -> Optional[Any]:
        try:
            return await asyncio.wait_for(self.call_tool(name, arguments), timeout=timeout)
        except asyncio.TimeoutError:
            logger.debug(f"TV tool '{name}' timed out after {timeout}s")
            return None
        except (TVConnectionError, TVToolError) as e:
            msg = str(e)[:120]
            logger.debug(f"TV tool '{name}': {msg}")
            return None
        except Exception as e:
            logger.debug(f"TV tool '{name}' unexpected error: {type(e).__name__}: {e}")
            return None
