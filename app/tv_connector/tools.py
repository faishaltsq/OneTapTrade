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

    async def draw_shape(self, shape: str, point: dict, point2: dict = None,
                         overrides: dict = None, text: str = None) -> Optional[dict]:
        args = {"shape": shape, "point": point}
        if point2:
            args["point2"] = point2
        if overrides:
            import json
            args["overrides"] = json.dumps(overrides)
        if text:
            args["text"] = text
        result = await self._client.try_call_tool("draw_shape", args)
        if isinstance(result, dict):
            return result
        return None

    async def draw_horizontal_line(self, price: float, text: str = "", color: str = "#FF0000") -> Optional[dict]:
        import time
        overrides = {"linecolor": color}
        if text:
            overrides["text"] = text
        return await self.draw_shape(
            shape="horizontal_line",
            point={"time": int(time.time()), "price": price},
            overrides=overrides,
        )

    async def draw_trend_line(self, time1: int, price1: float, time2: int, price2: float,
                              color: str = "#FF0000") -> Optional[dict]:
        overrides = {"linecolor": color}
        return await self.draw_shape(
            shape="trend_line",
            point={"time": time1, "price": price1},
            point2={"time": time2, "price": price2},
            overrides=overrides,
        )

    async def draw_text_on_chart(self, price: float, text: str, color: str = "#FFFFFF") -> Optional[dict]:
        import time
        overrides = {"textcolor": color}
        return await self.draw_shape(
            shape="text",
            point={"time": int(time.time()), "price": price},
            text=text,
            overrides=overrides,
        )

    async def draw_clear(self) -> bool:
        result = await self._client.try_call_tool("draw_clear", {})
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
        if isinstance(result, dict):
            file_path = result.get("file_path") or result.get("path") or result.get("file")
            if file_path:
                import os
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "rb") as f:
                            return f.read()
                    except Exception as e:
                        logger.debug(f"Failed to read screenshot file: {e}")
                        return None
            if "data" in result:
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
