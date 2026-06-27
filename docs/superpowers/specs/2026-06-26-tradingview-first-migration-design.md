# TradingView-First Migration Design

## Goal

Migrate signal analysis from MT5 candle data to TradingView MCP as primary source. MT5 remains only for optional execution and account info. Signal generation must work without MT5 connected.

## Non-Goals

- Do not remove MT5 integration (keep as fallback + execution).
- Do not change Telegram format or SMC probability scoring logic.
- Do not change DeepSeek prompt structure.
- Do not remove existing endpoints or bot commands.

## Architecture

Current flow:
```
MT5 candles → feature_builder → market_payload → SMC scorer → DeepSeek → Telegram
```

New flow:
```
TV get_ohlcv + get_quote + get_study_values + get_pine_boxes + get_pine_lines
  → tv_data_adapter → market_payload → SMC scorer → DeepSeek → Telegram
MT5 only: execution (AUTO_DEMO/LIVE_AUTO), account balance, spread
```

## TV MCP Tools Used

| Tool | Replaces | Purpose |
|------|----------|---------|
| `get_ohlcv` | `mt5.get_candles` | D1/H4/H1/M5/M15 candle data |
| `get_quote` | `mt5.get_latest_tick` | Bid/ask/mid real-time |
| `get_study_values` | `feature_builder._safe_indicators` | RSI, EMA, ATR from TV indicators |
| `get_pine_lines` | `feature_builder.detect_support_resistance` | Support/resistance levels |
| `get_pine_boxes` | `smc_detector.build_smc_section` | OB, FVG, liquidity zones from SMC indicator |
| `get_pine_labels` | — | CHoCH/BOS annotations from SMC indicator |
| `get_pine_tables` | — | SMC structure table if indicator provides |
| `capture_screenshot` | already used | Chart screenshot for Telegram |

## Data Mapping

### Candles (get_ohlcv → DataFrame)

TV `get_ohlcv` returns `OHLCVData` schema. Convert to pandas DataFrame matching existing format:

```python
{
  "time": int,       # unix timestamp
  "open": float,
  "high": float,
  "low": float,
  "close": float,
  "tick_volume": float,
}
```

Need fetch per timeframe: D1, H4, H1, M15, M5. Use `set_timeframe` between calls or multi-pane.

### Quote (get_quote → tick)

```python
{
  "bid": quote.bid,
  "ask": quote.ask,
  "mid": (quote.bid + quote.ask) / 2,
  "spread_points": 0,  # TV has no spread, default 0 or estimate
}
```

### Indicators (get_study_values)

Filter by study name. Map:
- RSI(14) → `rsi_14`
- EMA(50) → `ema_50`
- EMA(200) → `ema_200`
- ATR(14) → `atr_14`

If TV indicator names differ, use `study_filter` parameter or fuzzy match.

### SMC Zones (get_pine_boxes)

TV SMC indicators (like "Smart Money Concepts" by LuxAlgo) output boxes:
- Order Blocks (demand/supply)
- FVG zones
- Liquidity levels

Map pine boxes to existing `smc` payload structure:
```python
{
  "order_blocks": {"demand": [...], "supply": [...]},
  "fvg_zones": [...],
  "liquidity_levels": [...],
  "choch": {...},  # from pine_labels
}
```

### CHoCH/BOS (get_pine_labels)

SMC indicators label CHoCH/BOS on chart. Map labels to `choch` structure:
- Label text contains "CHoCH" → bullish/bearish choch
- Label text contains "BOS" → bos event

## Fallback Strategy

```
if TV available:
    use TV data (ohlcv, quote, studies, pine)
elif MT5 available:
    use MT5 data (existing flow)
else:
    return error
```

Config: `TV_FIRST_MODE=true` (default). Set `false` to keep MT5 primary.

## Files to Change

- Create `app/tv_connector/tv_data_fetcher.py`: fetch all TV data in one call
- Modify `app/services/signal_service.py`: try TV first, fallback MT5
- Modify `app/analysis/feature_builder.py`: accept TV-sourced data
- Modify `app/ai_engine/tv_data_adapter.py`: map pine_boxes/labels to SMC structure
- Modify `app/config.py`: add `tv_first_mode: bool = True`
- Modify `.env.example`: document `TV_FIRST_MODE`
- Tests: `tests/test_tv_data_fetcher.py`

## Risk

- TV MCP may not have all timeframes in one call — need `set_timeframe` between fetches
- TV indicator names vary — need flexible study filter
- TV quote may lag vs MT5 — acceptable for signal mode
- Spread = 0 from TV — SMC scorer spread gate needs adjustment (skip if 0)

## Rollout

1. Implement TV data fetcher
2. Add TV-first path in signal_service with fallback
3. Test with TV connected, MT5 disconnected
4. Test with both connected (TV primary)
5. Test fallback (TV down, MT5 up)
