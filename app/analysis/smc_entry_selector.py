def select_smc_limit_entry(
    decision: str,
    current_bid: float,
    current_ask: float,
    market_payload: dict,
) -> dict:
    side = str(decision).upper()
    payload = market_payload or {}
    smc = payload.get("smc", {}) if isinstance(payload, dict) else {}
    order_blocks = smc.get("order_blocks", {}) if isinstance(smc, dict) else {}

    if not _major_trend_allows(side, payload):
        return _no_limit(f"D1 major trend does not allow {side}")

    if side == "BUY":
        result = _select_buy_limit(order_blocks.get("demand", []) or [], current_ask, smc)
        return _mark_near_third(result, current_ask)
    if side == "SELL":
        result = _select_sell_limit(order_blocks.get("supply", []) or [], current_bid, smc)
        return _mark_near_third(result, current_bid)
    return _no_limit("Decision is not BUY or SELL")


def can_use_market_fallback(decision: str, confidence: float, market_payload: dict | None) -> bool:
    side = str(decision).upper()
    if confidence <= 0.50:
        return False
    payload = market_payload or {}
    if not _major_trend_allows(side, payload):
        return False

    h1 = _trend(payload.get("primary_timeframe", {}))
    m5 = _trend(payload.get("entry_timeframe", {}))
    if side == "BUY" and h1 == "BEARISH" and m5 == "BEARISH":
        return False
    if side == "SELL" and h1 == "BULLISH" and m5 == "BULLISH":
        return False
    return side in {"BUY", "SELL"}


def _select_buy_limit(demand_blocks: list, current_ask: float, smc: dict) -> dict:
    candidates = []
    for block in demand_blocks:
        low = block.get("low")
        high = block.get("high")
        if low is None or high is None:
            continue
        low = float(low)
        high = float(high)
        if high >= current_ask:
            continue
        entry = low + ((high - low) * 0.67)
        score = _score_zone(block, high, current_ask, smc, "BUY")
        candidates.append((score, block, low, high, entry))

    if not candidates:
        return _no_limit("No valid demand order block below current ask")

    score, block, low, high, entry = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
    return _limit_result("BUY_LIMIT", "demand_ob", low, high, entry, score, block)


def _select_sell_limit(supply_blocks: list, current_bid: float, smc: dict) -> dict:
    candidates = []
    for block in supply_blocks:
        low = block.get("low")
        high = block.get("high")
        if low is None or high is None:
            continue
        low = float(low)
        high = float(high)
        if low <= current_bid:
            continue
        entry = high - ((high - low) * 0.67)
        score = _score_zone(block, low, current_bid, smc, "SELL")
        candidates.append((score, block, low, high, entry))

    if not candidates:
        return _no_limit("No valid supply order block above current bid")

    score, block, low, high, entry = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
    return _limit_result("SELL_LIMIT", "supply_ob", low, high, entry, score, block)


def _score_zone(block: dict, zone_edge: float, current_price: float, smc: dict, side: str) -> float:
    score = 0.45
    index = block.get("index")
    if isinstance(index, int):
        score += min(max(index, 0), 100) / 500

    distance_pct = abs(current_price - zone_edge) / max(abs(current_price), 0.0001)
    if distance_pct <= 0.005:
        score += 0.20
    elif distance_pct <= 0.015:
        score += 0.10

    choch = smc.get("choch", {}) if isinstance(smc, dict) else {}
    m5_choch = choch.get("m5", {}) if isinstance(choch, dict) else {}
    if side == "BUY" and m5_choch.get("bullish_choch"):
        score += 0.10
    if side == "SELL" and m5_choch.get("bearish_choch"):
        score += 0.10

    if smc.get("fvg_zones") or smc.get("liquidity_levels"):
        score += 0.05

    return round(min(score, 1.0), 2)


def _quality(score: float) -> str:
    if score >= 0.70:
        return "HIGH"
    if score >= 0.50:
        return "MEDIUM"
    if score >= 0.30:
        return "LOW"
    return "NONE"


def _limit_result(order_type: str, zone_type: str, low: float, high: float, entry: float, score: float, block: dict) -> dict:
    depth = (entry - low) / (high - low) if (high - low) != 0 else 0.0
    depth = round(max(0.0, min(1.0, depth)), 2)

    return {
        "valid": _quality(score) in {"MEDIUM", "HIGH"},
        "entry_type": "LIMIT",
        "order_type": order_type,
        "entry_price": round(entry, 5),
        "zone_type": zone_type,
        "zone_low": round(low, 5),
        "zone_high": round(high, 5),
        "zone_depth": depth,
        "is_near_third": False,
        "score": score,
        "quality": _quality(score),
        "reason": f"Selected {zone_type} with {round(score, 2)} score",
        "source": block,
    }


def _mark_near_third(result: dict, current_price: float) -> dict:
    if not result.get("valid"):
        return result
    entry = float(result.get("entry_price", 0) or 0)
    if current_price and entry:
        distance_pct = abs(current_price - entry) / max(abs(current_price), 0.0001)
        result["is_near_third"] = distance_pct <= 0.003
    return result


def _no_limit(reason: str) -> dict:
    return {
        "valid": False,
        "entry_type": "MARKET",
        "order_type": "MARKET",
        "entry_price": None,
        "zone_type": None,
        "zone_low": None,
        "zone_high": None,
        "score": 0.0,
        "quality": "NONE",
        "reason": reason,
    }


def _major_trend_allows(side: str, payload: dict) -> bool:
    major_trend = payload.get("major_trend") or {}
    allowed = major_trend.get("allowed_directions") or []
    return not allowed or side in allowed


def _trend(section: dict) -> str:
    market_structure = section.get("market_structure", {}) if isinstance(section, dict) else {}
    return str(market_structure.get("trend") or market_structure.get("bias") or "").upper()
