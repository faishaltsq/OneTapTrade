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


def build_main_menu_keyboard(is_paused: bool = True, mode: str = "SIGNAL_ONLY", active_symbol: str = "ALL") -> "InlineKeyboardMarkup":
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    pause_btn = InlineKeyboardButton("\u25b6\ufe0f Resume" if is_paused else "\u23f8\ufe0f Pause", callback_data="MENU_TOGGLE_PAUSE")
    mode_label = {"SIGNAL_ONLY": "Signal", "SEMI_AUTO": "Semi-Auto", "AUTO_DEMO": "Auto Demo", "LIVE_AUTO": "Live"}.get(mode, mode)

    keyboard = [
        [
            InlineKeyboardButton("\U0001f4ca Status", callback_data="MENU_STATUS"),
            InlineKeyboardButton("\U0001f4cb Positions", callback_data="MENU_POSITIONS"),
        ],
        [
            InlineKeyboardButton("\U0001f4e1 Last Signal", callback_data="MENU_LAST_SIGNAL"),
            InlineKeyboardButton("\u2699\ufe0f Settings", callback_data="MENU_SETTINGS"),
        ],
        [
            InlineKeyboardButton(f"\U0001f4ca All Pairs", callback_data="MENU_SYMBOL_ALL"),
            InlineKeyboardButton(f"\U0001f504 Next Pair", callback_data="MENU_SYMBOL_NEXT"),
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

    keyboard = [
        [
            InlineKeyboardButton("🟢 Low", callback_data="MENU_RISK_LOW"),
            InlineKeyboardButton("🟡 Med", callback_data="MENU_RISK_MEDIUM"),
            InlineKeyboardButton("🔴 High", callback_data="MENU_RISK_HIGH"),
        ],
        [
            InlineKeyboardButton("Risk 0.25%", callback_data="MENU_RISK_TRADE_025"),
            InlineKeyboardButton("Risk 0.5%", callback_data="MENU_RISK_TRADE_050"),
            InlineKeyboardButton("Risk 1%", callback_data="MENU_RISK_TRADE_100"),
        ],
        [InlineKeyboardButton("⬅️ Back/Menu", callback_data="MENU_BACK")],
    ]
    return InlineKeyboardMarkup(keyboard)


def format_welcome_message() -> str:
    return (
        "<b>\U0001f916 OneTapTrade AI Trading Bot</b>\n\n"
        "<b>Commands:</b>\n"
        "/start - Show this message\n"
        "/status - Bot status &amp; account summary\n"
        "/positions - Open positions\n"
        "/last_signal - Latest AI decision\n"
        "/settings - Risk settings\n"
        "/pause - Pause trading loop\n"
        "/resume - Resume trading loop\n"
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
        lines.append("\n\u23f8\ufe0f <b>TRADING PAUSED</b>")

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


def format_market_trend_alert(decision, symbol: str, market_payload: dict | None = None, risk_result: dict | None = None) -> str:
    payload = market_payload or {}
    risk_result = risk_result or {}
    decision_str = _enum_value(getattr(decision, "decision", "HOLD"))
    confidence = getattr(decision, "confidence", 0.0) or 0.0
    reason = getattr(decision, "main_reason", "") or getattr(decision, "final_comment", "") or "No clear trade setup."
    d_emoji = _decision_emoji(decision_str)
    c_emoji = _confidence_emoji(confidence)

    lines = [f"<b>📊 Market Trend — {_escape_html(symbol)}</b>"]
    lines.append(f"{d_emoji} <b>Decision:</b> {_escape_html(decision_str)} | {c_emoji} <b>Confidence:</b> {confidence:.0%}")
    lines.extend(_format_bias_map(decision, payload))
    lines.extend(_format_price(payload))
    lines.extend(_format_momentum(payload))
    lines.extend(_format_smc(payload))
    lines.extend(_format_orderflow(payload))

    if decision_str in ("BUY", "SELL"):
        lines.extend(_format_trade_plan(decision))
        approved = risk_result.get("approved")
        risk_reason = risk_result.get("reason", "N/A")
        status = "✅ Approved" if approved else "❌ Blocked"
        lines.extend(["\n<b>🛡️ Risk Check</b>", f"{status}: {_escape_html(str(risk_reason))}"])

    lines.extend(["\n<b>📝 Read</b>", f"<i>{_escape_html(reason)}</i>"])
    return "\n".join(lines)


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
    return (
        "<b>\u2699\ufe0f Scalping Settings</b>\n\n"
        f"<b>Risk Profile:</b> <code>{_escape_html(settings.risk_profile)}</code>\n"
        f"<b>Mode:</b> <code>{_escape_html(settings.bot_mode)}</code>\n"
        f"<b>Symbols:</b> <code>{_escape_html(settings.default_symbols or settings.default_symbol)}</code>\n"
        f"<b>Risk/Trade:</b> {settings.risk_per_trade_percent}%\n"
        f"<b>Max Daily DD:</b> {settings.max_daily_drawdown_percent}%\n"
        f"<b>Min Confidence:</b> {settings.effective_min_confidence:.0%}\n"
        "<b>SL/TP:</b> AI-owned\n"
        f"<b>Max Positions:</b> {settings.max_open_positions}\n"
        f"<b>Interval:</b> {settings.trading_loop_interval_seconds}s\n"
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
