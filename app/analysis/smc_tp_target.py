def find_smc_tp_target(
    side: str,
    entry_price: float,
    smc: dict,
) -> float | None:
    side = str(side).upper()
    smc = smc or {}

    targets = []

    liquidity_levels = smc.get("liquidity_levels", []) or []
    for liq in liquidity_levels:
        price = float(liq.get("price", 0) or 0)
        if price == 0:
            continue
        if side == "BUY" and price > entry_price:
            targets.append(price)
        elif side == "SELL" and price < entry_price:
            targets.append(price)

    fvg_zones = smc.get("fvg_zones", []) or []
    for fvg in fvg_zones:
        if side == "BUY" and fvg.get("direction") == "bearish":
            top = float(fvg.get("top", 0) or 0)
            if top > entry_price:
                targets.append(top)
        elif side == "SELL" and fvg.get("direction") == "bullish":
            bottom = float(fvg.get("bottom", 0) or 0)
            if bottom > 0 and bottom < entry_price:
                targets.append(bottom)

    order_blocks = smc.get("order_blocks", {}) if isinstance(smc.get("order_blocks"), dict) else {}
    if side == "BUY":
        for ob in order_blocks.get("supply", []) or []:
            high = float(ob.get("high", 0) or 0)
            if high > entry_price:
                targets.append(high)
    elif side == "SELL":
        for ob in order_blocks.get("demand", []) or []:
            low = float(ob.get("low", 0) or 0)
            if low > 0 and low < entry_price:
                targets.append(low)

    if not targets:
        return None

    targets.sort(key=lambda t: abs(t - entry_price))
    return round(targets[0], 5)
