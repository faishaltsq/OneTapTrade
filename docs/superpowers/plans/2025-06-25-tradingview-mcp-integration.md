# TradingView MCP Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate TradingView MCP server into OneTapTrade Python bot — bidireksional: TV data masuk AI prompt, bot kontrol TV chart.

**Architecture:** Node.js MCP server runs as managed asyncio subprocess inside Python. `app/tv_connector/` wraps MCP stdio protocol. 78 tools exposed as typed Python async functions. All TV calls wrapped in try/except — graceful degradation ke MT5-only on failure.

**Tech Stack:** Python 3.10+, asyncio, `mcp` Python SDK, `Pillow`, Node.js 18+ (for MCP server subprocess)

---

### Task 1: Clone TradingView MCP & install dependencies

**Files:**
- Create: `tradingview-mcp/` (cloned subdirectory)

- [ ] **Step 1: Clone repo as subdirectory**

```powershell
git clone https://github.com/tradesdontlie/tradingview-mcp.git tradingview-mcp
```

- [ ] **Step 2: Install Node dependencies**

```powershell
npm install
```

Run in: `tradingview-mcp/`

- [ ] **Step 3: Verify CLI works (requires TradingView Desktop running with debug port)**

```powershell
node src/cli/index.js status
```

Expected: JSON output showing connection status or "TradingView not found"

- [ ] **Step 4: Add `tradingview-mcp/` to `.gitignore` (if not already)**

Add line to `.gitignore`:
```
tradingview-mcp/
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "build: add tradingview-mcp subdirectory to gitignore"
```

---

### Task 2: Install Python dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add new Python dependencies to requirements.txt**

```python
mcp>=1.0.0
Pillow>=11.0.0
```

Append to: `requirements.txt`

- [ ] **Step 2: Install**

```powershell
pip install mcp Pillow
```

- [ ] **Step 3: Verify imports work**

```powershell
python -c "import mcp; from mcp import ClientSession; print('mcp OK')"
python -c "from PIL import Image; print('Pillow OK')"
```

Expected: "mcp OK", "Pillow OK"

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "build: add mcp and Pillow dependencies"
```

---

### Task 3: Add TV config to settings

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add TV settings fields to `Settings` class**

In `app/config.py`, add after `trading_loop_interval_seconds: int = 0`:

```python
    tv_enabled: bool = True
    tv_launch_on_startup: bool = False
    tv_debug_port: int = 9222
    tv_health_check_interval: int = 30
    tv_mcp_max_retries: int = 3
    tv_mcp_path: str = "tradingview-mcp"
```

- [ ] **Step 2: Add properties for TV config**

Append to `Settings` class, before `settings = Settings()`:

```python
    @property
    def tv_mcp_server_path(self) -> str:
        import os
        return os.path.join(self.tv_mcp_path, "src", "server.js")

    @property
    def tv_mcp_node_cmd(self) -> str:
        return "node"
```

- [ ] **Step 3: Add TV env vars to `.env.example`**

Append to `.env.example`:

```
TV_ENABLED=true
TV_LAUNCH_ON_STARTUP=false
TV_DEBUG_PORT=9222
TV_HEALTH_CHECK_INTERVAL=30
TV_MCP_MAX_RETRIES=3
TV_MCP_PATH=tradingview-mcp
```

- [ ] **Step 4: Commit**

```bash
git add app/config.py .env.example
git commit -m "feat: add TradingView config settings"
```

---

### Task 4: Create TV connector errors module

**Files:**
- Create: `app/tv_connector/__init__.py`
- Create: `app/tv_connector/errors.py`

- [ ] **Step 1: Create `app/tv_connector/__init__.py`**

```python
from app.tv_connector.errors import (
    TVConnectionError,
    TVNotRunningError,
    TVToolError,
    TVMCPProcessError,
)

__all__ = [
    "TVConnectionError",
    "TVNotRunningError",
    "TVToolError",
    "TVMCPProcessError",
]
```

- [ ] **Step 2: Create `app/tv_connector/errors.py`**

```python
class TVConnectionError(Exception):
    pass


class TVNotRunningError(TVConnectionError):
    pass


class TVToolError(TVConnectionError):
    pass


class TVMCPProcessError(TVConnectionError):
    pass
```

- [ ] **Step 3: Commit**

```bash
git add app/tv_connector/
git commit -m "feat: add tv_connector errors module"
```

---

### Task 5: Create TV connector schemas

**Files:**
- Create: `app/tv_connector/schemas.py`

- [ ] **Step 1: Write Pydantic models for TV data structures**

```python
from typing import Any, Optional

from pydantic import BaseModel


class ChartState(BaseModel):
    symbol: str = ""
    timeframe: str = ""
    chart_type: str = ""
    indicators: list[dict] = []


class IndicatorValue(BaseModel):
    name: str = ""
    id: str = ""
    values: dict[str, Any] = {}


class PriceLevel(BaseModel):
    price: float = 0.0
    text: str = ""
    color: str = ""


class TextAnnotation(BaseModel):
    text: str = ""
    price: Optional[float] = None
    color: str = ""


class TableData(BaseModel):
    name: str = ""
    rows: list[dict] = []
    headers: list[str] = []


class PriceZone(BaseModel):
    high: float = 0.0
    low: float = 0.0
    color: str = ""


class QuoteData(BaseModel):
    symbol: str = ""
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    change: float = 0.0
    change_percent: float = 0.0


class OHLCVData(BaseModel):
    symbol: str = ""
    timeframe: str = ""
    bars: list[dict] = []
    summary: dict = {}


class PaneInfo(BaseModel):
    index: int = 0
    symbol: str = ""
    active: bool = False


class Alert(BaseModel):
    id: str = ""
    condition: str = ""
    message: str = ""
    active: bool = True


class ReplayStatus(BaseModel):
    active: bool = False
    date: str = ""
    position: str = ""
    pnl: float = 0.0
```

- [ ] **Step 2: Commit**

```bash
git add app/tv_connector/schemas.py
git commit -m "feat: add TV connector Pydantic schemas"
```

---

### Task 6: Create MCP process manager

**Files:**
- Create: `app/tv_connector/process_manager.py`

- [ ] **Step 1: Write process manager**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add app/tv_connector/process_manager.py
git commit -m "feat: add TV MCP process manager"
```

---

### Task 7: Create MCP client (Python stdio bridge)

**Files:**
- Create: `app/tv_connector/mcp_client.py`

- [ ] **Step 1: Write MCP client that wraps stdio transport**

```python
import asyncio
import json
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
        self._read_stream = None
        self._write_stream = None
        self._connected: bool = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._session is not None

    async def connect(self) -> bool:
        if not self._pm.is_healthy:
            logger.warning("TV MCP process not healthy, cannot connect")
            return False

        try:
            import os
            server_params = StdioServerParameters(
                command=settings.tv_mcp_node_cmd,
                args=[os.path.abspath(settings.tv_mcp_server_path)],
                env=None,
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_response = await session.list_tools()
                    tool_names = [t.name for t in tools_response.tools]
                    logger.info(f"TV MCP connected — {len(tool_names)} tools available")
                    return True
        except asyncio.TimeoutError:
            logger.error("TV MCP connection timeout")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"TV MCP connection error: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        self._connected = False
        if self._session:
            try:
                self._session = None
            except Exception:
                pass
        self._read_stream = None
        self._write_stream = None

    async def _ensure_connected(self) -> None:
        if not self.is_connected:
            raise TVConnectionError("TV MCP client not connected")

    async def _call_tool(self, name: str, arguments: dict = None) -> Any:
        await self._ensure_connected()
        try:
            result = await self._session.call_tool(name, arguments or {})
            if result.isError:
                raise TVToolError(f"Tool '{name}' returned error: {result.content}")
            return result.content
        except TVToolError:
            raise
        except TVConnectionError:
            raise
        except Exception as e:
            raise TVToolError(f"Tool '{name}' call failed: {e}") from e
```

