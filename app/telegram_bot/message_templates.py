from app.config import settings


def _escape_html(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _decision_emoji(decision: str) -> str:
    d = str(decision).upper()
    if d == "BUY":
        return "\U0001f7e2"
    if d == "SELL":
        return "\U0001f534"
    return "\u26aa"


def _confidence_emoji(confidence: float) -> str:
    if confidence >= 0.80:
        return "\u2705"
    if confidence >= 0.65:
        return "\u26a0\ufe0f"
    return "\u274c"


def _bool_emoji(value: bool) -> str:
    return "\u2705" if value else "\u274c"


def build_main_menu_keyboard(is_paused: bool = True, mode: str = "SIGNAL_ONLY", active_symbol: str = "ALL", strategy_mode: str | None = None) -> "InlineKeyboardMarkup":
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    pause_btn = InlineKeyboardButton(
        "\u25b6\ufe0f Auto Signal ON" if is_paused else "\u23f8\ufe0f Auto Signal OFF",
        callback_data="MENU_TOGGLE_PAUSE",
    )
    mode_label = {"SIGNAL_ONLY": "Signal", "SEMI_AUTO": "Semi-Auto", "AUTO_DEMO": "Auto Demo", "LIVE_AUTO": "Live"}.get(mode, mode)
    strategy_mode = strategy_mode or settings.strategy_mode
    smc_marker = " \u2705" if strategy_mode == "SMC_AI" else ""
    ai_marker = " \u2705" if strategy_mode == "AI_ONLY" else ""

    keyboard = [
        [
            InlineKeyboardButton("\U0001f4ca Status", callback_data="MENU_STATUS"),
            InlineKeyboardButton("\U0001f4cb Positions", callback_data="MENU_POSITIONS"),
        ],
        [
            InlineKeyboardButton("\U0001f4dd Pending", callback_data="MENU_PENDING"),
            InlineKeyboardButton("\u274c Close Pending", callback_data="MENU_CLOSE_PENDING"),
        ],
        [
            InlineKeyboardButton("\U0001f4e1 Last Signal", callback_data="MENU_LAST_SIGNAL"),
            InlineKeyboardButton("\u2699\ufe0f Settings", callback_data="MENU_SETTINGS"),
        ],
        [
            InlineKeyboardButton("\U0001f4f8 Chart", callback_data="MENU_CHART"),
            InlineKeyboardButton("\U0001f50d Analyze", callback_data="MENU_ANALYZE"),
        ],
        [
            InlineKeyboardButton(f"\U0001f4ca All Pairs", callback_data="MENU_SYMBOL_ALL"),
            InlineKeyboardButton(f"\U0001f504 Next Pair", callback_data="MENU_SYMBOL_NEXT"),
        ],
        [
            InlineKeyboardButton(f"\U0001f9e0 SMC+AI{smc_marker}", callback_data="MENU_STRATEGY_SMC"),
            InlineKeyboardButton(f"\U0001f916 AI Only{ai_marker}", callback_data="MENU_STRATEGY_AI"),
        ],
        [pause_btn],
        [
            InlineKeyboardButton("\U0001f4e1 Signal", callback_data="MENU_MODE_SIGNAL"),
            InlineKeyboardButton("\U0001f50d Semi", callback_data="MENU_MODE_SEMI"),
            InlineKeyboardButton("\U0001f504 Auto", callback_data="MENU_MODE_AUTO"),
        ],
        [
            InlineKeyboardButton("\U0001f7e2 Low", callback_data="MENU_RISK_LOW"),
            InlineKeyboardButton("\U0001f7e1 Med", callback_data="MENU_RISK_MEDIUM"),
            InlineKeyboardButton("\U0001f534 High", callback_data="MENU_RISK_HIGH"),
        ],
        [
            InlineKeyboardButton("\u274c Close All", callback_data="MENU_CLOSE_ALL"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_settings_keyboard() -> "InlineKeyboardMarkup":
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.config import settings

    smc_marker = " \u2705" if settings.strategy_mode == "SMC_AI" else ""
    ai_marker = " \u2705" if settings.strategy_mode == "AI_ONLY" else ""

    keyboard = [
        [
            InlineKeyboardButton("\U0001f7e2 Low (Swing)", callback_data="MENU_RISK_LOW"),
            InlineKeyboardButton("\U0001f7e1 Med (Day)", callback_data="MENU_RISK_MEDIUM"),
            InlineKeyboardButton("\U0001f534 High (Scalp)", callback_data="MENU_RISK_HIGH"),
        ],
        [
            InlineKeyboardButton(f"\U0001f9e0 SMC+AI{smc_marker}", callback_data="MENU_STRATEGY_SMC"),
            InlineKeyboardButton(f"\U0001f916 AI Only{ai_marker}", callback_data="MENU_STRATEGY_AI"),
        ],
        [
            InlineKeyboardButton("Risk 0.25%", callback_data="MENU_RISK_TRADE_025"),
            InlineKeyboardButton("Risk 0.5%", callback_data="MENU_RISK_TRADE_050"),
            InlineKeyboardButton("Risk 1%", callback_data="MENU_RISK_TRADE_100"),
        ],
        [InlineKeyboardButton("⬅️ Back/Menu", callback_data="MENU_BACK")],
    ]
    return InlineKeyboardMarkup(keyboard)


def format_pending_orders_message(orders: list) -> str:
    if not orders:
        return "<b>\U0001f4dd Pending Orders</b>\n\n<i>No pending orders.</i>"

    lines = [f"<b>\U0001f4dd Pending Orders — {len(orders)} order(s)</b>\n"]

    for order in orders:
        ticket = order.get("ticket", "?")
        symbol = order.get("symbol", "?")
        order_type = int(order.get("type", 0))
        price = order.get("price_open", 0)
        sl = order.get("sl", 0)
        tp = order.get("tp", 0)
        volume = order.get("volume", 0)

        try:
            import MetaTrader5 as mt5
            if order_type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP):
                side = "BUY"
                emoji = "\U0001f7e2"
            elif order_type in (mt5.ORDER_TYPE_SELL_LIMIT, mt5.ORDER_TYPE_SELL_STOP):
                side = "SELL"
                emoji = "\U0001f534"
            else:
                side = "?"
                emoji = "\u26aa"
        except Exception:
            side = "?"
            emoji = "\u26aa"

        lines.append(
            f"{emoji} <b>#{ticket}</b> {side} <code>{symbol}</code> | Lot: {volume} | "
            f"Price: {price} | SL: {sl} | TP: {tp}"
        )

    return "\n".join(lines)


def format_welcome_message() -> str:
    return (
        "<b>\U0001f916 OneTapTrade AI Trading Bot</b>\n\n"
        "<b>Commands:</b>\n"
        "/start - Show this message\n"
        "/status - Bot status &amp; account summary\n"
        "/positions - Open positions\n"
        "/last_signal - Latest AI decision\n"
        "/settings - Risk settings\n"
        "/pause - Stop Trade (stop new trades)\n"
        "/resume - Resume Trade\n"
        "/mode_signal - Signal-only mode\n"
        "/mode_semi - Semi-auto mode\n"
        "/mode_demo_auto - Auto demo mode\n"
        "/close_all - Close all positions\n\n"
        "<i>Use inline buttons on trade signals to approve or reject trades.</i>"
    )


def format_status_message(status_data: dict) -> str:
    mode = status_data.get("mode", "N/A")
    symbol = status_data.get("symbol", settings.default_symbol)
    equity = status_data.get("equity")
    balance = status_data.get("balance")
    daily_pnl = status_data.get("daily_pnl")
    dd_pct = status_data.get("daily_drawdown_percent")
    positions_count = status_data.get("open_positions_count", 0)
    paused = status_data.get("paused", False)
    mt5_connected = status_data.get("mt5_connected", False)
    last_signal_time = status_data.get("last_signal_time")

    lines = ["<b>\U0001f4ca Bot Status</b>\n"]
    lines.append(f"<b>Mode:</b> <code>{_escape_html(mode)}</code>")
    lines.append(f"<b>Symbol:</b> <code>{_escape_html(symbol)}</code>")

    if paused:
        lines.append("\n\u23f8\ufe0f <b>Auto Signal: OFF</b> (use \U0001f50d Analyze for manual)")
    else:
        lines.append("\n\u25b6\ufe0f <b>Auto Signal: ON</b>")

    if mt5_connected:
        lines.append(f"<b>Equity:</b> ${equity:,.2f}" if equity is not None else "<b>Equity:</b> N/A")
        lines.append(f"<b>Balance:</b> ${balance:,.2f}" if balance is not None else "<b>Balance:</b> N/A")
        pnl_str = f"${daily_pnl:+,.2f}" if daily_pnl is not None else "N/A"
        lines.append(f"<b>Daily P&amp;L:</b> {pnl_str}")
        dd_str = f"{dd_pct:.2f}%" if dd_pct is not None else "N/A"
        dd_emoji = "\u26a0\ufe0f" if (dd_pct and dd_pct > 1.0) else "\u2705"
        lines.append(f"<b>Daily DD:</b> {dd_emoji} {dd_str}")
        lines.append(f"<b>Open Positions:</b> {positions_count}")
    else:
        lines.append("\n\u26a0\ufe0f <b>MT5 not connected</b>")

    from app.tv_connector import is_tv_available

    if is_tv_available():
        lines.append(f"\n\U0001f4ca <b>TradingView:</b> \u2705 Connected")
    else:
        lines.append(f"\n\U0001f4ca <b>TradingView:</b> \u274c Not Connected")

    if last_signal_time:
        lines.append(f"\n<b>Last Signal:</b> <i>{_escape_html(str(last_signal_time))}</i>")

    return "\n".join(lines)


def format_positions_message(positions: list, symbol: str, realized_pnl: float = 0.0) -> str:
    floating_pnl = sum(
        (pos.get("profit", 0) or 0) + (pos.get("swap", 0) or 0)
        for pos in positions
    )
    total_pnl = floating_pnl + realized_pnl

    def _pnl_line(label: str, amount: float) -> str:
        emoji = "\U0001f7e2" if amount >= 0 else "\U0001f534"
        return f"<b>{label}: ${amount:+,.2f}</b> {emoji}"

    summary_lines = [
        _pnl_line("Floating P&amp;L", floating_pnl),
        _pnl_line("Today Realized P&amp;L", realized_pnl),
        _pnl_line("Today Total P&amp;L", total_pnl),
    ]

    if not positions:
        return (
            f"<b>\U0001f4cb Open Positions — {_escape_html(symbol)}</b>\n"
            + "\n".join(summary_lines)
            + "\n\n<i>No open positions.</i>"
        )

    lines = [f"<b>\U0001f4cb Open Positions — {_escape_html(symbol)}</b>"]
    lines.extend(summary_lines)
    lines.append("")

    for pos in positions:
        ticket = pos.get("ticket", "?")
        sym = pos.get("symbol", "?")
        pos_type = "BUY" if pos.get("type", 0) == 0 else "SELL"
        emoji = "\U0001f7e2" if pos_type == "BUY" else "\U0001f534"
        volume = pos.get("volume", 0)
        open_price = pos.get("price_open", 0)
        sl = pos.get("sl", 0)
        tp = pos.get("tp", 0)
        profit = pos.get("profit", 0)
        swap = pos.get("swap", 0)

        lines.append(
            f"{emoji} <b>#{ticket}</b> {pos_type} <code>{sym}</code> | Lot: {volume} | "
            f"Open: {open_price} | SL: {sl} | TP: {tp}"
        )
        total_profit = profit + swap
        pnl_str = f"${total_profit:+,.2f}"
        pnl_emoji = "\U0001f7e2" if total_profit >= 0 else "\U0001f534"
        lines.append(f"   P&amp;L: {pnl_emoji} {pnl_str}\n")

    return "\n".join(lines)


def _enum_value(value) -> str:
    if value is None:
        return "N/A"
    return value.value if hasattr(value, "value") else str(value)


def _val(value, default: str = "N/A") -> str:
    if value is None or value == "":
        return default
    return _escape_html(str(value))


def _fmt_num(value) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return _escape_html(str(value))


def _pip_size_for_symbol(symbol: str) -> float:
    letters = "".join(ch for ch in str(symbol).upper() if ch.isalpha())
    currencies = {"AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NZD", "USD"}
    if len(letters) >= 6 and letters[:3] in currencies and letters[3:6] in currencies:
        return 0.01 if letters[3:6] == "JPY" else 0.0001
    return 1.0


def _fmt_alert_num(value) -> str:
    if value is None:
        return "Menunggu data"
    return _fmt_num(value)


def _display_trend(value: str | None) -> str:
    if value is None or value == "":
        return "Menunggu data"
    text = str(value).upper()
    if text in {"UNCLEAR", "UNKNOWN", "NONE"}:
        return "Belum ada bias jelas"
    return text.title()


def _display_regime(value: str | None) -> str:
    if value is None or value == "":
        return "Menunggu data"
    text = str(value).upper()
    if text in {"UNCLEAR", "UNKNOWN", "NONE"}:
        return "Belum ada bias jelas"
    return text.replace("_", " ").title()


def _display_rsi_state(value: str | None) -> str:
    labels = {
        "OVERSOLD": "Oversold",
        "NORMAL": "Normal",
        "OVERBOUGHT": "Overbought",
        "MENUNGGU_DATA": "Menunggu data",
    }
    if value is None or value == "":
        return "Menunggu data"
    return labels.get(str(value).upper(), _display_trend(str(value)))


def _section_trend(payload: dict, key: str) -> str:
    section = (payload or {}).get(key, {})
    ms = section.get("market_structure", {}) if isinstance(section, dict) else {}
    raw_trend = ms.get("trend") or ms.get("bias")
    if raw_trend and str(raw_trend).upper() not in {"UNCLEAR", "UNKNOWN", "NONE"}:
        return _display_trend(raw_trend)

    indicators = section.get("indicators", {}) if isinstance(section, dict) else {}
    ema_trend = _ema_bias(indicators)
    if ema_trend != "Menunggu data":
        return ema_trend

    bars_count = section.get("bars_count") if isinstance(section, dict) else None
    if bars_count == 0:
        return "Menunggu data"
    return "Belum ada bias jelas"


def _indicators(payload: dict, key: str) -> dict:
    section = (payload or {}).get(key, {})
    return section.get("indicators", {}) if isinstance(section, dict) else {}


def _ema_bias(indicators: dict) -> str:
    ema200 = indicators.get("ema_200")
    ema50 = indicators.get("ema_50")
    if ema50 is None or ema200 is None:
        return "Menunggu data"
    try:
        if float(ema50) > float(ema200):
            return "Bullish"
        if float(ema50) < float(ema200):
            return "Bearish"
        return "Belum ada bias jelas"
    except (TypeError, ValueError):
        return "Menunggu data"


def _decision_bias_or_payload(decision_value, payload: dict, key: str) -> str:
    value = _enum_value(decision_value) if decision_value else ""
    if value and value.upper() not in {"UNCLEAR", "N/A"}:
        return value
    return _section_trend(payload, key)


def _format_bias_map(decision, payload: dict) -> list[str]:
    htf = getattr(decision, "higher_timeframe_bias", None)
    etf = getattr(decision, "entry_timeframe_bias", None)
    d1 = _decision_bias_or_payload(htf, payload, "higher_timeframe")
    h4 = _section_trend(payload, "secondary_timeframe")
    h1 = _section_trend(payload, "primary_timeframe")
    m5 = _decision_bias_or_payload(etf, payload, "entry_timeframe")
    regime = getattr(decision, "market_regime", None)
    raw_regime = _enum_value(regime) if regime else (payload or {}).get("overall_regime", {}).get("regime")
    if raw_regime and str(raw_regime).upper() in {"UNCLEAR", "N/A"}:
        raw_regime = (payload or {}).get("overall_regime", {}).get("regime")
    regime_text = _display_regime(raw_regime)
    regime_desc = _val((payload or {}).get("overall_regime", {}).get("description"), default="")
    return [
        "\n<b>🧭 Bias Map</b>",
        f"D1: {_escape_html(d1)} | H4: {_escape_html(h4)}",
        f"H1: {_escape_html(h1)} | M5: {_escape_html(m5)}",
        f"Regime: {regime_text}" + (f" / {regime_desc}" if regime_desc else ""),
    ]


def _format_price(payload: dict) -> list[str]:
    price = (payload or {}).get("current_price", {})
    return [
        "\n<b>💵 Price</b>",
        f"Bid/Ask: {_fmt_num(price.get('bid'))} / {_fmt_num(price.get('ask'))}",
        f"Spread: {_fmt_num(price.get('spread_points'))} pts",
    ]


def _format_momentum(payload: dict) -> list[str]:
    m5_ind = _indicators(payload, "entry_timeframe")
    h1_ind = _indicators(payload, "primary_timeframe")
    m5_rsi = _fmt_alert_num(m5_ind.get("rsi_14"))
    h1_rsi = _fmt_alert_num(h1_ind.get("rsi_14"))
    m5_state = _display_rsi_state(m5_ind.get("rsi_state"))
    h1_state = _display_rsi_state(h1_ind.get("rsi_state"))
    return [
        "\n<b>📈 Momentum</b>",
        f"M5 RSI: {m5_rsi} ({m5_state}) | EMA50/200: {_ema_bias(m5_ind)}",
        f"H1 RSI: {h1_rsi} ({h1_state}) | EMA50/200: {_ema_bias(h1_ind)}",
    ]


def _format_smc(payload: dict) -> list[str]:
    smc = (payload or {}).get("smc", {})
    choch = smc.get("choch", {}) if isinstance(smc, dict) else {}
    direction = choch.get("direction")
    if not direction:
        m5_choch = choch.get("m5", {}) if isinstance(choch, dict) else {}
        if m5_choch.get("bullish_choch"):
            direction = "Bullish"
        elif m5_choch.get("bearish_choch"):
            direction = "Bearish"
    order_blocks = smc.get("order_blocks", {}) if isinstance(smc, dict) else {}
    demand = order_blocks.get("demand", []) or []
    supply = order_blocks.get("supply", []) or []
    liquidity = smc.get("liquidity_levels", []) if isinstance(smc, dict) else []
    nearest_demand = demand[-1].get("low") if demand else None
    nearest_supply = supply[-1].get("high") if supply else None
    liq = liquidity[0] if liquidity else {}
    liq_text = f"{liq.get('type', 'level')} @ {_fmt_alert_num(liq.get('price'))}" if liq else "Menunggu data"
    return [
        "\n<b>🧱 SMC</b>",
        f"CHoCH: {_display_trend(direction)}",
        f"Nearest Demand: {_fmt_alert_num(nearest_demand)}",
        f"Nearest Supply: {_fmt_alert_num(nearest_supply)}",
        f"Liquidity: {_escape_html(liq_text)}",
    ]


def _format_orderflow(payload: dict) -> list[str]:
    orderflow = (payload or {}).get("orderflow_proxy", {})
    delta = orderflow.get("delta_proxy")
    if isinstance(delta, dict):
        delta_text = delta.get("bias") or delta.get("direction") or delta.get("signal")
    else:
        delta_text = delta
    dom = orderflow.get("dom_imbalance")
    return [
        "\n<b>⚖️ Orderflow</b>",
        f"Delta: {_val(delta_text, default='Menunggu data')}",
        f"DOM: {_val(dom, default='Menunggu data')}",
    ]


def _format_trade_plan(decision) -> list[str]:
    entry_plan = getattr(decision, "entry_plan", None)
    if not entry_plan:
        return []
    entry_type = _enum_value(getattr(entry_plan, "entry_type", None))
    entry_price = getattr(entry_plan, "preferred_entry_price", None)
    stop_loss = getattr(entry_plan, "stop_loss", None)
    tp1 = getattr(entry_plan, "take_profit_1", None)
    rr1 = getattr(entry_plan, "risk_reward_to_tp1", None)
    return [
        "\n<b>🎯 Trade Plan</b>",
        f"Entry: {_escape_html(entry_type)}" + (f" @ {_fmt_num(entry_price)}" if entry_price else ""),
        f"SL: {_fmt_num(stop_loss)}",
        f"TP1: {_fmt_num(tp1)}",
        f"R:R: {_fmt_num(rr1)}",
    ]


def _first_matching_reason(score: dict, factor: str) -> str | None:
    for adjustment in score.get("adjustments") or []:
        if adjustment.get("factor") == factor:
            return adjustment.get("reason")
    return None


def _format_smc_probability_block(symbol: str, payload: dict, risk_result: dict) -> list[str]:
    score = (payload or {}).get("smc_probability") or {}
    if not score:
        return []
    model = score.get("timeframe_model") or {}
    confluence = score.get("main_confluence") or []
    weaknesses = score.get("weaknesses") or []
    risk_notes = score.get("risk_notes") or []
    quality = str(score.get("setup_quality") or "low").title()
    decision = score.get("pre_ai_decision") or "WAIT"
    entry_note = score.get("entry_sl_tp_note") or "manual confirmation required"
    invalidation = score.get("invalidation") or "manual confirmation required"
    price = (payload or {}).get("current_price") or {}
    execution_tfs = "/".join(model.get("execution_timeframes") or []) or "N/A"

    emoji = "\U0001f7e2" if decision == "BUY_SETUP" else "\U0001f534" if decision == "SELL_SETUP" else "\u26aa"

    lines = [
        f"{emoji} <b>{_escape_html(symbol)} \u2014 SMC ANALYSIS</b>",
        "",
        "<b>Bias:</b>",
        f"Direction: {_escape_html(str(score.get('bias') or 'neutral'))}",
        f"Execution TF: {_escape_html(execution_tfs)}",
        "",
        "<b>SMC Event:</b>",
        f"Decision: {_escape_html(decision)}",
        f"Premium/Discount: {_escape_html(_first_matching_reason(score, 'premium_discount') or 'manual confirmation required')}",
        "",
        "<b>Confluence:</b>",
    ]
    lines.extend([f"\u2705 {_escape_html(item)}" for item in confluence[:4]])
    lines.extend([f"\u26a0\ufe0f {_escape_html(item)}" for item in weaknesses[:4]])
    lines.extend([
        "",
        "<b>Probability:</b>",
        f"Score: {int(score.get('final_score') or 0)}%",
        f"Quality: {_escape_html(quality)}",
        "",
        "<b>Decision:</b>",
        _escape_html(decision),
        "",
        "<b>Risk:</b>",
        f"Spread: {_fmt_num(price.get('spread_points'))} pts",
        f"RR: {_escape_html(str(((payload or {}).get('entry_plan_context') or {}).get('risk_reward_to_tp1', 'manual confirmation required')))}",
        "",
        "<b>Entry/SL/TP:</b>",
        _escape_html(entry_note).capitalize(),
        "",
        "<b>Invalidation:</b>",
        _escape_html(invalidation),
    ])
    if risk_notes:
        lines.append("")
        lines.append("<b>Notes:</b> " + _escape_html("; ".join(str(n) for n in risk_notes[:3])))
    return lines


def format_market_trend_alert(decision, symbol: str, market_payload: dict | None = None, risk_result: dict | None = None) -> str:
    payload = market_payload or {}
    risk_result = risk_result or {}
    smc_probability_lines = _format_smc_probability_block(symbol, payload, risk_result)
    if smc_probability_lines:
        semantic = (payload.get("smc_probability") or {}).get("pre_ai_decision", "")
        if semantic not in {"BUY_SETUP", "SELL_SETUP"}:
            return "\n".join(smc_probability_lines)
    decision_str = _enum_value(getattr(decision, "decision", "HOLD"))
    confidence = getattr(decision, "confidence", 0.0) or 0.0
    reason = getattr(decision, "main_reason", "") or getattr(decision, "final_comment", "") or ""
    d_emoji = _decision_emoji(decision_str)

    major_trend = payload.get("major_trend", {})
    d1_bias = major_trend.get("bias", "D1_UNCLEAR")
    h1_bias = major_trend.get("h1_bias", "NONE")
    hierarchy = major_trend.get("d1_h1_hierarchy", "")
    h1_alignment = major_trend.get("h1_alignment", "NONE")
    align_emoji = "\u2705" if h1_alignment == "ALIGNED" else ("\u26a0\ufe0f" if h1_alignment == "CONTRARY" else "\u2795")

    d1_short = "BULLISH" if "BULL" in d1_bias.upper() else ("BEARISH" if "BEAR" in d1_bias.upper() else "RANGING")
    h1_short = h1_bias.upper() if h1_bias and h1_bias != "NONE" else "UNCLEAR"

    entry_plan = getattr(decision, "entry_plan", None)
    ep = entry_plan
    entry_type = _enum_value(getattr(ep, "entry_type", None)) if ep else None
    entry_price = getattr(ep, "preferred_entry_price", None) if ep else None
    stop_loss = getattr(ep, "stop_loss", None) if ep else None
    tp1 = getattr(ep, "take_profit_1", None) if ep else None
    tp2 = getattr(ep, "take_profit_2", None) if ep else None
    rr1 = getattr(ep, "risk_reward_to_tp1", None) if ep else None
    entry_low = getattr(ep, "entry_area_low", None) if ep else None
    entry_high = getattr(ep, "entry_area_high", None) if ep else None

    current_price = payload.get("current_price", {})
    bid = current_price.get("bid")
    ask = current_price.get("ask")
    spread_pts = current_price.get("spread_points", 0)

    d1_section = payload.get("higher_timeframe", {})
    h1_section = payload.get("primary_timeframe", {})
    m5_section = payload.get("entry_timeframe", {})

    def _tf_line(section, label):
        if not section:
            return f"{label}: N/A"
        ms = section.get("market_structure", {}) if isinstance(section, dict) else {}
        ind = section.get("indicators", {}) if isinstance(section, dict) else {}
        trend = str(ms.get("trend") or ms.get("bias") or "UNCLEAR").title()
        rsi = ind.get("rsi_14")
        rsi_s = ""
        if rsi:
            try:
                rsi_s = f" | RSI {float(rsi):.0f}"
            except (ValueError, TypeError):
                pass
        ema = _ema_bias(ind)
        return f"{label}: {trend}{rsi_s} | EMA {ema}"

    m5_trend = ""
    try:
        m5_ms = m5_section.get("market_structure", {}) if isinstance(m5_section, dict) else {}
        m5_trend = str(m5_ms.get("trend") or m5_ms.get("bias") or "UNCLEAR").lower()
    except Exception:
        m5_trend = "unclear"

    if decision_str in ("BUY", "SELL"):
        setup_label = f"{decision_str} SETUP"
        entry_label = f"{decision_str} {entry_type or 'MARKET'}"
        aggressive = "Aggressive Entry" if m5_trend == "ranging" else "Confirmed Entry"
        pip_size = _pip_size_for_symbol(symbol)

        lines = [
            f"{d_emoji} <b>{_escape_html(symbol)} \u2014 {setup_label}</b>",
            "",
            f"<b>Bias:</b> D1 {d1_short} {align_emoji} | H1 {h1_short} {align_emoji}",
            f"<b>Confluence:</b> {_escape_html(hierarchy)}",
            f"<b>Entry Type:</b> {_escape_html(entry_label)} / {aggressive}",
            f"<b>Confidence:</b> {confidence:.0%}",
            "",
            "<b>-- Multi-Timeframe Analysis --</b>",
            _tf_line(d1_section, "D1"),
            _tf_line(h1_section, "H1"),
            _tf_line(m5_section, "M5"),
            "",
            "<b>-- Trade Plan Options --</b>",
        ]

        market_entry = bid if decision_str == "SELL" else ask
        limit_entry = entry_price

        if market_entry and stop_loss and tp1:
            try:
                me = float(market_entry)
                sl = float(stop_loss)
                tp = float(tp1)
                risk_m = abs(me - sl)
                reward_m = abs(tp - me)
                rr_m = reward_m / risk_m if risk_m > 0 else 0
                risk_m_pips = risk_m / pip_size
                reward_m_pips = reward_m / pip_size
                risk_label = "\U0001f534 High risk" if risk_m_pips > 50 else ("\U0001f7e1 Medium risk" if risk_m_pips > 20 else "\U0001f7e2 Low risk")
                lines.append(f"\U0001f449 <b>Option A: MARKET</b> ({risk_label})")
                lines.append(f"   Entry: <code>{_fmt_num(market_entry)}</code> (now)")
                lines.append(f"   SL: <code>{_fmt_num(stop_loss)}</code> | TP: <code>{_fmt_num(tp1)}</code>")
                lines.append(f"   Risk: {risk_m_pips:.2f} pips | Reward: {reward_m_pips:.2f} pips | R:R {rr_m:.1f}")
                lines.append(f"   \u26a0 Immediate fill, price may slip")
            except (ValueError, TypeError):
                pass

        if limit_entry and stop_loss and tp1:
            try:
                le = float(limit_entry)
                sl = float(stop_loss)
                tp = float(tp1)
                risk_l = abs(le - sl)
                reward_l = abs(tp - le)
                rr_l = reward_l / risk_l if risk_l > 0 else 0
                risk_l_pips = risk_l / pip_size
                reward_l_pips = reward_l / pip_size
                prob_label = "\u2705 High probability" if rr_l >= 2.0 else ("\u26a0\ufe0f Medium probability" if rr_l >= 1.2 else "\u274c Low probability")
                lines.append("")
                lines.append(f"\U0001f449 <b>Option B: LIMIT</b> ({prob_label})")
                lines.append(f"   Entry: <code>{_fmt_num(limit_entry)}</code> (AI preferred)")
                lines.append(f"   SL: <code>{_fmt_num(stop_loss)}</code> | TP: <code>{_fmt_num(tp1)}</code>")
                lines.append(f"   Risk: {risk_l_pips:.2f} pips | Reward: {reward_l_pips:.2f} pips | R:R {rr_l:.1f}")
                lines.append(f"   \u2705 Better entry price, may not fill")
            except (ValueError, TypeError):
                pass

        if tp2:
            lines.append(f"   TP2: <code>{_fmt_num(tp2)}</code>")

        lines.append("")
        lines.append("<b>-- Execution Notes --</b>")
        if reason:
            lines.append(f"<i>{_escape_html(reason[:300])}</i>")
        if m5_trend == "ranging":
            lines.append(f"M5 is ranging \u2014 entry is aggressive. Safer: wait for M5 breakout or pullback rejection.")
        else:
            lines.append(f"M5 confirms direction \u2014 entry aligned with short-term momentum.")

        lines.append("")
        lines.append("<b>-- Management --</b>")
        lines.append("Move SL to BE after price reaches +1R.")
        lines.append("Partial close can be taken at TP1.")
        if stop_loss:
            lines.append(f"Invalid if price breaks and closes below/above {_fmt_num(stop_loss)}.")

    else:
        lines = [
            f"{d_emoji} <b>{_escape_html(symbol)} \u2014 {decision_str}</b>",
            "",
            f"<b>Bias:</b> D1 {d1_short} {align_emoji} | H1 {h1_short} {align_emoji}",
            f"<b>Confluence:</b> {_escape_html(hierarchy)}",
            f"<b>Confidence:</b> {confidence:.0%}",
            "",
            "<b>-- Multi-Timeframe Analysis --</b>",
            _tf_line(d1_section, "D1"),
            _tf_line(h1_section, "H1"),
            _tf_line(m5_section, "M5"),
        ]

        limit_recs = _build_limit_recommendation_text(payload)
        if limit_recs:
            lines.append("")
            lines.append("<b>-- Limit Rekomendasi --</b>")
            lines.append(limit_recs)

        if reason:
            lines.append("")
            lines.append(f"\U0001f4ac <i>{_escape_html(reason[:300])}</i>")

    if smc_probability_lines and decision_str in ("BUY", "SELL"):
        lines.append("")
        lines.extend(smc_probability_lines[1:])

    lines.append("")
    lines.append(f"\U0001f4ca Bid: {_fmt_num(bid)} | Ask: {_fmt_num(ask)} | Spread: {spread_pts} pts")

    approved = risk_result.get("approved")
    if not approved and decision_str in ("BUY", "SELL"):
        risk_reason = risk_result.get("reason", "")
        lines.append(f"\u274c Blocked: {_escape_html(str(risk_reason))}")

    return "\n".join(lines)


def _build_limit_recommendation_text(payload: dict) -> str:
    smc = payload.get("smc", {})
    major_trend = payload.get("major_trend", {})
    price = payload.get("current_price", {})
    mid = price.get("mid", 0)

    lines = []
    allowed = major_trend.get("allowed_directions", [])
    order_blocks = smc.get("order_blocks", {})
    demand = order_blocks.get("demand", []) or []
    supply = order_blocks.get("supply", []) or []

    if "BUY" in allowed and demand:
        nearest = demand[-1] if isinstance(demand[-1], dict) else {}
        low = nearest.get("low")
        high = nearest.get("high")
        if low and high and mid > 0:
            lines.append(f"\u2191 BUY LIMIT zone: {low} \u2013 {high}")
            if float(low) < mid:
                lines.append("   Price above zone \u2014 wait for retrace")
            else:
                lines.append("   Price inside zone \u2014 wait for confirmation")
            lines.append(f"   SL: below {low} | TP: next supply block")

    if "SELL" in allowed and supply:
        nearest = supply[-1] if isinstance(supply[-1], dict) else {}
        high_val = nearest.get("high")
        low_val = nearest.get("low")
        if high_val and low_val and mid > 0:
            lines.append(f"\u2193 SELL LIMIT zone: {low_val} \u2013 {high_val}")
            if float(high_val) > mid:
                lines.append("   Price below zone \u2014 wait for retrace")
            else:
                lines.append("   Price inside zone \u2014 wait for confirmation")
            lines.append(f"   SL: above {high_val} | TP: next demand block")

    return "\n".join(lines) if lines else ""


def format_signal_message(decision, risk_result: dict, symbol: str, market_payload: dict | None = None) -> str:
    return format_market_trend_alert(decision, symbol, market_payload=market_payload, risk_result=risk_result)


def _format_signal_message_legacy(decision, risk_result: dict, symbol: str) -> str:
    decision_str = getattr(decision, "decision", "HOLD")
    if hasattr(decision_str, "value"):
        decision_str = decision_str.value
    confidence = getattr(decision, "confidence", 0.0)
    entry_plan = getattr(decision, "entry_plan", None)
    stop_loss = getattr(entry_plan, "stop_loss", None) if entry_plan else None
    tp1 = getattr(entry_plan, "take_profit_1", None) if entry_plan else None
    tp2 = getattr(entry_plan, "take_profit_2", None) if entry_plan else None
    entry_type = getattr(entry_plan, "entry_type", None) if entry_plan else None
    entry_price = getattr(entry_plan, "preferred_entry_price", None) if entry_plan else None
    rr1 = getattr(entry_plan, "risk_reward_to_tp1", None) if entry_plan else None
    rr2 = getattr(entry_plan, "risk_reward_to_tp2", None) if entry_plan else None
    main_reason = getattr(decision, "main_reason", "")
    market_regime = getattr(decision, "market_regime", None)
    htf_bias = getattr(decision, "higher_timeframe_bias", None)
    etf_bias = getattr(decision, "entry_timeframe_bias", None)
    risk_notes = getattr(decision, "risk_notes", None)
    main_risk = getattr(risk_notes, "main_risk", "") if risk_notes else ""
    final_comment = getattr(decision, "final_comment", "")

    d_emoji = _decision_emoji(decision_str)
    c_emoji = _confidence_emoji(confidence)
    approved = risk_result.get("approved", False)
    reason = risk_result.get("reason", "")

    regime_str = ""
    if market_regime:
        regime_str = market_regime.value if hasattr(market_regime, "value") else str(market_regime)
    htf_str = ""
    if htf_bias:
        htf_str = htf_bias.value if hasattr(htf_bias, "value") else str(htf_bias)
    etf_str = ""
    if etf_bias:
        etf_str = etf_bias.value if hasattr(etf_bias, "value") else str(etf_bias)

    lines = [f"<b>\U0001f4e1 Trade Signal — {_escape_html(symbol)}</b>\n"]
    risk_badge = {"LOW": "\U0001f7e2 QUALITY: HIGH", "MEDIUM": "\U0001f7e1 QUALITY: MED", "HIGH": "\U0001f534 QUALITY: LOW"}.get(settings.risk_profile, "")
    lines.append(f"{d_emoji} <b>{decision_str}</b> | {c_emoji} {confidence:.0%} | {risk_badge}")
    if regime_str or htf_str or etf_str:
        trend_parts = []
        if htf_str:
            trend_parts.append(f"D1: {htf_str}")
        if etf_str:
            trend_parts.append(f"M5: {etf_str}")
        if regime_str:
            trend_parts.append(f"Regime: {regime_str}")
        lines.append(f"<b>Trend:</b> {' | '.join(trend_parts)}")

    if entry_type:
        lines.append(f"<b>Entry:</b> {_escape_html(str(entry_type))}")
    if entry_price:
        lines.append(f"<b>Entry Price:</b> {entry_price}")
    if stop_loss:
        lines.append(f"<b>Stop Loss:</b> {stop_loss}")
    if tp1:
        lines.append(f"<b>Take Profit 1:</b> {tp1}" + (f" (R:R {rr1:.1f})" if rr1 else ""))
    if tp2:
        lines.append(f"<b>Take Profit 2:</b> {tp2}" + (f" (R:R {rr2:.1f})" if rr2 else ""))

    if main_reason:
        lines.append(f"\n<b>Reason:</b> <i>{_escape_html(main_reason)}</i>")
    if main_risk:
        lines.append(f"<b>Risk:</b> <i>{_escape_html(main_risk)}</i>")

    status_emoji = "\u2705" if approved else "\u274c"
    lines.append(f"\n<b>Risk Check:</b> {status_emoji} {_escape_html(reason)}")

    if final_comment:
        lines.append(f"\n\U0001f4ac <i>{_escape_html(final_comment)}</i>")

    return "\n".join(lines)


def format_settings_message() -> str:
    style_map = {"LOW": "Swing", "MEDIUM": "Daytrade", "HIGH": "Scalp"}
    style = style_map.get(settings.risk_profile, settings.risk_profile)
    strategy_label = "SMC+AI" if settings.strategy_mode == "SMC_AI" else "AI Only"
    entry_tfs = "/".join(settings.effective_entry_tfs)
    sl_lo, sl_hi = settings.effective_sl_pip_range
    tp_lo, tp_hi = settings.effective_tp_pip_range
    noise_strictness = {"LOW": "strict", "MEDIUM": "lenient", "HIGH": "very lenient"}.get(settings.risk_profile, "lenient")

    return (
        "<b>\u2699\ufe0f Settings</b>\n\n"
        f"<b>Strategy:</b> {strategy_label}\n"
        f"<b>Profile:</b> {settings.risk_profile} \u2192 {style}\n"
        f"<b>Entry TF:</b> {entry_tfs} | <b>Hold:</b> {settings.effective_hold_time}\n"
        f"<b>Min Conf:</b> {settings.effective_min_confidence:.0%} | <b>Min R:R:</b> {settings.effective_min_risk_reward}\n"
        f"<b>SL range:</b> {sl_lo}-{sl_hi} pips | <b>TP range:</b> {tp_lo}-{tp_hi} pips\n"
        f"<b>Noise filter:</b> {noise_strictness} ({settings.risk_profile})\n"
        f"<b>Mode:</b> <code>{_escape_html(settings.bot_mode)}</code>\n"
        f"<b>Symbols:</b> <code>{_escape_html(settings.default_symbols or settings.default_symbol)}</code>\n"
        f"<b>Risk/Trade:</b> {settings.risk_per_trade_percent}%\n"
        f"<b>Max Daily DD:</b> {settings.max_daily_drawdown_percent}%\n"
        f"<b>Max Positions:</b> {settings.max_open_positions}\n"
        f"<b>Interval:</b> {settings.effective_loop_interval}s{' (auto)' if settings.trading_loop_interval_seconds == 0 else ''}\n"
        f"<b>Live Trading:</b> {_bool_emoji(settings.live_trading_enabled)}"
    )


def format_decision_for_telegram(decision) -> str:
    decision_str = getattr(decision, "decision", "HOLD")
    if hasattr(decision_str, "value"):
        decision_str = decision_str.value
    confidence = getattr(decision, "confidence", 0.0)
    entry_plan = getattr(decision, "entry_plan", None)
    stop_loss = getattr(entry_plan, "stop_loss", None) if entry_plan else None
    tp1 = getattr(entry_plan, "take_profit_1", None) if entry_plan else None
    tp2 = getattr(entry_plan, "take_profit_2", None) if entry_plan else None
    rr1 = getattr(entry_plan, "risk_reward_to_tp1", None) if entry_plan else None
    rr2 = getattr(entry_plan, "risk_reward_to_tp2", None) if entry_plan else None
    entry_type = getattr(entry_plan, "entry_type", None) if entry_plan else None
    entry_price = getattr(entry_plan, "preferred_entry_price", None) if entry_plan else None
    main_reason = getattr(decision, "main_reason", "")
    market_regime = getattr(decision, "market_regime", None)
    htf_bias = getattr(decision, "higher_timeframe_bias", None)
    etf_bias = getattr(decision, "entry_timeframe_bias", None)
    final_comment = getattr(decision, "final_comment", "")

    d_emoji = _decision_emoji(decision_str)
    c_emoji = _confidence_emoji(confidence)

    lines = [f"{d_emoji} <b>{decision_str}</b> | Confidence: {c_emoji} {confidence:.0%}"]

    if entry_type:
        lines.append(f"<b>Entry:</b> {_escape_html(str(entry_type))}")
    if entry_price:
        lines.append(f"<b>Entry Price:</b> {entry_price}")
    if stop_loss:
        lines.append(f"<b>SL:</b> {stop_loss}")
    if tp1:
        lines.append(f"<b>TP1:</b> {tp1}" + (f" (R:R {rr1:.1f})" if rr1 else ""))
    if tp2:
        lines.append(f"<b>TP2:</b> {tp2}" + (f" (R:R {rr2:.1f})" if rr2 else ""))

    if market_regime:
        regime_str = market_regime.value if hasattr(market_regime, "value") else str(market_regime)
        lines.append(f"<b>Regime:</b> {_escape_html(regime_str)}")
    if htf_bias:
        htf_str = htf_bias.value if hasattr(htf_bias, "value") else str(htf_bias)
        lines.append(f"<b>HTF:</b> {_escape_html(htf_str)}")
    if etf_bias:
        etf_str = etf_bias.value if hasattr(etf_bias, "value") else str(etf_bias)
        lines.append(f"<b>Entry TF:</b> {_escape_html(etf_str)}")

    if main_reason:
        lines.append(f"<i>{_escape_html(main_reason)}</i>")
    if final_comment:
        lines.append(f"<i>{_escape_html(final_comment)}</i>")

    return "\n".join(lines)
