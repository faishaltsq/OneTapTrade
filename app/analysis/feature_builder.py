from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from app.analysis.indicators import calc_atr, calc_ema, calc_rsi
from app.analysis.market_structure import (
    detect_market_structure,
    detect_support_resistance,
    detect_trend,
)
from app.analysis.orderflow import (
    analyze_spread,
    calc_delta_proxy,
    calc_tick_imbalance,
    dom_imbalance_proxy,
)
from app.analysis.regime_detector import detect_market_regime
from app.analysis.volume_profile import calculate_volume_profile
from app.config import settings
from app.logger import logger


def _safe_candle(df: pd.DataFrame) -> dict:
    if df is None or len(df) == 0:
        return {}
    row = df.iloc[-1]
    return {
        "time": str(row.get("time", "")),
        "open": float(row["open"]) if not pd.isna(row.get("open")) else None,
        "high": float(row["high"]) if not pd.isna(row.get("high")) else None,
        "low": float(row["low"]) if not pd.isna(row.get("low")) else None,
        "close": float(row["close"]) if not pd.isna(row.get("close")) else None,
        "tick_volume": float(row["tick_volume"]) if not pd.isna(row.get("tick_volume")) else 0,
    }


def _safe_indicators(df: pd.DataFrame) -> dict:
    if df is None or len(df) == 0:
        return {"ema_50": None, "ema_200": None, "rsi_14": None, "rsi_state": "MENUNGGU_DATA", "atr_14": None}

    def _last(series):
        if series is None or series.empty or series.dropna().empty:
            return None
        val = series.dropna().iloc[-1]
        return round(float(val), 5) if not pd.isna(val) else None

    rsi_14 = _last(calc_rsi(df, 14))
    if rsi_14 is None:
        rsi_state = "MENUNGGU_DATA"
    elif rsi_14 < 25:
        rsi_state = "OVERSOLD"
    elif rsi_14 > 75:
        rsi_state = "OVERBOUGHT"
    else:
        rsi_state = "NORMAL"

    return {
        "ema_50": _last(calc_ema(df, 50)),
        "ema_200": _last(calc_ema(df, 200)),
        "rsi_14": rsi_14,
        "rsi_state": rsi_state,
        "atr_14": _last(calc_atr(df, 14)),
    }


def _safe_none(df: pd.DataFrame) -> bool:
    return df is None or len(df) == 0


def _build_timeframe_section(
    df: pd.DataFrame, timeframe: str, include_orderflow: bool = False
) -> dict:
    bars_count = len(df) if df is not None else 0

    section: dict[str, Any] = {
        "timeframe": timeframe,
        "bars_count": bars_count,
        "current_candle": _safe_candle(df),
        "indicators": _safe_indicators(df),
        "market_structure": {
            **detect_trend(df),
            **detect_market_structure(df),
            "support_resistance": detect_support_resistance(df),
        },
        "volume_profile": calculate_volume_profile(df),
    }

    if include_orderflow and df is not None and len(df) > 0:
        section["orderflow"] = calc_delta_proxy(df)

    return section


def build_market_payload(
    symbol: str,
    df_d1: Optional[pd.DataFrame],
    df_h4: Optional[pd.DataFrame],
    df_h1: Optional[pd.DataFrame],
    df_m15: Optional[pd.DataFrame],
    bid: float,
    ask: float,
    spread_points: int,
    tick_data: Optional[pd.DataFrame] = None,
    depth_data: Optional[list] = None,
    account_info: Optional[dict] = None,
) -> dict:

    logger.debug(f"Building market payload for {symbol}")

    mid = round((bid + ask) / 2.0, 5)

    d1_section = _build_timeframe_section(df_d1, "D1")
    h4_section = _build_timeframe_section(df_h4, "H4")
    h1_section = _build_timeframe_section(df_h1, "H1")
    m15_section = _build_timeframe_section(df_m15, "M5", include_orderflow=True)

    regime = detect_market_regime(df_d1, df_h1, df_m15)

    tick_imbalance_1m = None
    tick_imbalance_5m = None

    if tick_data is not None and len(tick_data) > 0:
        tick_imbalance_1m = _last_safe(calc_tick_imbalance(tick_data, 1))
        tick_imbalance_5m = _last_safe(calc_tick_imbalance(tick_data, 5))

    spread_analysis = analyze_spread(df_m15 if not _safe_none(df_m15) else None)
    delta_proxy = calc_delta_proxy(df_m15 if not _safe_none(df_m15) else None)
    dom_imbalance = dom_imbalance_proxy(depth_data) if depth_data else dom_imbalance_proxy(None)

    orderflow_proxy: dict[str, Any] = {
        "spread_status": spread_analysis["status"],
        "tick_imbalance_1m": tick_imbalance_1m,
        "tick_imbalance_5m": tick_imbalance_5m,
        "delta_proxy": delta_proxy,
        "dom_imbalance": dom_imbalance if depth_data else None,
        "current_spread_points": spread_analysis["current_spread_points"],
        "avg_spread_points": spread_analysis["avg_spread_points"],
    }

    account_context: dict[str, Any] = {
        "balance": None,
        "equity": None,
        "daily_pnl_percent": None,
        "daily_drawdown_percent": None,
        "open_positions_count": 0,
        "has_open_position": False,
    }

    if account_info:
        account_context["balance"] = account_info.get("balance")
        account_context["equity"] = account_info.get("equity")
        account_context["daily_pnl_percent"] = account_info.get("daily_pnl_percent")
        account_context["daily_drawdown_percent"] = account_info.get("daily_drawdown_percent")
        account_context["open_positions_count"] = account_info.get("open_positions_count", 0)
        account_context["has_open_position"] = bool(account_context["open_positions_count"])

    risk_config = {
        "risk_profile": settings.risk_profile,
        "risk_per_trade_percent": settings.risk_per_trade_percent,
        "min_risk_reward": settings.effective_min_risk_reward,
        "max_open_positions": settings.max_open_positions,
        "max_daily_drawdown_percent": settings.max_daily_drawdown_percent,
        "min_confidence": settings.effective_min_confidence,
    }

    from app.analysis.smc_detector import build_smc_section
    from app.analysis.major_trend import build_major_trend_section
    from app.services.position_state_service import get_open_position_state

    smc_section = build_smc_section(df_h1, df_m15)
    major_trend = build_major_trend_section(df_d1, smc_section)
    open_position_state = get_open_position_state(symbol)

    payload = {
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_price": {
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread_points": spread_points,
        },
        "higher_timeframe": d1_section,
        "primary_timeframe": h1_section,
        "secondary_timeframe": h4_section,
        "entry_timeframe": m15_section,
        "overall_regime": regime,
        "orderflow_proxy": orderflow_proxy,
        "smc": smc_section,
        "major_trend": major_trend,
        "open_position_state": open_position_state,
        "account_context": account_context,
        "risk_config": risk_config,
    }

    logger.debug(f"Market payload built for {symbol} — regime: {regime.get('regime')}")
    return payload


def _last_safe(series: pd.Series) -> Optional[float]:
    if series is None or series.empty or series.dropna().empty:
        return None
    val = series.dropna().iloc[-1]
    return round(float(val), 5) if not pd.isna(val) else None