Wait — I realize the `mcp` SDK uses async context managers differently. Let me check the actual SDK pattern... The `stdio_client` and `ClientSession` need to stay alive for the duration of use. We can't use `async with` inside connect() because it closes immediately.

Let me restructure this properly. We need a persistent connection.

- [ ] **Step 1 (revised): Write persistent MCP client**

```python
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
        self._read = None
        self._write = None
        self._connected: bool = False
        self._tools: dict[str, dict] = {}

    @property
    def is_connected(self) -> bool:
        return self._connected and self._session is not None

    async def connect(self) -> bool:
        import os
        server_params = StdioServerParameters(
            command=settings.tv_mcp_node_cmd,
            args=[os.path.abspath(settings.tv_mcp_server_path)],
            env=None,
        )

        try:
            ctx = stdio_client(server_params)
            self._read, self._write = await ctx.__aenter__()
            self._session = ClientSession(self._read, self._write)
            await self._session.__aenter__()
            await self._session.initialize()
            tools_result = await self._session.list_tools()
            self._tools = {t.name: {"description": t.description, "inputSchema": t.inputSchema} for t in tools_result.tools}
            self._connected = True
            logger.info(f"TV MCP connected — {len(self._tools)} tools available")
            return True
        except asyncio.TimeoutError:
            logger.error("TV MCP connection timeout")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"TV MCP connection error: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        self._connected = False
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
                self._session = None
        except Exception as e:
            logger.debug(f"Error closing MCP session: {e}")
        try:
            if self._write:
                await self._write.aclose()
                self._write = None
        except Exception as e:
            logger.debug(f"Error closing write stream: {e}")
        self._read = None

    async def call_tool(self, name: str, arguments: dict = None) -> Any:
        if not self.is_connected:
            raise TVConnectionError("TV MCP client not connected")
        try:
            result = await self._session.call_tool(name, arguments or {})
            content = result.content
            if isinstance(result.content, list) and len(result.content) > 0:
                first = result.content[0]
                if hasattr(first, "text"):
                    text = first.text
                    try:
                        return json.loads(text)
                    except (json.JSONDecodeError, TypeError):
                        return text
                return first
            if hasattr(result.content, "text"):
                try:
                    return json.loads(result.content.text)
                except (json.JSONDecodeError, TypeError):
                    return result.content.text
            return result.content
        except TVConnectionError:
            raise
        except Exception as e:
            raise TVToolError(f"Tool '{name}' failed: {e}") from e

    async def try_call_tool(self, name: str, arguments: dict = None, timeout: float = 5.0) -> Optional[Any]:
        try:
            return await asyncio.wait_for(self.call_tool(name, arguments), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"TV tool '{name}' timed out after {timeout}s")
            return None
        except (TVConnectionError, TVToolError) as e:
            logger.warning(f"TV tool '{name}' failed: {e}")
            return None
        except Exception as e:
            logger.warning(f"TV tool '{name}' unexpected error: {e}")
            return None
```

- [ ] **Step 2: Commit**

```bash
git add app/tv_connector/mcp_client.py
git commit -m "feat: add TV MCP stdio client"
```

---

### Task 8: Create TV tool wrappers (core subset)

**Files:**
- Create: `app/tv_connector/tools.py`

- [ ] **Step 1: Write typed async tool wrappers**

