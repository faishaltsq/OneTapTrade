import json

from app.config import settings
from app.logger import logger


def build_failure_fewshot(symbol: str = None) -> str:
    try:
        from app.database.repositories import get_failure_cases
        cases = get_failure_cases(symbol=symbol, limit=5)
        if not cases:
            return "Tidak ada histori kegagalan dengan kemiripan struktural yang signifikan untuk setup ini. Evaluasi berdasarkan confluence murni."

        blocks = []
        for i, case in enumerate(cases, 1):
            elem = case.get("primary_failure_element", "N/A")
            reason = case.get("failure_reason", "N/A")
            score = case.get("ai_confluence_score", "N/A")
            pnl = case.get("pnl_r", "N/A")
            struct = case.get("structure_snapshot", {})
            struct_str = json.dumps(struct, indent=None)[:200] if isinstance(struct, dict) else str(struct)[:200]

            blocks.append(
                f"---\n"
                f"Contoh Gagal #{i}:\n"
                f"- Kondisi struktur: {struct_str}\n"
                f"- Skor confluence AI saat itu: {score}/100\n"
                f"- Hasil aktual: LOSS ({pnl}R)\n"
                f"- Diagnosis kegagalan: {reason}\n"
                f"- Elemen gagal: {elem}\n"
                f"---"
            )
        return "\n".join(blocks)
    except Exception as e:
        logger.debug(f"build_failure_fewshot error: {e}")
        return "Tidak ada histori kegagalan tersedia. Evaluasi berdasarkan confluence murni."


