# Adaptive TP Based On OB Depth Design

## Goal

Adjust TP ratio based on where the LIMIT entry sits inside the order block zone. Near-third entries get capped R:R of 1:1.5 to 1:2 to minimize SL risk. SMC acts as context for DeepSeek, not as sole decision maker.

## Scope

- After SMC selector picks a LIMIT zone, calculate entry depth inside OB.
- If entry is in near third (depth < 0.33), cap TP to 1:1.5 - 1:2 R:R.
- If entry is in middle or premium third, leave TP to AI/SMC-based target.
- TP target prefers nearest liquidity level, FVG, or opposite OB from SMC payload.
- If SMC target gives R:R > 2 and entry is near third, scale TP down to 2x SL distance.
- DeepSeek still owns SL/TP in prompt, but execution layer adjusts TP when near-third cap applies.
- Prompt updated to tell AI about near-third TP behavior.

## OB Depth Calculation

```python
depth = (entry_price - ob_low) / (ob_high - ob_low)
```

- BUY: `depth < 0.33` = near third (entry dekat current price, bukan premium)
- SELL: `depth > 0.67` = near third (entry dekat current price untuk SELL_LIMIT above bid)

For SELL, depth is inverted because near third is the upper part of the zone closer to current price.

## TP Adjustment Rules

### Near Third (depth < 0.33 for BUY, depth > 0.67 for SELL)

1. Calculate SL distance: `sl_dist = abs(entry_price - stop_loss)`
2. Target R:R = 1.5 minimum, 2.0 maximum
3. Try SMC target first:
   - BUY: nearest liquidity level above entry, or unfilled bearish FVG top, or opposite supply OB high
   - SELL: nearest liquidity level below entry, or unfilled bullish FVG bottom, or opposite demand OB low
4. If SMC target R:R > 2.0, cap TP at `entry_price + (sl_dist * 2.0)` for BUY, `entry_price - (sl_dist * 2.0)` for SELL
5. If no SMC target found, use `entry_price + (sl_dist * 1.5)` for BUY, `entry_price - (sl_dist * 1.5)` for SELL

### Middle/Premium Third

- Do not adjust TP. Keep AI-provided TP.
- SMC SL protection remains active.

## Integration Point

In `app/services/execution_service.py`:
- After SMC selector returns valid LIMIT and before order request build.
- Only applies when `is_limit=True` and selector returned zone info.
- Adjust `take_profit` variable.

In `app/analysis/smc_entry_selector.py`:
- Add `zone_depth` to selector return dict.
- Add `is_near_third` boolean flag.

## SMC Target Helper

Create `app/analysis/smc_tp_target.py`:

```python
def find_smc_tp_target(
    side: str,
    entry_price: float,
    smc: dict,
) -> float | None:
    ...
```

Returns nearest SMC-based TP target or None.

## Prompt Changes

Add to system prompt:
- When AI returns LIMIT entry at near-third of OB zone, TP should be conservative (1:1.5 to 1:2).
- SMC data helps AI choose TP targets at liquidity levels or FVG.
- Near-third entries have higher SL risk, so TP must be closer.

## Tests

- Selector returns `zone_depth` and `is_near_third` for BUY near-third.
- Selector returns `zone_depth` and `is_near_third` for SELL near-third.
- `find_smc_tp_target` returns nearest liquidity above entry for BUY.
- `find_smc_tp_target` returns None when no SMC target.
- Execution caps TP at 2x SL for near-third BUY LIMIT.
- Execution caps TP at 2x SL for near-third SELL LIMIT.
- Execution does not adjust TP for middle-third entry.
- Prompt includes near-third TP guidance.

## Non-Goals

- Do not change SL logic.
- Do not change AI schema.
- Do not force-close existing orders.
- Do not change cap enforcement logic.

## Self-Review

- Placeholder scan: no TBD/TODO.
- Internal consistency: depth calc, near-third rules, and TP cap all match.
- Scope check: focused on adaptive TP for near-third LIMIT entries.
- Ambiguity check: near-third definition explicit for both BUY and SELL.