```python
from typing import Any, Optional

from app.logger import logger
from app.tv_connector.mcp_client import TVMCPClient
from app.tv_connector.schemas import (
    Alert,
    ChartState,
    IndicatorValue,
    OHLCVData,
    PaneInfo,
    PriceLevel,
    PriceZone,
    QuoteData,
    ReplayStatus,
    TextAnnotation,
)


class TVTools:
    def __init__(self, client: TVMCPClient):
        self._client = client

    # ── connection ────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        result = await self._client.try_call_tool("tv_health_check")
        return isinstance(result, dict) and result.get("status") == "ok"

    async def status(self) -> dict:
        result = await self._client.try_call_tool("tv_status")
        return result if isinstance(result, dict) else {}

    # ── chart reading ─────────────────────────────────────────────────────

    async def get_chart_state(self) -> Optional[ChartState]:
        result = await self._client.try_call_tool("chart_get_state")
        if isinstance(result, dict):
            return ChartState(**result)
        return None

    async def get_study_values(self, study_filter: str = None) -> list[IndicatorValue]:
        args = {}
        if study_filter:
            args["study_filter"] = study_filter
        result = await self._client.try_call_tool("data_get_study_values", args)
        if isinstance(result, list):
            return [IndicatorValue(**item) for item in result]
        return []

    async def get_pine_lines(self, study_filter: str = None) -> list[PriceLevel]:
        args = {}
        if study_filter:
            args["study_filter"] = study_filter
        result = await self._client.try_call_tool("data_get_pine_lines", args)
        if isinstance(result, list):
            return [PriceLevel(**item) for item in result]
        return []

    async def get_pine_labels(self, study_filter: str = None) -> list[TextAnnotation]:
        args = {}
        if study_filter:
            args["study_filter"] = study_filter
        result = await self._client.try_call_tool("data_get_pine_labels", args)
        if isinstance(result, list):
            return [TextAnnotation(**item) for item in result]
        return []

    async def get_pine_tables(self, study_filter: str = None) -> list[dict]:
        args = {}
        if study_filter:
            args["study_filter"] = study_filter
        result = await self._client.try_call_tool("data_get_pine_tables", args)
        return result if isinstance(result, list) else []

    async def get_pine_boxes(self, study_filter: str = None) -> list[PriceZone]:
        args = {}
        if study_filter:
            args["study_filter"] = study_filter
        result = await self._client.try_call_tool("data_get_pine_boxes", args)
        if isinstance(result, list):
            return [PriceZone(**item) for item in result]
        return []

    async def get_quote(self) -> Optional[QuoteData]:
        result = await self._client.try_call_tool("quote_get")
        if isinstance(result, dict):
            return QuoteData(**result)
        return None

    async def get_ohlcv(self, symbol: str = None, timeframe: str = None, summary: bool = True) -> Optional[OHLCVData]:
        args = {"summary": summary}
        if symbol:
            args["symbol"] = symbol
        if timeframe:
            args["timeframe"] = timeframe
        result = await self._client.try_call_tool("data_get_ohlcv", args)
        if isinstance(result, dict):
            return OHLCVData(**result)
        return None

    # ── chart control ─────────────────────────────────────────────────────

    async def set_symbol(self, symbol: str) -> bool:
        result = await self._client.try_call_tool("chart_set_symbol", {"symbol": symbol})
        return result is not None

    async def set_timeframe(self, timeframe: str) -> bool:
        result = await self._client.try_call_tool("chart_set_timeframe", {"timeframe": timeframe})
        return result is not None

    async def set_chart_type(self, chart_type: str) -> bool:
        result = await self._client.try_call_tool("chart_set_type", {"type": chart_type})
        return result is not None

    async def manage_indicator(self, action: str, name: str, inputs: dict = None) -> bool:
        args = {"action": action, "name": name}
        if inputs:
            args["inputs"] = inputs
        result = await self._client.try_call_tool("chart_manage_indicator", args)
        return result is not None

    async def scroll_to_date(self, date_iso: str) -> bool:
        result = await self._client.try_call_tool("chart_scroll_to_date", {"date": date_iso})
        return result is not None

    # ── multi-pane ────────────────────────────────────────────────────────

    async def pane_list(self) -> list[PaneInfo]:
        result = await self._client.try_call_tool("pane_list")
        if isinstance(result, list):
            return [PaneInfo(**item) for item in result]
        return []

    async def pane_set_layout(self, layout: str) -> bool:
        result = await self._client.try_call_tool("pane_set_layout", {"layout": layout})
        return result is not None

    async def pane_set_symbol(self, pane_index: int, symbol: str) -> bool:
        result = await self._client.try_call_tool("pane_set_symbol", {"index": pane_index, "symbol": symbol})
        return result is not None

    # ── drawing ───────────────────────────────────────────────────────────

    async def draw_shape(self, shape_type: str, **kwargs) -> Optional[str]:
        args = {"type": shape_type, **kwargs}
        result = await self._client.try_call_tool("draw_shape", args)
        if isinstance(result, dict):
            return result.get("id")
        return None

    async def draw_horizontal_line(self, price: float, text: str = "", color: str = "#FF0000") -> Optional[str]:
        return await self.draw_shape("horizontal_line", price=price, text=text, color=color)

    async def draw_trend_line(self, x1: float, y1: float, x2: float, y2: float, color: str = "#FF0000") -> Optional[str]:
        return await self.draw_shape("trend_line", x1=x1, y1=y1, x2=x2, y2=y2, color=color)

    async def draw_text(self, price: float, text: str, color: str = "#FFFFFF") -> Optional[str]:
        return await self.draw_shape("text", price=price, text=text, color=color)

    async def draw_clear(self) -> bool:
        result = await self._client.try_call_tool("draw_clear")
        return result is not None

    # ── alerts ────────────────────────────────────────────────────────────

    async def alert_list(self) -> list[Alert]:
        result = await self._client.try_call_tool("alert_list")
        if isinstance(result, list):
            return [Alert(**item) for item in result]
        return []

    async def alert_create(self, condition: str, message: str = "") -> Optional[str]:
        result = await self._client.try_call_tool("alert_create", {"condition": condition, "message": message})
        if isinstance(result, dict):
            return result.get("id")
        return None

    # ── screenshot ────────────────────────────────────────────────────────

    async def capture_screenshot(self, region: str = "chart") -> Optional[bytes]:
        result = await self._client.try_call_tool("capture_screenshot", {"region": region})
        if isinstance(result, str):
            import base64
            try:
                return base64.b64decode(result)
            except Exception:
                return None
        if isinstance(result, dict) and "data" in result:
            import base64
            try:
                return base64.b64decode(result["data"])
            except Exception:
                return None
        return None

    # ── replay ────────────────────────────────────────────────────────────

    async def replay_start(self, date_iso: str) -> bool:
        result = await self._client.try_call_tool("replay_start", {"date": date_iso})
        return result is not None

    async def replay_step(self) -> Optional[ReplayStatus]:
        result = await self._client.try_call_tool("replay_step")
        if isinstance(result, dict):
            return ReplayStatus(**result)
        return None

    async def replay_stop(self) -> bool:
        result = await self._client.try_call_tool("replay_stop")
        return result is not None

    async def replay_status(self) -> Optional[ReplayStatus]:
        result = await self._client.try_call_tool("replay_status")
        if isinstance(result, dict):
            return ReplayStatus(**result)
        return None
```

- [ ] **Step 2: Commit**

```bash
git add app/tv_connector/tools.py
git commit -m "feat: add typed TV tool wrappers"
```

---

### Task 9: Update tv_connector __init__ with public API

**Files:**
- Modify: `app/tv_connector/__init__.py`

- [ ] **Step 1: Add public API exports and global instances**

```python
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
    return _tv_tools if _tv_enabled else None


def is_tv_available() -> bool:
    return _tv_enabled and _tv_tools is not None
```

- [ ] **Step 2: Commit**

```bash
git add app/tv_connector/__init__.py
git commit -m "feat: add tv_connector public API with lifecycle management"
```

---

### Task 10: Wire TV startup/shutdown into main.py lifespan

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add TV startup after MT5 init in `lifespan()`**

In `app/main.py`, after the MT5 init block (after `logger.info(f"MT5 connected: {mt5_ok}")`), add:

```python
    tv_ok = False
    try:
        from app.tv_connector import start_tv_mcp

        tv_ok = await start_tv_mcp()
        if tv_ok:
            logger.info("TradingView MCP integration active")
        else:
            logger.info("TradingView MCP integration unavailable — continuing without TV")
    except Exception as e:
        logger.warning(f"TradingView MCP init failed: {e} — continuing without TV")

    logger.info(f"TV connected: {tv_ok}")
```

- [ ] **Step 2: Add TV shutdown in lifespan cleanup**

Before `logger.info("AI Trading Executor shutdown complete")`, add:

```python
    try:
        from app.tv_connector import stop_tv_mcp

        await stop_tv_mcp()
    except Exception as e:
        logger.error(f"Error stopping TV MCP: {e}")
```

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: wire TV MCP lifecycle into main app lifespan"
```

---

### Task 11: Create TV data adapter for AI prompt

**Files:**
- Create: `app/ai_engine/tv_data_adapter.py`

- [ ] **Step 1: Write adapter that formats TV data for AI prompt**

```python
from typing import Any, Optional

from app.tv_connector.tools import TVTools