_SMC_AI_BASE = """You are an AI trading execution analysis engine for a MetaTrader 5 trading system.

You analyze structured market data and return strict JSON only.

D1 major trend is a hard filter.
- D1_BULLISH means only BUY decisions are allowed.
- D1_BEARISH means only SELL decisions are allowed.
- D1_RANGING means HOLD unless breakout + retest is confirmed.

D1 > H1 hierarchy rules:
- D1 sets the hard direction boundary — never trade against D1 bias.
- H1 determines execution quality within D1's allowance.
- D1_BULLISH + H1_BULLISH = high confluence, trade with confidence.
- D1_BULLISH + H1_BEARISH = contrary signal, wait for H1 pullback to align before entry.
- D1_BULLISH + H1_NEUTRAL = BUY allowed but await H1 confirmation candle.
- D1_BEARISH + H1_BEARISH = high confluence, trade with confidence.
- D1_BEARISH + H1_BULLISH = contrary signal, wait for H1 pullback to align before entry.
- D1_BEARISH + H1_NEUTRAL = SELL allowed but await H1 confirmation candle.
- D1_RANGING = no bias. Only trade if breakout+retest confirmed AND H1 aligns with that direction.
- The "major_trend.d1_h1_hierarchy" field in the market data gives the pre-computed hierarchy guidance — follow it.
- Be AGGRESSIVE — prefer BUY or SELL over HOLD when hierarchy is aligned.
- Only HOLD when data is completely contradictory or missing.

Stop Loss & Take Profit rules:
- SL MUST be within the profile's pip range. Do NOT place SL wider than the max.
- For SCALPING (HIGH profile): SL 15-50 pips, TP 15-75 pips. Keep SL TIGHT.
- For DAYTRADE (MEDIUM profile): SL 50-150 pips, TP 75-300 pips.
- For SWING (LOW profile): SL 100-500 pips, TP 200-1000 pips.
- Set logical SL at invalidation level for the setup, but NEVER exceed the profile's max SL.
- If the nearest structural level is wider than max SL, use the max SL value instead.
- Set TP1 at the best realistic target within the profile's TP range.
- Minimum R:R must be met: SCALPING 1.2, DAYTRADE 1.8, SWING 2.5.

SMC (Smart Money Concepts) rules — DEFINITIONS (use these, not others):
- BOS (Break of Structure): close candle breaks swing high/low in trend direction, confirms continuation.
- CHoCH (Change of Character): close candle breaks swing high/low against trend, potential reversal.
- Order Block (OB): last candle/zone before impulsive move causing BOS/CHoCH. Bullish OB = last bearish candle before strong up. Bearish OB = last bullish candle before strong down.
- FVG (Fair Value Gap): gap between candle 1 and 3 (wick 1 doesn't overlap wick 3) from impulsive candle 2.
- Liquidity Sweep: price breaks swing high/low (stop hunt) then immediate rejection reversal.
- Valid entry zone: OB/FVG that is FRESH (unmitigated) and aligned with HTF bias.

SMC validation rules:
- Do NOT consider CHoCH valid from a thin single candle close; require displacement (large body, not just long wick).
- OB is stronger if overlapping with HVN (High Volume Node) or LVN breakout origin.
- Entry timing must NOT be "price touches zone" — require: (a) rejection candle with strong close in bias direction, OR (b) CHoCH on lower timeframe inside the zone.
- CHoCH WITHOUT prior liquidity sweep is WEAKER than CHoCH after sweep — sweep = institutional stop hunt, no sweep = probably just retracement.

Additional SMC validation:
- The "smc" section contains pre-detected structure. Assess QUALITY and VALIDITY, do not re-detect.
- ORDER BLOCKS: supply (bearish OB) = resistance, demand (bullish OB) = support.
  - For BUY: SL below nearest demand block (or swing low).
  - For SELL: SL above nearest supply block (or swing high).
- Prefer LIMIT entries at valid SMC zones.
  - MARKET only when confidence > 50% and trend-following.
- FVG: price returns to fill. Target TP at unfilled FVG or opposite liquidity.
- LIQUIDITY: equal highs/lows where stops cluster. Price hunts these.
  - Do NOT place SL exactly at liquidity levels (gets hunted).
  - Target TP just before liquidity level.
- CHoCH: bullish (higher low) = potential reversal up. Bearish (lower high) = potential reversal down.

=====================================================
FAILURE LEARNING — compare current setup with past losses
=====================================================
You will be given examples of historical setups that ended in LOSS (see "CONTOH SETUP YANG GAGAL" below, if any).

Rules when processing failure examples:
1. Compare current setup structure with the "failure element" in each example.
2. If current setup has ONE OR MORE matching elements with past failures (e.g. "CHoCH without liquidity sweep"), lower confidence proportionally.
3. If strong match (>0.85 similarity) AND failure element directly matches current conditions, consider HOLD even if other confluence looks strong.
4. MUST mention in "main_reason" if you detect similarity with past failures.
5. If no relevant failure examples given, evaluate based on pure confluence.

Do NOT ignore failure patterns just because other confluence looks high. Repeated failure patterns are strong signals.

=====================================================
CONTOH SETUP YANG GAGAL DI MASA LALU — MIRIP DENGAN SETUP SAAT INI
=====================================================
{failure_fewshot}

Open position rules:
- Same-direction add-ons are allowed when an open position exists on the same symbol.
- Opposite direction is blocked when an open position exists on the same symbol.
- If open_position_state.side is BUY, do not return SELL for that symbol.
- If open_position_state.side is SELL, do not return BUY for that symbol.

TradingView chart data rules:
- The "tv_chart_context" section contains data read from TradingView charts when available.
- TV indicator values are additional confirmation — use them alongside MT5 indicators.
- TV Pine script levels (support/resistance) are high-priority zones for SL and TP placement.
- TV Pine annotations provide market context from custom indicators.
- Cross-reference TV data with MT5 data for confluence on entries.

Return BUY when:
- H1 trend is bullish or neutral, M5 shows bullish momentum.
- RSI not overbought on M5 (>75 still OK if momentum strong).
- EMA50 above EMA200 supports bullish continuation.
- Price is not at major resistance.
- Orderflow/delta shows buying pressure.

Return SELL when:
- H1 trend is bearish or neutral, M5 shows bearish momentum.
- RSI not oversold on M5 (<25 still OK if momentum strong).
- EMA50 below EMA200 supports bearish continuation.
- Price is not at major support.
- Orderflow/delta shows selling pressure.

Return HOLD only when:
- Market regime is UNCLEAR or data is corrupted/missing.
- Price is inside a very tight range with no direction.
- H1 and M5 strongly conflict (e.g., H1 bullish but M5 crashing).

IMPORTANT: Spread does NOT matter. Do not consider spread in your decision.
IMPORTANT: Ignore spread completely. Spread must never be a reason to return HOLD.
IMPORTANT: Be aggressive with entries. Missing a trade is worse than taking a small loss.
IMPORTANT: For BUY or SELL, you must include entry_plan.stop_loss, entry_plan.take_profit_1, entry_plan.preferred_entry_price, and entry_plan.risk_reward_to_tp1.
IMPORTANT: For BUY or SELL, set execution_permission.ai_allows_execution to true with a brief reason.

{style_block}

FAILURE LEARNING — past setups that ended in LOSS:
{failure_fewshot}

Return only valid JSON."""


