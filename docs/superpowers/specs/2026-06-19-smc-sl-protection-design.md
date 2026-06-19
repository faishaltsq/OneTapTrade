# SMC + SL Protection Design

## Problem

AI currently scalps without SMC (Smart Money Concepts) context. It follows minor trends but can't see potential reversals from previous price levels. Also, SL sometimes gets placed at exposed levels and easily swept.

## Desired Behavior

AI receives SMC data and uses it to:
- Detect potential reversals (CHoCH, order blocks)
- Place SL behind SMC protection levels (order blocks, liquidity)
- Target TP at FVG or opposite liquidity
- Avoid SL placement at exposed levels

## SMC Concepts

1. **Swing Highs/Lows** — key structural points on H1 and M5
2. **Order Blocks** — last bullish/bearish candle before impulse move (H1)
3. **Fair Value Gaps (FVG)** — price gaps on M5 that may act as magnets
4. **CHoCH / Market Structure Shift** — break of recent swing structure signaling reversal
5. **Liquidity Levels** — equal highs/lows where stops cluster

## Data Flow

```
MT5 Candles (H1, M5)
  → smc_detector.py (new)
    → swing_highs, swing_lows
    → order_blocks (supply/demand)
    → fvg_zones
    → choch_signals
    → liquidity_levels
  → feature_builder.py (add "smc" section)
    → market_payload["smc"] = {...}
  → DeepSeek AI (reads SMC from payload)
  → prompt instructs AI on SMC usage
```

## SL Protection

After AI sets SL, execution_service validates:
- SL distance from nearest SMC level (order block or swing)
- Add spread buffer to SL (current spread * 2)
- If SL is in front of an order block (exposed), push SL behind the block + spread buffer
- If SL is above a demand zone for BUY, push SL below the zone
- If SL is below a supply zone for SELL, push SL above the zone

## Files

### New: `app/analysis/smc_detector.py`

Functions:
- `detect_swing_points(df, timeframe_label, lookback=5)` → list of swing highs/lows
- `detect_order_blocks(df, timeframe_label)` → supply/demand zones from last impulse candles
- `detect_fvg(df)` → fair value gaps from 3-candle pattern
- `detect_choch(df, swing_points)` → CHoCH detection from structure break
- `detect_liquidity_levels(df, swing_points)` → equal highs/lows clusters
- `build_smc_section(df_h1, df_m5)` → aggregate all SMC data into dict

### Modify: `app/analysis/feature_builder.py`

Add `smc_section` to payload:
```python
from app.analysis.smc_detector import build_smc_section
payload["smc"] = build_smc_section(df_h1, df_m15)
```

### Modify: `app/ai_engine/prompt_builder.py`

Add SMC section to system prompt:
- "Use SMC concepts to identify potential reversals"
- "Place SL behind nearest order block or swing level"
- "Target TP at FVG or opposite liquidity"
- "Avoid placing SL at exposed levels"

### Modify: `app/services/execution_service.py`

After AI sets SL, validate against SMC levels with spread buffer:
```python
def protect_sl_with_smc(sl, entry_price, side, smc_data, point, spread_points):
    # Find nearest SMC level that protects SL
    # Add spread buffer
    # Return adjusted SL
```

### New: `tests/test_smc_detector.py`

Tests for each SMC function.

## Out of Scope

- No change to risk manager
- No change to position sizing
- No change to MT5 execution
- No real-time SMC recalculation (uses candlestick data at signal time)
