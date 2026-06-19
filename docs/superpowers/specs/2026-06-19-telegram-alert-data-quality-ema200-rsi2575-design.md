# Telegram Alert Data Quality, EMA200, And RSI 25/75 Design

## Goal

Improve Telegram market trend alerts so they show real computed data whenever possible, use EMA50/EMA200 instead of EMA20/EMA50, and classify RSI with oversold at 25 and overbought at 75.

## Scope

- Replace market alert `N/A` labels with real payload-derived data when available.
- Replace remaining fallback display text with Indonesian-friendly terms:
  - `Menunggu data` when data is unavailable.
  - `Belum ada bias jelas` when data exists but direction is neutral or unclear.
- Compute and expose EMA200 in market payload indicators.
- Use EMA50/EMA200 for trend and momentum display.
- Update DeepSeek prompt RSI thresholds from 30/70 to 25/75.
- Keep existing AI schema and trading modes unchanged.

## Current Problems

- Telegram alert displays `N/A` and `UNCLEAR` in several sections, even when enough indicator data exists to infer context.
- Momentum section says `EMA20/50`, while requested strategy uses `EMA50/200`.
- Prompt still describes RSI overbought/oversold as 70/30.
- Some missing data is real broker/API limitation, especially DOM/depth data. Those fields should not be faked.

## Data Rules

### Indicators

`app.analysis.feature_builder._safe_indicators()` will return:

```python
{
    "ema_50": float | None,
    "ema_200": float | None,
    "rsi_14": float | None,
    "rsi_state": "OVERSOLD" | "NORMAL" | "OVERBOUGHT" | "MENUNGGU_DATA",
    "atr_14": float | None,
}
```

RSI state rules:

- `rsi_14 is None` -> `MENUNGGU_DATA`
- `rsi_14 < 25` -> `OVERSOLD`
- `rsi_14 > 75` -> `OVERBOUGHT`
- otherwise -> `NORMAL`

EMA bias rules:

- missing EMA50 or EMA200 -> `Menunggu data`
- EMA50 > EMA200 -> `Bullish`
- EMA50 < EMA200 -> `Bearish`
- equal -> `Belum ada bias jelas`

### Bias Map

Formatter will prefer real timeframe market structure when clear. If market structure is missing or `UNCLEAR`, it will fallback to EMA50/EMA200 bias from that timeframe indicators.

If both structure and EMA bias cannot determine direction:

- return `Menunggu data` when bars/indicators are missing.
- return `Belum ada bias jelas` when data exists but direction is neutral/unclear.

### Orderflow

Orderflow data must not be invented.

- Missing DOM/depth -> `Menunggu data`
- Missing delta proxy -> `Menunggu data`
- Existing delta direction/bias -> show actual value

## Telegram Output Changes

Momentum lines become:

```text
M5 RSI: 41.8 (Normal) | EMA50/200: Bearish
H1 RSI: 48.9 (Normal) | EMA50/200: Bearish
```

Fallback wording examples:

```text
D1: Bullish | H4: Menunggu data
H1: Bearish | M5: Belum ada bias jelas
Delta: Menunggu data
DOM: Menunggu data
```

No `N/A` or `UNCLEAR` should appear in market trend alert sections.

## Prompt Changes

`app.ai_engine.prompt_builder.SYSTEM_PROMPT` will change RSI and EMA guidance:

- BUY: RSI not overbought on M5, where overbought is `>75`.
- SELL: RSI not oversold on M5, where oversold is `<25`.
- Use EMA50/EMA200 for trend context.

## Tests

Add or update tests to prove:

- Indicator payload includes `ema_200` and not only `ema_20`.
- RSI state uses 25/75 thresholds.
- Telegram momentum displays `EMA50/200`.
- Telegram alert does not display `N/A` or `UNCLEAR` when fallback wording should be used.
- Bias map falls back to EMA50/EMA200 when market structure is unclear.
- Prompt includes RSI 25/75 and EMA50/EMA200 wording.

## Non-Goals

- Do not change AI response schema.
- Do not change MT5 execution behavior.
- Do not invent DOM/depth/orderflow values if broker data is unavailable.
- Do not change trading modes or risk profile thresholds.

## Rollout

This is a display and analysis-context change. Existing `.env` configuration remains valid. After deploy, restart the bot so new formatter and payload logic apply to future Telegram alerts.

## Self-Review

- Placeholder scan: no TBD/TODO placeholders.
- Internal consistency: display fallback rules match data rules.
- Scope check: focused on alert data quality, EMA200, and RSI thresholds only.
- Ambiguity check: missing data and unclear bias have explicit separate wording.