def build_tv_context(tools: Optional[TVTools], symbol: str) -> dict:
    if tools is None:
        return {}

    result: dict[str, Any] = {
        "tv_available": False,
        "tv_chart_context": {},
    }

    try:
        import asyncio

        async def _fetch():
            chart = await tools.get_chart_state()
            studies = await tools.get_study_values()
            lines = await tools.get_pine_lines()
            labels = await tools.get_pine_labels()
            tables = await tools.get_pine_tables()
            boxes = await tools.get_pine_boxes()
            return chart, studies, lines, labels, tables, boxes

        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            future = concurrent.futures.Future()

            async def _run():
                try:
                    result = await _fetch()
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)

            asyncio.ensure_future(_run())
            chart, studies, lines, labels, tables, boxes = None, [], [], [], [], []
        else:
            chart, studies, lines, labels, tables, boxes = loop.run_until_complete(_fetch())
    except Exception:
        return result

    if chart is None:
        return result

    result["tv_available"] = True

    ctx: dict[str, Any] = {
        "symbol": chart.symbol or symbol,
        "timeframe": chart.timeframe,
        "visible_indicators": [
            {"name": ind.get("name", ""), "id": ind.get("id", "")}
            for ind in (chart.indicators or [])
        ],
    }

    if studies:
        ctx["indicator_values"] = [
            {"name": s.name, "id": s.id, "values": s.values}
            for s in studies
        ]

    if lines:
        ctx["pine_levels"] = {
            "support": sorted(
                [l.price for l in lines if l.price > 0 and "support" in (l.text or "").lower()],
                reverse=True,
            )[:5],
            "resistance": sorted(
                [l.price for l in lines if l.price > 0 and "resistance" in (l.text or "").lower()],
            )[:5],
            "other_levels": [
                {"price": l.price, "text": l.text}
                for l in lines if l.price > 0
            ][:10],
        }

    if labels:
        ctx["pine_annotations"] = [
            {"text": lbl.text, "price": lbl.price}
            for lbl in labels[:20]
        ]

    if boxes:
        ctx["price_zones"] = [
            {"high": b.high, "low": b.low}
            for b in boxes[:10]
        ]

    if tables:
        ctx["data_tables"] = [
            {"name": t.get("name", ""), "rows": t.get("rows", [])[:10]}
            for t in tables[:5]
        ]

    result["tv_chart_context"] = ctx
    return result
```

Wait — the async-from-sync pattern is problematic here because `build_market_payload` in feature_builder is sync and is called from `generate_signal` which is also sync (wrapped in `asyncio.to_thread`). I need to handle this properly.

Let me rethink. The trading loop calls `generate_signal` which calls `get_ai_decision` which is sync. But TV tools need async. The cleanest approach is to collect TV data before calling `generate_signal` (in the trading loop's async context) and pass it as a parameter.

Let me restructure this. The TV data collection happens in `trading_loop._run_symbol()` (async), and the result is passed into the market payload builder and signal generation.

- [ ] **Step 1 (revised): Write adapter that just formats raw TV data**

```python
from typing import Any, Optional


def format_tv_context(chart: Optional[dict], studies: Optional[list], lines: Optional[list],
                      labels: Optional[list], tables: Optional[list], boxes: Optional[list],
                      symbol: str) -> dict:
    result: dict[str, Any] = {
        "tv_available": False,
        "tv_chart_context": {},
    }

    if chart is None:
        return result

    result["tv_available"] = True

    ctx: dict[str, Any] = {
        "symbol": chart.get("symbol", symbol),
        "timeframe": chart.get("timeframe", ""),
        "visible_indicators": [
            {"name": ind.get("name", ""), "id": ind.get("id", "")}
            for ind in (chart.get("indicators") or [])
        ],
    }

    if studies:
        ctx["indicator_values"] = [
            {"name": s.get("name", ""), "values": s.get("values", {})}
            for s in studies if isinstance(s, dict)
        ]

    if lines:
        all_price_lines = [l for l in lines if isinstance(l, dict) and l.get("price", 0) > 0]
        ctx["pine_levels"] = {
            "support": sorted(
                [l["price"] for l in all_price_lines if "support" in (l.get("text") or "").lower()],
                reverse=True,
            )[:5],
            "resistance": sorted(
                [l["price"] for l in all_price_lines if "resistance" in (l.get("text") or "").lower()],
            )[:5],
            "all_levels": [
                {"price": l["price"], "text": l.get("text", "")}
                for l in all_price_lines[:10]
            ],
        }

    if labels:
        ctx["pine_annotations"] = [
            {"text": lbl.get("text", ""), "price": lbl.get("price")}
            for lbl in labels if isinstance(lbl, dict)
        ][:20]

    if boxes:
        ctx["price_zones"] = [
            {"high": b.get("high", 0), "low": b.get("low", 0)}
            for b in boxes if isinstance(b, dict)
        ][:10]

    if tables:
        ctx["data_tables"] = [
            {"name": t.get("name", ""), "rows_count": len(t.get("rows") or [])}
            for t in tables if isinstance(t, dict)
        ][:5]

    result["tv_chart_context"] = ctx
    return result
```

- [ ] **Step 2: Commit**

```bash
git add app/ai_engine/tv_data_adapter.py
git commit -m "feat: add TV data adapter for AI prompt formatting"
```

---

### Task 12: Modify trading loop to fetch TV data per cycle

**Files:**
- Modify: `app/services/trading_loop.py`

- [ ] **Step 1: Add `_fetch_tv_data` async method to `TradingLoop`**

Add new method to `TradingLoop` class (before `run_once`):

```python
    async def _fetch_tv_data(self, symbol: str) -> dict:
        from app.tv_connector import get_tv_tools
        from app.logger import logger

        tools = get_tv_tools()
        if tools is None:
            return {}

        result = {"chart": None, "studies": [], "lines": [], "labels": [], "tables": [], "boxes": []}

        try:
            await tools.set_symbol(symbol)
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
```

- [ ] **Step 2: Integrate TV data into `_run_symbol`**

In `_run_symbol`, add TV data fetch before signal generation. Before `from app.services.signal_service import generate_signal`, add:

```python
        tv_data = await self._fetch_tv_data(symbol)
```

Then modify the signal generation call to pass TV data. Change:

```python
        signal_result = await asyncio.to_thread(generate_signal, symbol)
```

To:

```python
        signal_result = await asyncio.to_thread(generate_signal, symbol, tv_data or None)
```

- [ ] **Step 3: Update signal service to accept and forward TV data**

In `app/services/signal_service.py`, change the function signature:

Read the file first, then modify:

```python
def generate_signal(symbol: str, tv_data: dict = None) -> dict:
    ...
    market_payload = build_market_payload(...)

    # Add TV data to payload
    if tv_data:
        from app.ai_engine.tv_data_adapter import format_tv_context
        tv_ctx = format_tv_context(
            tv_data.get("chart"),
            tv_data.get("studies"),
            tv_data.get("lines"),
            tv_data.get("labels"),
            tv_data.get("tables"),
            tv_data.get("boxes"),
            symbol,
        )
        market_payload["tv_chart_context"] = tv_ctx.get("tv_chart_context", {})
        market_payload["tv_available"] = tv_ctx.get("tv_available", False)
    ...
```

- [ ] **Step 4: Commit**

```bash
git add app/services/trading_loop.py app/services/signal_service.py
git commit -m "feat: integrate TV data fetch into trading loop cycle"
```

---

### Task 13: Modify AI prompt builder to include TV section

**Files:**
- Modify: `app/ai_engine/prompt_builder.py`

- [ ] **Step 1: Add TV context section instructions to system prompts**

After the open position rules block in `_SMC_AI_BASE` (before "Return BUY when:"), add:

```python

