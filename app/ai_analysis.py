import json
from typing import Any

import httpx

from app.config import settings

SIGNAL_FORMAT = """⚪ {PAIR} — {BUY / SELL / WAIT}

Bias: {Bullish/Bearish/Neutral}
Confidence: {0–100}%

Entry: {WAIT / MARKET / LIMIT + harga / area entry}
SL: {harga SL}
TP1: {harga TP1}
TP2: {harga TP2}

Reason:
{Alasan singkat AI dalam 1–2 kalimat.}

Invalid jika:
{syarat setup batal}

Risk:
Gunakan lot sesuai manajemen risiko."""

DAYTRADE_PLAYBOOK = """FOREX DAY-TRADE METHOD:
- Trade horizon: intraday only. Do not force swing-trade assumptions.
- Bias filter: align signal with trend, market structure, and visible support/resistance. Prefer continuation after pullback or breakout-retest; allow reversal only after clear liquidity sweep and rejection.
- Entry quality: BUY/SELL only when there is a defensible trigger around current price or a precise LIMIT area. If entry is late, chasing, inside chop, or far from invalidation, choose WAIT.
- Liquidity and structure: identify recent swing highs/lows, breakout levels, failed breaks, support/resistance, supply/demand, and stop-loss liquidity when available from chart context.
- Momentum/volatility: use OHLCV summary and indicator_values when present. Avoid trades when volatility is too compressed, candles are indecisive, or momentum conflicts with the bias.
- Session awareness: prefer London, New York, or London-New York overlap behavior. If session/news context is unavailable, do not invent it; reduce confidence or choose WAIT.
- Risk quality: for BUY/SELL, SL must sit beyond invalidation structure, not an arbitrary fixed distance. TP1 should target the nearest realistic level; TP2 should target the next structure/liquidity area.
- Minimum quality gate: only output BUY/SELL when confidence is at least {min_confidence}% and expected reward:risk is at least 1:{min_rr}. Otherwise output WAIT.
- Be selective. A high-quality WAIT is better than a weak BUY/SELL."""


def _safe_value(value: Any, fallback: str = "-") -> str:
    if value in (None, ""):
        return fallback
    return str(value)


def _percent_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    text = str(value).replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _float_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _price_precision(value: float) -> int:
    if value >= 1000:
        return 3
    if value >= 100:
        return 3
    if value >= 10:
        return 4
    return 5


def _format_price(value: float | None, reference: float | None = None) -> str:
    if value is None:
        return "N/A"
    precision = _price_precision(reference if reference is not None else value)
    return f"{value:.{precision}f}"


def build_chart_analysis_prompt(context: dict[str, Any], signal: dict[str, Any] | None = None) -> str:
    compact_context = {
        "signal": signal,
        "chart": {
            "status": context.get("status"),
            "state": context.get("state"),
            "quote": context.get("quote"),
            "ohlcv_summary": context.get("ohlcv_summary"),
            "indicator_values": context.get("indicator_values"),
        },
    }
    return (
        f"Analyze this TradingView chart context as a DeepSeek-powered {settings.ai_trading_style} signal-only assistant. "
        "Return ONLY the exact plain-text template below. Do not add markdown, bullets, disclaimers, or extra sections. "
        "Use BUY, SELL, or WAIT. Entry must explicitly choose WAIT, MARKET, or LIMIT. "
        "For WAIT, write Entry: WAIT - no trade and SL/TP as N/A. "
        "For BUY/SELL, choose MARKET only when price is already at a valid trigger; otherwise choose LIMIT with an entry area. "
        "For BUY/SELL, always provide numeric SL, TP1, and TP2 based on visible support/resistance/structure. "
        "Confidence must reflect setup quality, not certainty of profit. "
        "Use Indonesian for Reason and Invalid jika. Reason must be 1-2 concise sentences. "
        "If the setup is unclear or levels are not defensible, use WAIT.\n\n"
        f"{DAYTRADE_PLAYBOOK.format(min_confidence=settings.ai_min_trade_confidence, min_rr=settings.ai_min_rr)}\n\n"
        f"TEMPLATE:\n{SIGNAL_FORMAT}\n\n"
        f"DATA:\n{json.dumps(compact_context, ensure_ascii=False, indent=2)}"
    )


