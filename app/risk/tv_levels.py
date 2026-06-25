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
