from typing import Optional


def _atr_based_sl_tp(mid: float, atr: float, direction: str, tf: str) -> tuple:
    multipliers = {
        "D1": (2.0, 4.0),
        "H1": (1.5, 3.0),
        "M5": (1.0, 2.0),
    }
    sl_mult, tp_mult = multipliers.get(tf, (1.5, 3.0))
    if direction.upper() == "BUY":
        sl = mid - (atr * sl_mult)
        tp = mid + (atr * tp_mult)
    else:
        sl = mid + (atr * sl_mult)
        tp = mid - (atr * tp_mult)
    return round(sl, 5), round(tp, 5)


def _tf_probability(trend: str, rsi: float, ema_bias: str, choch: str) -> int:
    score = 50
    if trend in ("BULLISH", "BEARISH"):
        score += 15
    elif trend == "RANGING":
        score -= 10
    if rsi:
        if 40 < rsi < 60:
            score -= 5
        elif rsi > 70 or rsi < 30:
            score += 10
    if ema_bias == "Bullish":
        score += 10
    elif ema_bias == "Bearish":
        score += 10
    if choch and choch != "NONE":
        score += 5
    return max(10, min(95, score))


def _tf_trend_from_candles(df_section: dict) -> str:
    if not df_section:
        return "N/A"
    ms = df_section.get("market_structure", {})
    trend = ms.get("trend") or ms.get("bias") or ""
    if trend:
        return str(trend).upper()
    ind = df_section.get("indicators", {})
    ema50 = ind.get("ema_50")
    ema200 = ind.get("ema_200")
    if ema50 and ema200:
        try:
            if float(ema50) > float(ema200):
                return "BULLISH"
            elif float(ema50) < float(ema200):
                return "BEARISH"
        except (ValueError, TypeError):
            pass
    return "UNCLEAR"


def _rsi_state(rsi_val) -> str:
    if rsi_val is None:
        return "N/A"
    try:
        r = float(rsi_val)
        if r > 70:
            return "OVERBOUGHT"
        if r < 30:
            return "OVERSOLD"
        return "NORMAL"
    except (ValueError, TypeError):
        return "N/A"


def _ema_bias(indicators: dict) -> str:
    ema50 = indicators.get("ema_50")
    ema200 = indicators.get("ema_200")
    if ema50 and ema200:
        try:
            if float(ema50) > float(ema200):
                return "Bullish"
            if float(ema50) < float(ema200):
                return "Bearish"
        except (ValueError, TypeError):
            pass
    return "N/A"


def build_per_tf_analysis(market_payload: dict, decision: str, mid: float) -> dict:
    payload = market_payload or {}
    smc = payload.get("smc", {})
    choch = ""
    try:
        choch_data = smc.get("choch", {})
        choch = choch_data.get("direction", "NONE") if isinstance(choch_data, dict) else "NONE"
    except Exception:
        choch = "NONE"

    order_blocks = smc.get("order_blocks", {})
    demand = order_blocks.get("demand", []) or []
    supply = order_blocks.get("supply", []) or []

    sections = {
        "D1": payload.get("higher_timeframe", {}),
        "H1": payload.get("primary_timeframe", {}),
        "M5": payload.get("entry_timeframe", {}),
    }

    tf_labels = {
        "D1": "D1 \u2014 Daily Trend",
        "H1": "H1 \u2014 Execution Bias",
        "M5": "M5 \u2014 Entry Trigger",
    }

    result = {}

    for tf, section in sections.items():
        trend = _tf_trend_from_candles(section)
        ind = section.get("indicators", {}) if isinstance(section, dict) else {}
        rsi = ind.get("rsi_14")
        rsi_state = _rsi_state(rsi)
        ema_bias = _ema_bias(ind)
        atr = ind.get("atr_14")

        prob = _tf_probability(trend, rsi if rsi else 0, ema_bias, str(choch))

        sl, tp = (None, None)
        if atr and mid:
            try:
                sl, tp = _atr_based_sl_tp(mid, float(atr), decision, tf)
            except Exception:
                pass

        ob_zone = ""
        if decision.upper() == "BUY" and demand:
            blk = demand[-1] if isinstance(demand[-1], dict) else {}
            ob_zone = f"Demand: {blk.get('low', '?')} \u2013 {blk.get('high', '?')}"
        elif decision.upper() == "SELL" and supply:
            blk = supply[-1] if isinstance(supply[-1], dict) else {}
            ob_zone = f"Supply: {blk.get('low', '?')} \u2013 {blk.get('high', '?')}"

        entry_type = "MARKET"
        if decision.upper() == "BUY" and demand:
            blk = demand[-1] if isinstance(demand[-1], dict) else {}
            try:
                if float(blk.get("high", 0)) < mid:
                    entry_type = "BUY LIMIT"
            except Exception:
                pass
        elif decision.upper() == "SELL" and supply:
            blk = supply[-1] if isinstance(supply[-1], dict) else {}
            try:
                if float(blk.get("low", 0)) > mid:
                    entry_type = "SELL LIMIT"
            except Exception:
                pass

        trend_emoji = "\U0001f7e2" if trend == "BULLISH" else ("\U0001f534" if trend == "BEARISH" else "\u26aa")
        prob_emoji = "\u2705" if prob >= 70 else ("\u26a0\ufe0f" if prob >= 50 else "\u274c")

        lines = [
            f"\U0001f4ca <b>{tf_labels[tf]}</b>",
            f"{trend_emoji} Trend: {trend} | RSI: {rsi_state} | EMA: {ema_bias}",
            f"{prob_emoji} Setup prob: {prob}%",
        ]

        if ob_zone:
            lines.append(f"\U0001f4cd {ob_zone}")

        if entry_type != "MARKET" or decision.upper() in ("BUY", "SELL"):
            lines.append(f"\U0001f4cc Entry: <b>{entry_type}</b>")
            if sl:
                lines.append(f"SL: <code>{sl}</code> | TP: <code>{tp}</code>")

        if decision.upper() == "HOLD":
            if trend == "BULLISH":
                lines.append("\U0001f4a1 Wait for pullback to demand for BUY LIMIT")
            elif trend == "BEARISH":
                lines.append("\U0001f4a1 Wait for retrace to supply for SELL LIMIT")
            else:
                lines.append("\u23f9 Wait for clear direction before entry")

        result[tf] = "\n".join(lines)

    return result