def fallback_signal_message(context: dict[str, Any], signal: dict[str, Any] | None = None) -> str:
    signal = signal or {}
    state = context.get("state") or {}
    quote = context.get("quote") or {}
    summary = context.get("ohlcv_summary") or {}

    pair = _safe_value(signal.get("symbol") or state.get("symbol") or quote.get("symbol") or settings.default_symbol)
    action = str(signal.get("action") or signal.get("decision") or "WAIT").upper()
    if action not in {"BUY", "SELL", "WAIT"}:
        action = "WAIT"

    change_pct = _percent_float(summary.get("change_pct"))
    if action == "BUY":
        bias = "Bullish"
    elif action == "SELL":
        bias = "Bearish"
    elif change_pct > 0.3:
        bias = "Bullish"
    elif change_pct < -0.3:
        bias = "Bearish"
    else:
        bias = "Neutral"

    confidence = signal.get("confidence")
    if confidence is None:
        confidence = 50 if action in {"BUY", "SELL"} else 35
    try:
        confidence = int(float(confidence) * 100) if float(confidence) <= 1 else int(float(confidence))
    except (TypeError, ValueError):
        confidence = 35
    confidence = max(0, min(100, confidence))

    current_price_number = _float_value(signal.get("price") or signal.get("entry") or quote.get("last") or quote.get("close"))
    chart_range = _float_value(summary.get("range"))
    if current_price_number is not None and chart_range:
        risk_distance = max(chart_range * 0.08, current_price_number * 0.001)
    elif current_price_number is not None:
        risk_distance = current_price_number * 0.001
    else:
        risk_distance = None

    order_type = str(signal.get("order_type") or signal.get("entry_type") or "MARKET").upper()
    if order_type not in {"MARKET", "LIMIT"}:
        order_type = "MARKET"

    if action == "WAIT":
        entry = "WAIT - no trade"
        sl = "N/A"
        tp1 = "N/A"
        tp2 = "N/A"
    else:
        entry_price = _float_value(signal.get("entry") or signal.get("entry_price")) or current_price_number
        entry = f"{order_type} {_format_price(entry_price, current_price_number)}"
        explicit_sl = _float_value(signal.get("stop_loss") or signal.get("sl"))
        explicit_tp1 = _float_value(signal.get("take_profit_1") or signal.get("tp1") or signal.get("take_profit"))
        explicit_tp2 = _float_value(signal.get("take_profit_2") or signal.get("tp2"))

        if explicit_sl is not None:
            sl = _format_price(explicit_sl, current_price_number)
        elif current_price_number is not None and risk_distance is not None:
            sl = _format_price(current_price_number - risk_distance if action == "BUY" else current_price_number + risk_distance, current_price_number)
        else:
            sl = "N/A"

        if explicit_tp1 is not None:
            tp1 = _format_price(explicit_tp1, current_price_number)
        elif current_price_number is not None and risk_distance is not None:
            tp1 = _format_price(current_price_number + risk_distance * 1.5 if action == "BUY" else current_price_number - risk_distance * 1.5, current_price_number)
        else:
            tp1 = "N/A"

        if explicit_tp2 is not None:
            tp2 = _format_price(explicit_tp2, current_price_number)
        elif current_price_number is not None and risk_distance is not None:
            tp2 = _format_price(current_price_number + risk_distance * 2.5 if action == "BUY" else current_price_number - risk_distance * 2.5, current_price_number)
        else:
            tp2 = "N/A"

    if action == "WAIT":
        reason = signal.get("message") or (
            f"Chart {pair} terbaca dari TradingView MCP di sekitar harga {_format_price(current_price_number, current_price_number)}; perubahan 100 bar sekitar {summary.get('change_pct', 'n/a')}. "
            "Belum ada entry yang cukup valid, jadi posisi terbaik adalah menunggu konfirmasi."
        )
        invalid = signal.get("invalid_if") or "WAIT batal jika muncul breakout/retest valid dengan struktur SL dan target yang jelas."
    else:
        reason = signal.get("message") or (
            f"Chart {pair} terbaca dari TradingView MCP; perubahan 100 bar sekitar {summary.get('change_pct', 'n/a')}. "
            "Level entry, SL, dan TP fallback dihitung dari range chart terakhir karena analisis AI tidak tersedia."
        )
        invalid = signal.get("invalid_if") or "Setup batal jika harga menembus SL atau struktur berbalik melawan bias setup."

    return (
        f"⚪ {pair} — {action}\n\n"
        f"Bias: {bias}\n"
        f"Confidence: {confidence}%\n\n"
        f"Entry: {entry}\n"
        f"SL: {sl}\n"
        f"TP1: {tp1}\n"
        f"TP2: {tp2}\n\n"
        f"Reason:\n{reason}\n\n"
        f"Invalid jika:\n{invalid}\n\n"
        "Risk:\nGunakan lot sesuai manajemen risiko."
    )


def formatted_signal_message(
    context: dict[str, Any],
    signal: dict[str, Any] | None = None,
    ai_analysis: dict[str, Any] | None = None,
) -> str:
    if ai_analysis and ai_analysis.get("success") and ai_analysis.get("analysis"):
        return str(ai_analysis["analysis"]).strip()
    return fallback_signal_message(context, signal)


async def analyze_chart_context(context: dict[str, Any], signal: dict[str, Any] | None = None) -> dict[str, Any]:
    if not settings.ai_enabled:
        return {"success": False, "configured": False, "analysis": None}

    url = settings.ai_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.ai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a cautious DeepSeek forex day-trading chart analyst. "
                    "Your job is to improve selectivity and signal quality, not to predict with certainty. "
                    "You never execute trades. You must follow the requested output format exactly."
                ),
            },
            {"role": "user", "content": build_chart_analysis_prompt(context, signal)},
        ],
        "temperature": 0.2,
        "max_tokens": 700,
    }
    headers = {"Authorization": f"Bearer {settings.ai_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return {
            "success": True,
            "configured": True,
            "model": settings.ai_model,
            "analysis": content,
        }
    except Exception as e:
        return {
            "success": False,
            "configured": True,
            "model": settings.ai_model,
            "analysis": None,
            "error": str(e),
        }