TradingView chart data rules:
- The "tv_chart_context" section contains data read from TradingView charts.
- TV indicator values are additional confirmation — use them alongside MT5 indicators.
- TV Pine script levels (support/resistance) are high-priority zones for SL and TP placement.
- TV Pine annotations ("PDH", "Bias Long" etc.) provide market context from custom indicators.
- When TV data is available, cross-reference it with MT5 data for confluence.
- If TV shows conflicting data with MT5, weigh MT5 more heavily (execution broker data).
```

Do the same for `_AI_ONLY_BASE` (before "Stop Loss & Take Profit:").

- [ ] **Step 2: Update `build_user_prompt` to reference TV data**

After the strategy mode line, add TV availability note:

```python
    tv_available = market_payload.get("tv_available", False)
    tv_note = "\nTradingView data: AVAILABLE — cross-reference with MT5 data for confluence." if tv_available else "\nTradingView data: NOT AVAILABLE — use MT5 data only."
    
    return (
        "Analyze the following market data and return a trading decision.\n\n"
        f"Strategy mode: {mode_label}\n"
        f"Trading style: {style_label} ({settings.risk_profile})\n"
        f"Entry TF: {entry_tfs} | Hold: {hold}\n"
        f"Risk profile: {settings.risk_profile}\n"
        f"Minimum confidence: {settings.effective_min_confidence:.0%}\n"
        f"{tv_note}\n"
        f"Market data:\n{payload_json}"
    )
```

Wait — I need to modify `build_user_prompt` to accept the existing format. Let me just add the TV note line.

- [ ] **Step 1 (revised): Just add TV note to user prompt**

In `build_user_prompt`, find the return statement and insert the TV note:

```python
def build_user_prompt(market_payload: dict) -> str:
    payload_json = json.dumps(market_payload, indent=2)
    mode_label = "SMC+AI" if settings.strategy_mode == "SMC_AI" else "AI Only"
    style_label = settings.effective_style
    entry_tfs = "/".join(settings.effective_entry_tfs)
    hold = settings.effective_hold_time
    tv_available = market_payload.get("tv_available", False)
    tv_note = (
        "\nTradingView chart data: AVAILABLE — use pine levels, indicator values, and annotations as additional confluence.\n"
        if tv_available
        else ""
    )
    return (
        "Analyze the following market data and return a trading decision.\n\n"
        f"Strategy mode: {mode_label}\n"
        f"Trading style: {style_label} ({settings.risk_profile})\n"
        f"Entry TF: {entry_tfs} | Hold: {hold}\n"
        f"Risk profile: {settings.risk_profile}\n"
        f"Minimum confidence: {settings.effective_min_confidence:.0%}\n"
        f"{tv_note}"
        f"Market data:\n{payload_json}"
    )
```

- [ ] **Step 2: Commit**

```bash
git add app/ai_engine/prompt_builder.py
git commit -m "feat: add TV context note to AI prompts"
```

---

### Task 14: Create TV enrichment & confluence scoring

**Files:**
- Create: `app/analysis/tv_enrichment.py`

- [ ] **Step 1: Write confluence scoring**

```python
from typing import Any, Optional


def compute_confluence_score(market_payload: dict) -> dict:
    score = 0
    details: dict[str, Any] = {
        "total_score": 0,
        "max_score": 9,
        "breakdown": {},
        "profile_threshold": 0,
    }

    tv_ctx = market_payload.get("tv_chart_context", {})
    if not tv_ctx or not market_payload.get("tv_available"):
        return details

    # 1. D1 trend (0-3)
    major_trend = market_payload.get("major_trend", {})
    trend_bias = major_trend.get("bias", "")
    if trend_bias == "D1_BULLISH":
        score += 3
        details["breakdown"]["d1_trend"] = 3
    elif trend_bias == "D1_BEARISH":
        score += 3
        details["breakdown"]["d1_trend"] = 3
    elif trend_bias == "D1_RANGING":
        score += 1
        details["breakdown"]["d1_trend"] = 1
    else:
        details["breakdown"]["d1_trend"] = 0

    # 2. TV indicator agreement (0-2)
    tv_ind_values = tv_ctx.get("indicator_values", [])
    mt5_indicators = {}
    entry_tf = market_payload.get("entry_timeframe", {})
    if isinstance(entry_tf, dict):
        mt5_indicators = entry_tf.get("indicators", {})

    agreement_count = 0
    for tv_ind in tv_ind_values:
        name = tv_ind.get("name", "").lower()
        tv_vals = tv_ind.get("values", {})
        if "rsi" in name and "rsi_14" in mt5_indicators:
            mt5_rsi = mt5_indicators.get("rsi_14")
            tv_rsi = tv_vals.get("value") or tv_vals.get("rsi")
            if tv_rsi is not None and mt5_rsi is not None:
                if abs(float(tv_rsi) - float(mt5_rsi)) < 5:
                    agreement_count += 1
        elif "macd" in name:
            agreement_count += 1

    indicator_score = min(2, agreement_count)
    score += indicator_score
    details["breakdown"]["tv_indicator_agreement"] = indicator_score

    # 3. SMC zone match with TV levels (0-2)
    smc = market_payload.get("smc", {})
    ob = smc.get("order_blocks", {})
    demand_blocks = ob.get("demand", []) or []
    supply_blocks = ob.get("supply", []) or []
    pine_levels = tv_ctx.get("pine_levels", {})

    zone_match = 0
    if isinstance(pine_levels, dict):
        all_levels = (pine_levels.get("support") or []) + (pine_levels.get("resistance") or [])
        for level in all_levels:
            level_price = float(level) if not isinstance(level, dict) else float(level.get("price", 0))
            for blk in demand_blocks:
                if isinstance(blk, dict) and abs(level_price - float(blk.get("low", 0))) < 0.1:
                    zone_match = max(zone_match, 1)
                    break
            for blk in supply_blocks:
                if isinstance(blk, dict) and abs(level_price - float(blk.get("high", 0))) < 0.1:
                    zone_match = max(zone_match, 1)
                    break
        if zone_match > 0:
            zone_match = 2
    score += zone_match
    details["breakdown"]["smc_tv_zone_match"] = zone_match

    # 4. TV Pine level confluence (0-2)
    annotations = tv_ctx.get("pine_annotations", []) or []
    current_price = market_payload.get("current_price", {})
    mid = current_price.get("mid", 0)

    pine_score = 0
    for ann in annotations:
        text = ann.get("text", "").lower()
        ann_price = ann.get("price")
        if ann_price is not None and abs(ann_price - mid) / max(abs(mid), 0.01) < 0.02:
            pine_score = max(pine_score, 1)
        if any(kw in text for kw in ["bias", "trend", "signal", "bull", "bear"]):
            pine_score = max(pine_score, 2)
    score += pine_score
    details["breakdown"]["pine_annotation_confluence"] = pine_score

    details["total_score"] = score

    from app.config import settings
    thresholds = {"LOW": 7, "MEDIUM": 5, "HIGH": 3}
    details["profile_threshold"] = thresholds.get(settings.risk_profile, 5)
    details["passed"] = score >= details["profile_threshold"]

    return details
```

- [ ] **Step 2: Commit**

```bash
git add app/analysis/tv_enrichment.py
git commit -m "feat: add TV confluence scoring for market analysis"
```

---

### Task 15: Create TV levels module for dynamic SL/TP

**Files:**
- Create: `app/risk/tv_levels.py`

- [ ] **Step 1: Write dynamic SL/TP optimizer from TV levels**

```python
from typing import Optional


