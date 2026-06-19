# Readable Market Trend Alerts Design

## Goal

Improve Telegram market trend alerts so both HOLD market updates and BUY/SELL trade signals are more detailed, structured, and easy to read on mobile.

## Scope

- Update HOLD market update messages.
- Update BUY/SELL trade signal messages.
- Preserve existing approve/reject buttons for semi-auto mode.
- Preserve existing Telegram HTML parse mode.
- Use existing analysis data from `market_payload` where available.
- Keep messages concise enough for Telegram mobile reading.

## Message Format

All market alerts use a compact dashboard structure:

```text
📊 Market Trend — SYMBOL
Decision: HOLD | Confidence: 42%

🧭 Bias Map
D1: Bullish | H4: Ranging
H1: Bullish | M5: Bearish
Regime: Ranging / Low momentum

💵 Price
Bid/Ask: 2432.10 / 2432.45
Spread: 35 pts

📈 Momentum
M5 RSI: 48 | EMA20/50: Bearish
H1 RSI: 56 | EMA20/50: Bullish

🧱 SMC
CHoCH: Bearish
Nearest Demand: 2427.50
Nearest Supply: 2440.20
Liquidity: Equal highs above

⚖️ Orderflow
Delta: Sell pressure
DOM: N/A

📝 Read
No trade. M5 conflicts with H1 and price is between liquidity zones.
```

BUY/SELL trade signals use the same top sections, then add:

```text
🎯 Trade Plan
Entry: MARKET @ 2432.45
SL: 2427.50
TP1: 2440.20
R:R: 1.8

🛡️ Risk Check
✅ Approved
```

## Data Sources

- Decision, confidence, reason: `AIDecisionResponse`.
- D1/H4/H1/M5 bias: decision fields and `market_payload` timeframe structures.
- Price: `market_payload.current_price`.
- Momentum: `market_payload.primary_timeframe.indicators` and `market_payload.entry_timeframe.indicators`.
- SMC: `market_payload.smc`.
- Orderflow: `market_payload.orderflow_proxy`.
- Risk check: existing `risk_result`.

## Fallbacks

- Missing payload fields render as `N/A`.
- Missing SMC values render as `N/A` rather than failing.
- Existing old decision fields still render when `market_payload` is unavailable.
- Trade buttons continue using the same decision ID and keyboard behavior.

## Architecture

- Add a shared formatter `format_market_trend_alert(decision, symbol, market_payload=None, risk_result=None)` in `app/telegram_bot/message_templates.py`.
- Keep `format_signal_message(...)` as a compatibility wrapper that calls the new formatter.
- Update `TradingLoop._send_market_update` to pass `market_payload` from `signal_result`.
- Update trade signal sending path to pass `market_payload` when available.
- Keep message formatting pure and unit-testable.

## Testing

- HOLD alert includes Bias Map, Price, Momentum, SMC, Orderflow, and Read sections.
- BUY/SELL alert includes the same trend dashboard plus Trade Plan and Risk Check sections.
- Formatter handles missing payload without crashing.
- Trading loop passes `market_payload` into market update formatter.
