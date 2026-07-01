import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from app.config import settings


def _mcp_dir() -> Path:
    path = Path(settings.tradingview_mcp_dir)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _cli_path() -> Path:
    return _mcp_dir() / "src" / "cli" / "index.js"


async def run_tv_command(*args: str) -> dict[str, Any]:
    cli_path = _cli_path()
    if not cli_path.exists():
        return {
            "success": False,
            "error": f"TradingView MCP CLI not found: {cli_path}",
            "command": list(args),
        }

    env = os.environ.copy()
    env["TRADINGVIEW_CDP_PORT"] = str(settings.tradingview_cdp_port)
    if settings.tradingview_app_path:
        env["TRADINGVIEW_APP_PATH"] = settings.tradingview_app_path

    process = await asyncio.create_subprocess_exec(
        settings.tradingview_mcp_node,
        str(cli_path),
        *args,
        cwd=str(_mcp_dir()),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=settings.tradingview_mcp_timeout_seconds,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return {
            "success": False,
            "error": f"TradingView MCP command timed out after {settings.tradingview_mcp_timeout_seconds}s",
            "command": list(args),
        }

    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()
    payload_text = stdout_text or stderr_text

    try:
        result = json.loads(payload_text) if payload_text else {}
    except json.JSONDecodeError:
        result = {"output": stdout_text, "stderr": stderr_text}

    if process.returncode != 0:
        if isinstance(result, dict):
            result.setdefault("success", False)
            result.setdefault("error", stderr_text or stdout_text or "TradingView MCP command failed")
            result["command"] = list(args)
            return result
        return {"success": False, "error": str(result), "command": list(args)}

    if isinstance(result, dict):
        return result
    return {"success": True, "output": result}


async def launch_tradingview() -> dict[str, Any]:
    if not settings.tradingview_app_path:
        return {"success": False, "error": "TRADINGVIEW_APP_PATH is not configured"}

    app_path = Path(settings.tradingview_app_path)
    if not app_path.exists():
        return {"success": False, "error": f"TradingView app not found: {app_path}"}

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/IM", "TradingView.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            await asyncio.sleep(2)

        subprocess.Popen(
            [str(app_path), f"--remote-debugging-port={settings.tradingview_cdp_port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        return {"success": False, "error": f"Failed to launch TradingView: {e}"}

    for _ in range(12):
        await asyncio.sleep(1)
        status = await run_tv_command("status")
        if status.get("success"):
            return {"success": True, "status": status}

    return {
        "success": False,
        "error": "TradingView launched but CDP did not become ready",
        "app_path": str(app_path),
        "cdp_port": settings.tradingview_cdp_port,
    }


async def ensure_tradingview_ready() -> dict[str, Any]:
    status = await run_tv_command("status")
    if status.get("success") and status.get("api_available"):
        return {"success": True, "launched": False, "status": status}

    launch = await launch_tradingview()
    if not launch.get("success"):
        return {"success": False, "launched": False, "status": status, "launch": launch}

    ready_status = launch.get("status") or await wait_for_chart_api()
    if ready_status.get("success") and ready_status.get("api_available"):
        return {"success": True, "launched": True, "status": ready_status}

    ready_status = await wait_for_chart_api()
    return {
        "success": bool(ready_status.get("success") and ready_status.get("api_available")),
        "launched": True,
        "status": ready_status,
    }


async def wait_for_chart_api(max_attempts: int = 30) -> dict[str, Any]:
    last_status: dict[str, Any] = {"success": False, "error": "Chart API not checked"}
    for _ in range(max_attempts):
        last_status = await run_tv_command("status")
        if last_status.get("success") and last_status.get("api_available"):
            return last_status
        await asyncio.sleep(1)
    return last_status


def _symbol_matches(current: str | None, target: str | None) -> bool:
    if not current or not target:
        return False
    current_upper = current.upper()
    target_upper = target.upper()
    return current_upper == target_upper or current_upper.split(":")[-1] == target_upper.split(":")[-1]


async def set_symbol_and_wait(symbol: str) -> dict[str, Any]:
    last_command: dict[str, Any] | None = None
    last_state: dict[str, Any] | None = None
    for _ in range(4):
        last_command = await run_tv_command("symbol", symbol)
        await asyncio.sleep(2)
        for _ in range(8):
            last_state = await run_tv_command("state")
            if last_state.get("success") and _symbol_matches(last_state.get("symbol"), symbol):
                return {
                    "success": True,
                    "symbol": symbol,
                    "chart_ready": True,
                    "command": last_command,
                    "state": last_state,
                }
            await asyncio.sleep(1)

    return {
        "success": False,
        "symbol": symbol,
        "chart_ready": False,
        "command": last_command,
        "state": last_state,
    }


async def set_timeframe_and_wait(timeframe: str) -> dict[str, Any]:
    last_command: dict[str, Any] | None = None
    last_state: dict[str, Any] | None = None
    for _ in range(3):
        last_command = await run_tv_command("timeframe", timeframe)
        await asyncio.sleep(1)
        for _ in range(6):
            last_state = await run_tv_command("state")
            if last_state.get("success") and str(last_state.get("resolution")) == str(timeframe):
                return {
                    "success": True,
                    "timeframe": timeframe,
                    "chart_ready": True,
                    "command": last_command,
                    "state": last_state,
                }
            await asyncio.sleep(1)

    return {
        "success": False,
        "timeframe": timeframe,
        "chart_ready": False,
        "command": last_command,
        "state": last_state,
    }


async def get_chart_context(
    include_screenshot: bool = True,
    include_indicators: bool = True,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict[str, Any]:
    initial_status = await run_tv_command("status")
    if not initial_status.get("success"):
        ensure = await ensure_tradingview_ready()
        if not ensure.get("success"):
            return {"success": False, "status": initial_status, "launch": ensure.get("launch")}
        initial_status = ensure.get("status") or await run_tv_command("status")

    if not initial_status.get("api_available"):
        initial_status = await wait_for_chart_api()
        if not initial_status.get("success"):
            return {"success": False, "status": initial_status}

    chart_updates: dict[str, Any] = {}
    if symbol:
        chart_updates["symbol"] = await set_symbol_and_wait(symbol)
    if timeframe:
        chart_updates["timeframe"] = await set_timeframe_and_wait(timeframe)

    status = await run_tv_command("status") if chart_updates else initial_status

    context: dict[str, Any] = {
        "success": True,
        "initial_status": initial_status,
        "status": status,
        "chart_updates": chart_updates,
        "state": await run_tv_command("state"),
        "quote": await run_tv_command("quote"),
        "ohlcv_summary": await run_tv_command("ohlcv", "--summary"),
    }

    if include_indicators:
        context["indicator_values"] = await run_tv_command("values")
        if settings.tradingview_ema_bar_count > 0:
            context["ohlcv_bars"] = await run_tv_command("ohlcv", "--count", str(settings.tradingview_ema_bar_count))
        if settings.tradingview_smc_study_filter:
            smc_filter = settings.tradingview_smc_study_filter
            context["smc_lines"] = await run_tv_command("data", "lines", "-f", smc_filter)
            context["smc_labels"] = await run_tv_command("data", "labels", "-f", smc_filter)
            context["smc_boxes"] = await run_tv_command("data", "boxes", "-f", smc_filter)

    if include_screenshot:
        context["screenshot"] = await run_tv_command("screenshot", "-r", "chart")

    return context