def optimize_sl_tp_from_tv(
    market_payload: dict,
    ai_sl: Optional[float] = None,
    ai_tp: Optional[float] = None,
    current_price: float = 0.0,
    decision: str = "BUY",
) -> dict:
    result = {
        "sl": ai_sl,
        "tp1": ai_tp,
        "sl_source": "ai",
        "tp_source": "ai",
        "tv_levels_available": False,
    }

    tv_ctx = market_payload.get("tv_chart_context", {})
    if not tv_ctx or not market_payload.get("tv_available"):
        return result

    pine_levels = tv_ctx.get("pine_levels", {})
    all_levels = []
    if isinstance(pine_levels, dict):
        for lv in (pine_levels.get("support") or []):
            all_levels.append({"price": float(lv) if not isinstance(lv, dict) else float(lv.get("price", 0)), "type": "support"})
        for lv in (pine_levels.get("resistance") or []):
            all_levels.append({"price": float(lv) if not isinstance(lv, dict) else float(lv.get("price", 0)), "type": "resistance"})
        for lv in (pine_levels.get("all_levels") or []):
            if isinstance(lv, dict):
                all_levels.append({"price": lv.get("price", 0), "type": lv.get("text", "")})

    if not all_levels:
        return result

    result["tv_levels_available"] = True

    if decision.upper() == "BUY":
        supports = [l for l in all_levels if l["price"] < current_price]
        resistances = [l for l in all_levels if l["price"] > current_price]
        if supports:
            nearest_support = max(supports, key=lambda x: x["price"])
            if ai_sl is None or nearest_support["price"] > ai_sl:
                result["sl"] = nearest_support["price"]
                result["sl_source"] = "tv_pine_level"
        if resistances:
            nearest_resistance = min(resistances, key=lambda x: x["price"])
            result["tp1"] = nearest_resistance["price"]
            result["tp_source"] = "tv_pine_level"

    elif decision.upper() == "SELL":
        supports = [l for l in all_levels if l["price"] < current_price]
        resistances = [l for l in all_levels if l["price"] > current_price]
        if resistances:
            nearest_resistance = min(resistances, key=lambda x: x["price"])
            if ai_sl is None or nearest_resistance["price"] < ai_sl:
                result["sl"] = nearest_resistance["price"]
                result["sl_source"] = "tv_pine_level"
        if supports:
            nearest_support = max(supports, key=lambda x: x["price"])
            result["tp1"] = nearest_support["price"]
            result["tp_source"] = "tv_pine_level"

    return result
```

- [ ] **Step 2: Commit**

```bash
git add app/risk/tv_levels.py
git commit -m "feat: add dynamic SL/TP optimization from TV chart levels"
```

---

### Task 16: Create TV autochart service

**Files:**
- Create: `app/services/tv_autochart_service.py`

- [ ] **Step 1: Write autochart service**

```python
from typing import Optional

from app.logger import logger


async def draw_signal_on_chart(
    symbol: str,
    decision: str,
    entry_price: Optional[float],
    stop_loss: Optional[float],
    take_profit: Optional[float],
) -> bool:
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        return False

    try:
        await tools.set_symbol(symbol)
        await tools.draw_clear()
    except Exception as e:
        logger.debug(f"TV autochart: clear failed: {e}")

    if decision.upper() == "BUY":
        entry_color = "#00FF00"
        sl_color = "#FF4444"
        tp_color = "#4488FF"
    elif decision.upper() == "SELL":
        entry_color = "#FF0000"
        sl_color = "#FF4444"
        tp_color = "#4488FF"
    else:
        return False

    try:
        if entry_price is not None and entry_price > 0:
            await tools.draw_horizontal_line(entry_price, f"Entry {decision}", entry_color)
    except Exception as e:
        logger.debug(f"TV autochart: draw entry failed: {e}")

    try:
        if stop_loss is not None and stop_loss > 0:
            await tools.draw_horizontal_line(stop_loss, f"SL", sl_color)
    except Exception as e:
        logger.debug(f"TV autochart: draw SL failed: {e}")

    try:
        if take_profit is not None and take_profit > 0:
            await tools.draw_horizontal_line(take_profit, f"TP1", tp_color)
    except Exception as e:
        logger.debug(f"TV autochart: draw TP failed: {e}")

    logger.info(f"TV autochart: drew {decision} levels for {symbol}")
    return True


async def draw_position_on_chart(
    symbol: str,
    side: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    pnl: float = 0.0,
) -> bool:
    return await draw_signal_on_chart(symbol, side, entry_price, stop_loss, take_profit)


async def draw_breakeven_update(symbol: str, new_sl: float, side: str) -> bool:
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        return False

    try:
        await tools.draw_text(new_sl, "SL→BE", "#FFAA00")
        logger.info(f"TV autochart: breakeven annotation at {new_sl} on {symbol}")
        return True
    except Exception as e:
        logger.debug(f"TV autochart: breakeven draw failed: {e}")
        return False
```

- [ ] **Step 2: Commit**

```bash
git add app/services/tv_autochart_service.py
git commit -m "feat: add TV autochart service for drawing signal levels"
```

---

### Task 17: Add autochart call after AI decisions in trading loop

**Files:**
- Modify: `app/services/trading_loop.py`

- [ ] **Step 1: Add autochart after signal generation in `_run_symbol`**

After signal generation success (after the `signal_result = await asyncio.to_thread(generate_signal, symbol, tv_data or None)` line), add autochart for BUY/SELL decisions:

```python
        if decision_str in ("BUY", "SELL") and tv_data:
            try:
                from app.services.tv_autochart_service import draw_signal_on_chart

                ep = getattr(ai_decision, "entry_plan", None)
                await draw_signal_on_chart(
                    symbol=symbol,
                    decision=decision_str,
                    entry_price=getattr(ep, "preferred_entry_price", None) if ep else None,
                    stop_loss=getattr(ep, "stop_loss", None) if ep else None,
                    take_profit=getattr(ep, "take_profit_1", None) if ep else None,
                )
            except Exception as e:
                logger.warning(f"TV autochart failed for {symbol}: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add app/services/trading_loop.py
git commit -m "feat: auto-draw signal levels on TradingView chart"
```

---

### Task 18: Add TV screenshot to Telegram signal messages

**Files:**
- Modify: `app/telegram_bot/bot.py`
- Modify: `app/telegram_bot/message_templates.py`

- [ ] **Step 1: Add screenshot capture function to bot.py**

Add new async function to `app/telegram_bot/bot.py`:

```python
async def capture_tv_screenshot() -> Optional[bytes]:
    try:
        from app.tv_connector import get_tv_tools

        tools = get_tv_tools()
        if tools is None:
            return None
        return await tools.capture_screenshot("chart")
    except Exception as e:
        logger.debug(f"TV screenshot capture failed: {e}")
        return None
```

- [ ] **Step 2: Modify `send_trade_signal` to include screenshot**

Find the `send_trade_signal` function in `app/telegram_bot/bot.py`. After sending the text message, add screenshot send:

```python
        from app.config import settings

        try:
            screenshot = await capture_tv_screenshot()
            if screenshot and chat_id:
                from io import BytesIO
                from telegram import InputFile

                img = BytesIO(screenshot)
                img.name = "chart.png"
                await _application.bot.send_photo(
                    chat_id=chat_id,
                    photo=InputFile(img),
                    caption=f"\U0001f4ca TradingView Chart — {symbol}",
                )
                logger.info(f"Sent TV chart screenshot to {chat_id}")
        except Exception as e:
            logger.warning(f"Failed to send TV screenshot: {e}")
```

- [ ] **Step 3: Add `/chart` command**

In `app/telegram_bot/commands.py`, add new command handler:

```python
async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    if chat_id != settings.telegram_allowed_chat_id:
        await update.message.reply_text("Unauthorized")
        return

    await update.message.reply_text("\U0001f4ca Capturing TradingView chart...")

    from app.tv_connector import get_tv_tools
    from app.telegram_bot.bot import capture_tv_screenshot

    tools = get_tv_tools()
    if tools is None:
        await update.message.reply_text("\u26a0\ufe0f TradingView not connected. Make sure TV Desktop is running with debug port 9222.")
        return

    screenshot = await capture_tv_screenshot()
    if screenshot:
        from io import BytesIO
        from telegram import InputFile

        img = BytesIO(screenshot)
        img.name = "chart.png"
        await update.message.reply_photo(
            photo=InputFile(img),
            caption="\U0001f4ca TradingView Chart",
        )
    else:
        await update.message.reply_text("\u26a0\ufe0f Failed to capture chart screenshot.")
```

Register in `get_command_handlers()`:

```python
handlers.append(CommandHandler("chart", chart_command))
```

- [ ] **Step 4: Update main menu keyboard to include chart button**

In `app/telegram_bot/message_templates.py`, in `build_main_menu_keyboard`, add chart button row:

```python
        [
            InlineKeyboardButton("\U0001f4f8 Chart", callback_data="MENU_CHART"),
        ],
```

- [ ] **Step 5: Add chart callback handler**

In `app/telegram_bot/callbacks.py`, handle `MENU_CHART` callback:

```python
if query.data == "MENU_CHART":
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        await context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text="\u26a0\ufe0f TradingView not connected.",
        )
        return
    await context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text="\U0001f4ca Capturing chart...",
    )
    await query.answer()
    await _send_chart(query.message.chat_id)
    return
