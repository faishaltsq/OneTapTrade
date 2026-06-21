from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class Decision(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class ConfidenceLabel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    BREAKOUT = "BREAKOUT"
    REVERSAL = "REVERSAL"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNCLEAR = "UNCLEAR"


class TimeframeBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNCLEAR = "UNCLEAR"


class EntryType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    WAIT_FOR_CONFIRMATION = "WAIT_FOR_CONFIRMATION"
    NONE = "NONE"


class EntryPlan(BaseModel):
    entry_type: EntryType = EntryType.NONE
    entry_area_low: Optional[float] = None
    entry_area_high: Optional[float] = None
    preferred_entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    risk_reward_to_tp1: Optional[float] = None
    risk_reward_to_tp2: Optional[float] = None


class ExecutionPermission(BaseModel):
    ai_allows_execution: bool = False
    reason: str = ""


class RiskNotes(BaseModel):
    main_risk: str = ""
    invalidation_condition: str = ""
    conditions_to_avoid_trade: List[str] = []


class AIDecisionResponse(BaseModel):
    decision: Decision
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_label: ConfidenceLabel
    market_regime: MarketRegime
    higher_timeframe_bias: TimeframeBias
    entry_timeframe_bias: TimeframeBias
    main_reason: str = ""
    entry_plan: EntryPlan = EntryPlan()
    execution_permission: ExecutionPermission = ExecutionPermission()
    risk_notes: RiskNotes = RiskNotes()
    final_comment: str = ""
    strategy_mode: Optional[str] = None
    trading_style: Optional[str] = None


class AIDecisionPartial(BaseModel):
    decision: Optional[Decision] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence_label: Optional[ConfidenceLabel] = None
    market_regime: Optional[MarketRegime] = None
    higher_timeframe_bias: Optional[TimeframeBias] = None
    entry_timeframe_bias: Optional[TimeframeBias] = None
    main_reason: Optional[str] = None
    entry_plan: Optional[EntryPlan] = None
    execution_permission: Optional[ExecutionPermission] = None
    risk_notes: Optional[RiskNotes] = None
    final_comment: Optional[str] = None


class DecisionValidationError(Exception):
    pass
