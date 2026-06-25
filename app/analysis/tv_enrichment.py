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
                try:
                    if abs(float(tv_rsi) - float(mt5_rsi)) < 5:
                        agreement_count += 1
                except (ValueError, TypeError):
                    pass
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
        supports = pine_levels.get("support") or []
        resistances = pine_levels.get("resistance") or []
        all_levels = supports + resistances
        for level in all_levels:
            level_price = float(level) if not isinstance(level, dict) else float(level.get("price", 0))
            for blk in demand_blocks:
                if isinstance(blk, dict):
                    blk_price = float(blk.get("low", 0))
                    if abs(level_price - blk_price) / max(abs(blk_price), 0.0001) < 0.002:
                        zone_match = max(zone_match, 1)
            for blk in supply_blocks:
                if isinstance(blk, dict):
                    blk_price = float(blk.get("high", 0))
                    if abs(level_price - blk_price) / max(abs(blk_price), 0.0001) < 0.002:
                        zone_match = max(zone_match, 1)
        if zone_match > 0:
            zone_match = 2
    score += zone_match
    details["breakdown"]["smc_tv_zone_match"] = zone_match

    # 4. TV Pine annotation confluence (0-2)
    annotations = tv_ctx.get("pine_annotations", []) or []
    current_price = market_payload.get("current_price", {})
    mid = current_price.get("mid", 0)

    pine_score = 0
    for ann in annotations:
        text = (ann.get("text") or "").lower()
        ann_price = ann.get("price")
        if ann_price is not None and mid > 0:
            if abs(float(ann_price) - float(mid)) / max(abs(float(mid)), 0.01) < 0.02:
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
