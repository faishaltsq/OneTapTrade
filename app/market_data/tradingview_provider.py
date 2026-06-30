import json
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any

import pandas as pd

from app.config import settings


class TradingViewMarketDataProvider:
    def __init__(self, runner=None):
        self._runner = runner or self._run_mcp

    def get_symbol_info(self, symbol: str) -> dict:
        return {"symbol": symbol, "source": "TRADINGVIEW", "point": 0.01}

    def get_latest_price(self, symbol: str) -> dict:
        candles = self.get_candles(symbol, "M5", 1)
        if candles.empty:
            raise ValueError(f"No TradingView price data for {symbol}")
        last = float(candles.iloc[-1]["close"])
        return {"bid": last, "ask": last, "last": last, "source": "TRADINGVIEW"}

    def get_candles(self, symbol: str, timeframe: str, count: int):
        self._runner(["symbol", symbol])
        self._runner(["timeframe", self._to_tv_timeframe(timeframe)])
        raw = self._runner(["ohlcv", "--count", str(count)])
        rows = self._extract_rows(raw)
        return self._to_dataframe(rows).tail(count).reset_index(drop=True)

    def health_check(self) -> bool:
        try:
            self._runner(["status"])
            return True
        except Exception:
            return False

    def capture_screenshot(self, symbol: str, timeframe: str = "M5", output_base: str | Path | None = None) -> Path:
        self._runner(["symbol", symbol])
        self._runner(["timeframe", self._to_tv_timeframe(timeframe)])
        base = self._screenshot_output_base(symbol, timeframe, output_base)
        result = self._runner(["screenshot", "--region", "chart", "--output", str(base)])
        if isinstance(result, dict):
            path = result.get("file_path") or result.get("path") or result.get("output")
            if path:
                return Path(path)
        return base.with_suffix(".png")

    def _run_mcp(self, cli_args: list[str]) -> Any:
        args = self._build_command(cli_args)
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=30, check=True)
        except FileNotFoundError as exc:
            raise RuntimeError(f"TradingView MCP command not found: {settings.tv_mcp_path}") from exc
        if not proc.stdout.strip():
            return []
        return json.loads(proc.stdout)

    @staticmethod
    def _screenshot_output_base(symbol: str, timeframe: str, output_base: str | Path | None) -> Path:
        if output_base is not None:
            base = Path(output_base)
            return base.with_suffix("") if base.suffix.lower() == ".png" else base

        safe_symbol = "".join(ch if ch.isalnum() else "_" for ch in symbol)
        output_dir = Path(tempfile.gettempdir()) / "onetaptrade"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"tradingview_{safe_symbol}_{timeframe}_{int(time.time())}"

    @staticmethod
    def _build_command(cli_args: list[str]) -> list[str]:
        configured = settings.tv_mcp_path
        path = Path(configured)
        if path.exists() and path.is_dir():
            cli = path / "src" / "cli" / "index.js"
            if cli.exists():
                return ["node", str(cli), *cli_args]
        if path.exists() and path.suffix.lower() == ".js":
            return ["node", str(path), *cli_args]
        return [configured, *cli_args]

    @staticmethod
    def _to_tv_timeframe(timeframe: str) -> str:
        mapping = {
            "D1": "D",
            "H4": "240",
            "H1": "60",
            "M15": "15",
            "M5": "5",
        }
        return mapping.get(timeframe.upper(), timeframe)

    @staticmethod
    def _extract_rows(raw: Any) -> list[dict]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            for key in ("candles", "data", "bars", "result"):
                value = raw.get(key)
                if isinstance(value, list):
                    return value
        raise ValueError("TradingView MCP response does not contain candle rows")

    @staticmethod
    def _to_dataframe(rows: list[dict]) -> pd.DataFrame:
        normalized = []
        for row in rows:
            normalized.append(
                {
                    "time": row.get("time") or row.get("timestamp") or row.get("datetime"),
                    "open": float(row.get("open") or row.get("o")),
                    "high": float(row.get("high") or row.get("h")),
                    "low": float(row.get("low") or row.get("l")),
                    "close": float(row.get("close") or row.get("c")),
                    "tick_volume": float(row.get("tick_volume") or row.get("volume") or row.get("v") or 0),
                }
            )
        return pd.DataFrame(normalized, columns=["time", "open", "high", "low", "close", "tick_volume"])