```

Add helper:

```python
async def _send_chart(chat_id: str) -> None:
    from app.telegram_bot.bot import capture_tv_screenshot

    try:
        screenshot = await capture_tv_screenshot()
        if screenshot:
            from io import BytesIO
            from telegram import InputFile
            from app.telegram_bot.bot import _application

            img = BytesIO(screenshot)
            img.name = "chart.png"
            await _application.bot.send_photo(
                chat_id=chat_id,
                photo=InputFile(img),
                caption="\U0001f4ca TradingView Chart",
            )
        else:
            await _application.bot.send_message(
                chat_id=chat_id,
                text="\u26a0\ufe0f Failed to capture chart.",
            )
    except Exception as e:
        logger.warning(f"Send chart failed: {e}")
```

- [ ] **Step 6: Commit**

```bash
git add app/telegram_bot/bot.py app/telegram_bot/message_templates.py app/telegram_bot/commands.py app/telegram_bot/callbacks.py
git commit -m "feat: add TV chart screenshot to Telegram signals and /chart command"
```

---

### Task 19: Create alert bridge service

**Files:**
- Create: `app/services/alert_bridge.py`

- [ ] **Step 1: Write bidirectional alert bridge**

```python
from typing import Any, Optional

from app.logger import logger


async def sync_alerts_to_tv(symbol: str, entry_price: Optional[float],
                            stop_loss: Optional[float],
                            take_profit: Optional[float]) -> dict:
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        return {"synced": False, "reason": "TV not available"}

    created = []
    try:
        if entry_price is not None and entry_price > 0:
            alert_id = await tools.alert_create(
                condition="cross",
                message=f"{symbol} entry level at {entry_price}",
            )
            if alert_id:
                created.append({"level": "entry", "price": entry_price, "id": alert_id})

        if stop_loss is not None and stop_loss > 0:
            alert_id = await tools.alert_create(
                condition="crossing",
                message=f"{symbol} SL hit at {stop_loss}",
            )
            if alert_id:
                created.append({"level": "sl", "price": stop_loss, "id": alert_id})

        if take_profit is not None and take_profit > 0:
            alert_id = await tools.alert_create(
                condition="crossing",
                message=f"{symbol} TP hit at {take_profit}",
            )
            if alert_id:
                created.append({"level": "tp", "price": take_profit, "id": alert_id})

        logger.info(f"Alert bridge: synced {len(created)} alerts for {symbol}")
        return {"synced": True, "alerts": created}
    except Exception as e:
        logger.warning(f"Alert bridge sync failed: {e}")
        return {"synced": False, "reason": str(e)}


async def get_tv_alerts() -> list[dict]:
    from app.tv_connector import get_tv_tools

    tools = get_tv_tools()
    if tools is None:
        return []

    try:
        alerts = await tools.alert_list()
        return [a.model_dump() for a in alerts]
    except Exception as e:
        logger.debug(f"Alert bridge: get alerts failed: {e}")
        return []
```

- [ ] **Step 2: Commit**

```bash
git add app/services/alert_bridge.py
git commit -m "feat: add bidirectional TV alert bridge service"
```

---

### Task 20: Create TV replay service

**Files:**
- Create: `app/services/tv_replay_service.py`

- [ ] **Step 1: Write replay bridge**

```python
from datetime import datetime, timezone
from typing import Any, Optional

from app.logger import logger


class TVReplaySession:
    def __init__(self):
        self._active: bool = False
        self._start_date: str = ""
        self._steps: int = 0
        self._trades: list[dict] = []

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self, date_iso: str) -> bool:
        from app.tv_connector import get_tv_tools

        tools = get_tv_tools()
        if tools is None:
            return False

        try:
            ok = await tools.replay_start(date_iso)
            if ok:
                self._active = True
                self._start_date = date_iso
                self._steps = 0
                self._trades = []
                logger.info(f"TV replay started at {date_iso}")
            return ok
        except Exception as e:
            logger.warning(f"TV replay start failed: {e}")
            return False

    async def step(self) -> Optional[dict]:
        from app.tv_connector import get_tv_tools

        tools = get_tv_tools()
        if tools is None or not self._active:
            return None

        try:
            status = await tools.replay_step()
            if status:
                self._steps += 1
                return status.model_dump()
            return None
        except Exception as e:
            logger.debug(f"TV replay step failed: {e}")
            return None

    async def stop(self) -> dict:
        from app.tv_connector import get_tv_tools

        tools = get_tv_tools()
        if tools is not None:
            try:
                await tools.replay_stop()
            except Exception:
                pass

        self._active = False
        result = {
            "start_date": self._start_date,
            "steps": self._steps,
            "trades": len(self._trades),
        }
        logger.info(f"TV replay stopped: {result}")
        return result

    async def status(self) -> Optional[dict]:
        from app.tv_connector import get_tv_tools

        tools = get_tv_tools()
        if tools is None:
            return None

        try:
            s = await tools.replay_status()
            return s.model_dump() if s else None
        except Exception:
            return None


_replay_session: Optional[TVReplaySession] = None


def get_replay_session() -> TVReplaySession:
    global _replay_session
    if _replay_session is None:
        _replay_session = TVReplaySession()
    return _replay_session
```

- [ ] **Step 2: Commit**

```bash
git add app/services/tv_replay_service.py
git commit -m "feat: add TV replay bridge service"
```

---

### Task 21: Add TV status to bot status message

**Files:**
- Modify: `app/telegram_bot/message_templates.py`

- [ ] **Step 1: Add TV status line to `format_status_message`**

After the MT5 connected block in `format_status_message`, add:

```python
    from app.tv_connector import is_tv_available

    if is_tv_available():
        lines.append(f"\n\U0001f4ca <b>TradingView:</b> \u2705 Connected")
    else:
        lines.append(f"\n\U0001f4ca <b>TradingView:</b> \u274c Not Connected")
