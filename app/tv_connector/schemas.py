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