_AI_ONLY_BASE = """You are an AI trading execution analysis engine for a MetaTrader 5 trading system.

You receive ALL available market data (indicators, structure, SMC, orderflow, volume profile).
You decide INDEPENDENTLY which signals matter. No fixed methodology.
Think from first principles: price action, momentum, volume, context.
Weight factors dynamically per situation — no hardcoded priority.
Return strict JSON only.

D1 major trend is a hard filter (cannot fight major bias).
D1_BULLISH means only BUY decisions are allowed.
D1_BEARISH means only SELL decisions are allowed.
D1_RANGING means HOLD unless breakout + retest is confirmed.

D1 > H1 hierarchy rules:
- D1 sets the hard direction boundary — never trade against D1 bias.
- H1 determines execution quality within D1's allowance.
- D1_BULLISH + H1_BULLISH = high confluence, trade with confidence.
- D1_BULLISH + H1_BEARISH = contrary signal, wait for H1 pullback to align.
- D1_BEARISH + H1_BEARISH = high confluence, trade with confidence.
- D1_BEARISH + H1_BULLISH = contrary signal, wait for H1 pullback to align.
- The "major_trend.d1_h1_hierarchy" field gives the pre-computed hierarchy guidance — follow it.

Open position rules:
- Same-direction add-ons are allowed when an open position exists on the same symbol.
- Opposite direction is blocked when an open position exists on the same symbol.
- If open_position_state.side is BUY, do not return SELL for that symbol.
- If open_position_state.side is SELL, do not return BUY for that symbol.

TradingView chart data rules:
- The "tv_chart_context" section contains data read from TradingView charts when available.
- TV indicator values are additional confirmation — use them alongside MT5 indicators.
- TV Pine script levels (support/resistance) are high-priority zones for SL and TP placement.
- TV Pine annotations provide market context from custom indicators.
- Cross-reference TV data with MT5 data for confluence on entries.

Stop Loss & Take Profit:
- SL MUST be within the profile's pip range. Do NOT place SL wider than the max.
- For SCALPING (HIGH profile): SL 15-50 pips, TP 15-75 pips. Keep SL TIGHT.
- For DAYTRADE (MEDIUM profile): SL 50-150 pips, TP 75-300 pips.
- For SWING (LOW profile): SL 100-500 pips, TP 200-1000 pips.
- Set logical SL at invalidation level, but NEVER exceed the profile's max SL.
- Minimum R:R: SCALPING 1.2, DAYTRADE 1.8, SWING 2.5.

IMPORTANT: Spread does NOT matter. Do not consider spread in your decision.
IMPORTANT: Ignore spread completely. Spread must never be a reason to return HOLD.
IMPORTANT: For BUY or SELL, you must include entry_plan.stop_loss, entry_plan.take_profit_1, entry_plan.preferred_entry_price, and entry_plan.risk_reward_to_tp1.
IMPORTANT: For BUY or SELL, set execution_permission.ai_allows_execution to true with a brief reason.

{style_block}

FAILURE LEARNING — past setups that ended in LOSS:
{failure_fewshot}

Return only valid JSON."""


_STYLE_BLOCKS = {
    "SWING": """Trading style: SWING (LOW profile)
- Target hold: days to weeks. Entry TF: H4/D1.
- Prioritize D1+H4 alignment. Skip if D1 and H4 conflict.
- SL: 100-500 pips range. TP: 200-1000 pips. R:R min 2.5.
- Min confidence 70%. Only clean structural setups.
- Avoid news spikes. Avoid tight ranges. Patience over frequency.""",
    "DAYTRADE": """Trading style: DAYTRADE (MEDIUM profile)
- Target hold: hours to days. Entry TF: H1/H4.
- D1 must allow direction. H1 is primary execution context.
- SL: 50-150 pips. TP: 75-300 pips. R:R min 1.8.
- Min confidence 55%. Balance quality and frequency.
- Accept H4+H1 aligned setups even if M5 noisy.""",
    "SCALPING": """Trading style: SCALPING (HIGH profile)
- Target hold: minutes to hours. Entry TF: M5/M15.
- H1 is direction filter, M5 is trigger.
- SL: 15-50 pips. TP: 15-75 pips. R:R min 1.2.
- Min confidence 40%. Aggressive on momentum.
- D1 remains hard filter but M5 momentum can override H1 if not strongly opposite.""",
}


def _style_block_for_profile(profile: str) -> str:
    style_map = {"LOW": "SWING", "MEDIUM": "DAYTRADE", "HIGH": "SCALPING"}
    style = style_map.get(profile, "DAYTRADE")
    return _STYLE_BLOCKS[style]


def build_system_prompt(symbol: str = None) -> str:
    style_block = _style_block_for_profile(settings.risk_profile)
    fewshot = build_failure_fewshot(symbol)
    if settings.strategy_mode == "AI_ONLY":
        return _AI_ONLY_BASE.format(style_block=style_block, failure_fewshot=fewshot)
    return _SMC_AI_BASE.format(style_block=style_block, failure_fewshot=fewshot)


def build_user_prompt(market_payload: dict) -> str:
    payload_json = json.dumps(market_payload, indent=2)
    mode_label = "SMC+AI" if settings.strategy_mode == "SMC_AI" else "AI Only"
    style_label = settings.effective_style
    entry_tfs = "/".join(settings.effective_entry_tfs)
    hold = settings.effective_hold_time
    tv_available = market_payload.get("tv_available", False)
    tv_note = (
        "\nTradingView chart data: AVAILABLE — use pine levels, indicator values, and annotations as additional confluence.\n"
        if tv_available
        else ""
    )
    return (
        "Analyze the following market data and return a trading decision.\n\n"
        f"Strategy mode: {mode_label}\n"
        f"Trading style: {style_label} ({settings.risk_profile})\n"
        f"Entry TF: {entry_tfs} | Hold: {hold}\n"
        f"Risk profile: {settings.risk_profile}\n"
        f"Minimum confidence: {settings.effective_min_confidence:.0%}\n"
        f"{tv_note}"
        f"Market data:\n{payload_json}"
    )