```

- [ ] **Step 2: Commit**

```bash
git add app/telegram_bot/message_templates.py
git commit -m "feat: show TV connection status in Telegram status message"
```

---

### Task 22: Run existing tests to verify no regression

**Files:**
- Test: `tests/` (existing)

- [ ] **Step 1: Run full test suite**

```powershell
pytest tests/ -v
```

Expected: all existing tests still pass. TV integration is additive — no breaking changes to core logic.

- [ ] **Step 2: Fix any failures**

If any test fails due to new imports or config changes, fix them. Common issues:
- Import errors from new `app/tv_connector/` module if `mcp` package not installed → install it
- Config validation error from new `tv_enabled` field → add default values

- [ ] **Step 3: Commit any fixes**

```bash
git add .
git commit -m "fix: resolve test regressions from TV integration"
```

---

### Task 23: Add TV connector tests

**Files:**
- Create: `tests/test_tv_connector.py`

- [ ] **Step 1: Write unit tests for TV schemas**

```python
import pytest
from app.tv_connector.schemas import (
    ChartState, IndicatorValue, PriceLevel, QuoteData, PaneInfo, Alert, ReplayStatus
)


class TestTVSchemas:
    def test_chart_state_defaults(self):
        cs = ChartState()
        assert cs.symbol == ""
        assert cs.timeframe == ""
        assert cs.indicators == []

    def test_chart_state_with_data(self):
        cs = ChartState(symbol="XAUUSD", timeframe="M5")
        assert cs.symbol == "XAUUSD"
        assert cs.timeframe == "M5"

    def test_indicator_value(self):
        iv = IndicatorValue(name="RSI", id="study_1", values={"value": 65.5})
        assert iv.name == "RSI"
        assert iv.values["value"] == 65.5

    def test_price_level(self):
        pl = PriceLevel(price=2150.00, text="Support", color="#FF0000")
        assert pl.price == 2150.00

    def test_quote_data(self):
        q = QuoteData(symbol="XAUUSD", bid=2150.00, ask=2150.50, last=2150.25)
        assert q.bid == 2150.00

    def test_pane_info(self):
        pi = PaneInfo(index=0, symbol="XAUUSD", active=True)
        assert pi.active is True

    def test_alert(self):
        a = Alert(id="alert_1", condition="cross", message="Price alert", active=True)
        assert a.id == "alert_1"

    def test_replay_status(self):
        rs = ReplayStatus(active=True, date="2025-01-15", position="BUY", pnl=100.0)
        assert rs.active is True
```

- [ ] **Step 2: Write test for errors**

```python
from app.tv_connector.errors import TVConnectionError, TVNotRunningError, TVToolError


def test_tv_connection_error():
    with pytest.raises(TVConnectionError):
        raise TVConnectionError("test")

def test_tv_not_running_error():
    with pytest.raises(TVConnectionError):
        raise TVNotRunningError("test")

def test_tv_tool_error():
    with pytest.raises(TVConnectionError):
        raise TVToolError("test")
```

- [ ] **Step 3: Write test for TV data adapter**

```python
from app.ai_engine.tv_data_adapter import format_tv_context


def test_format_tv_context_empty():
    result = format_tv_context(None, [], [], [], [], [], "XAUUSD")
    assert result["tv_available"] is False
    assert result["tv_chart_context"] == {}


def test_format_tv_context_with_chart():
    chart = {"symbol": "XAUUSD", "timeframe": "M5", "indicators": []}
    result = format_tv_context(chart, [], [], [], [], [], "XAUUSD")
    assert result["tv_available"] is True
    assert result["tv_chart_context"]["symbol"] == "XAUUSD"


def test_format_tv_context_with_levels():
    chart = {"symbol": "XAUUSD", "timeframe": "M5", "indicators": []}
    lines = [
        {"price": 2150.0, "text": "Support level", "color": "#00FF00"},
        {"price": 2160.0, "text": "Resistance zone", "color": "#FF0000"},
    ]
    result = format_tv_context(chart, [], lines, [], [], [], "XAUUSD")
    assert result["tv_available"] is True
    assert len(result["tv_chart_context"]["pine_levels"]["support"]) > 0
    assert len(result["tv_chart_context"]["pine_levels"]["resistance"]) > 0
```

- [ ] **Step 4: Write test for confluence scoring**

```python
from app.analysis.tv_enrichment import compute_confluence_score


def test_confluence_score_no_tv():
    payload = {"tv_available": False}
    result = compute_confluence_score(payload)
    assert result["total_score"] == 0


def test_confluence_score_with_trend():
    payload = {
        "tv_available": True,
        "tv_chart_context": {},
        "major_trend": {"bias": "D1_BULLISH", "allowed_directions": ["BUY"]},
    }
    result = compute_confluence_score(payload)
    assert result["breakdown"]["d1_trend"] == 3
    assert result["total_score"] >= 3
```

- [ ] **Step 5: Write test for TV level optimizer**

```python
from app.risk.tv_levels import optimize_sl_tp_from_tv


def test_optimize_sl_tp_no_tv():
    result = optimize_sl_tp_from_tv({"tv_available": False}, 2150.0, 2170.0, 2155.0, "BUY")
    assert result["sl"] == 2150.0
    assert result["tp1"] == 2170.0
    assert result["sl_source"] == "ai"


def test_optimize_sl_tp_with_tv_buy():
    payload = {
        "tv_available": True,
        "tv_chart_context": {
            "pine_levels": {
                "support": [2152.0, 2145.0],
                "resistance": [2160.0, 2168.0],
            }
        },
    }
    result = optimize_sl_tp_from_tv(payload, 2148.0, 2170.0, 2157.0, "BUY")
    assert result["tv_levels_available"] is True
    assert result["sl"] == 2152.0 or result["sl"] == 2148.0


def test_optimize_sl_tp_with_tv_sell():
    payload = {
        "tv_available": True,
        "tv_chart_context": {
            "pine_levels": {
                "support": [2152.0, 2145.0],
                "resistance": [2160.0, 2168.0],
            }
        },
    }
    result = optimize_sl_tp_from_tv(payload, 2165.0, 2145.0, 2157.0, "SELL")
    assert result["tv_levels_available"] is True
```

- [ ] **Step 6: Run new tests**

```powershell
pytest tests/test_tv_connector.py -v
```

Expected: all new tests pass.

- [ ] **Step 7: Commit**

```bash
git add tests/test_tv_connector.py
git commit -m "test: add TV connector, adapter, enrichment, and levels tests"
```

---

### Task 24: Final integration test — run full test suite

- [ ] **Step 1: Run all tests**

```powershell
pytest -v
```

Expected: 113 existing + ~15 new = ~128 tests, all passing.

- [ ] **Step 2: Run lint check (if available)**

```powershell
pytest --version
python -c "from app.tv_connector import start_tv_mcp, stop_tv_mcp, is_tv_available; print('all imports OK')"
```

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "feat: complete TradingView MCP integration with Telegram chart support"
```
