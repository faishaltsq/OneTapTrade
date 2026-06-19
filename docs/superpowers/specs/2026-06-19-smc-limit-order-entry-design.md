# SMC Limit Order Entry Design

## Goal

Add pending LIMIT order execution that prefers high-probability SMC order block, supply, or demand zones while keeping MARKET order execution available only for confident trend-following setups.

## Decisions

- Prefer LIMIT when a valid SMC zone exists.
- Use BUY_LIMIT at strong demand/order block zones below current ask.
- Use SELL_LIMIT at strong supply/order block zones above current bid.
- Pending orders use GTC (`ORDER_TIME_GTC`).
- MARKET orders remain allowed only when:
  - confidence is greater than 50%, and
  - direction follows D1 major trend, and
  - H1/M5 trend context is not strongly opposite.
- If no valid SMC limit zone exists, executor may fall back to MARKET only if MARKET rule above passes.
- If no valid LIMIT and MARKET rule fails, reject execution with clear reason.

## Current State

- `EntryType.LIMIT` already exists in `app/ai_engine/schemas.py`.
- `app/mt5_connector/execution.py` already supports pending BUY_LIMIT and SELL_LIMIT through `is_limit=True`.
- `app/services/execution_service.py` currently detects `entry_type` LIMIT/STOP and passes `is_limit=True`, but it does not select a high-probability SMC zone automatically.
- SMC payload already includes H1 order blocks, H1/M5 swings, FVG zones, CHoCH, and liquidity levels.

## New Component

Create `app/analysis/smc_entry_selector.py` with one public helper:

```python
def select_smc_limit_entry(
    decision: str,
    current_bid: float,
    current_ask: float,
    market_payload: dict,
) -> dict:
    ...
```

Return shape:

```python
{
    "valid": bool,
    "entry_type": "LIMIT" | "MARKET",
    "order_type": "BUY_LIMIT" | "SELL_LIMIT" | "MARKET",
    "entry_price": float | None,
    "zone_type": "demand_ob" | "supply_ob" | "demand_zone" | "supply_zone" | None,
    "zone_low": float | None,
    "zone_high": float | None,
    "score": float,
    "quality": "HIGH" | "MEDIUM" | "LOW" | "NONE",
    "reason": str,
}
```

## SMC Zone Rules

### BUY LIMIT

Candidates:

- H1 demand order blocks from `market_payload["smc"]["order_blocks"]["demand"]`.
- Demand-like support zones can be added later, but first implementation uses existing OB data only.

Validity:

- Zone must have `low` and `high`.
- Zone high must be below current ask so the pending order is a true BUY_LIMIT.
- Zone must align with D1 allowed directions. D1 must allow BUY.

Entry price:

- Use upper third of zone for better fill probability:
  - `entry = low + ((high - low) * 0.67)`
- Normalize later using symbol digits in execution service.

### SELL LIMIT

Candidates:

- H1 supply order blocks from `market_payload["smc"]["order_blocks"]["supply"]`.

Validity:

- Zone must have `low` and `high`.
- Zone low must be above current bid so the pending order is a true SELL_LIMIT.
- Zone must align with D1 allowed directions. D1 must allow SELL.

Entry price:

- Use lower third of zone for better fill probability:
  - `entry = high - ((high - low) * 0.67)`

## Zone Scoring

Score range: 0.0 to 1.0.

Factors:

- Recency: more recent OB gets higher score.
- Distance: closer zone gets higher score, but must be valid pending side.
- Directional alignment: D1 allowed direction is required.
- CHoCH alignment adds score when direction matches.
- Nearby liquidity target or FVG in profit direction adds score.

Quality:

- `HIGH`: score >= 0.70
- `MEDIUM`: score >= 0.50
- `LOW`: score >= 0.30
- `NONE`: score < 0.30 or no valid zone

Execution will only auto-convert to LIMIT for `MEDIUM` or `HIGH` zones.

## Execution Flow

In `app/services/execution_service.py`:

1. Read AI decision, entry plan, current bid/ask, and market payload.
2. If decision is BUY/SELL, call `select_smc_limit_entry()`.
3. If selector returns valid `LIMIT` with quality `MEDIUM` or `HIGH`, override entry type to LIMIT and set entry price from selected SMC zone.
4. If selector returns no valid LIMIT:
   - allow MARKET only if confidence > 0.50 and trend-following rule passes.
   - otherwise return failure with reason.
5. Existing SMC SL protection remains active.
6. Build MT5 request with `is_limit=True` for LIMIT and GTC pending order.

## Market Order Rule

MARKET is allowed only when all conditions are true:

- `ai_decision.confidence > 0.50`
- BUY when `major_trend.allowed_directions` contains BUY.
- SELL when `major_trend.allowed_directions` contains SELL.
- H1/M5 trend from payload is not strongly opposite:
  - BUY blocked if H1 and M5 are both bearish.
  - SELL blocked if H1 and M5 are both bullish.

If `major_trend` is missing, keep existing risk-manager direction checks as source of truth and allow only if confidence rule passes. The normal risk manager still runs before execution.

## Prompt Changes

Update DeepSeek system prompt:

- Prefer `entry_plan.entry_type=LIMIT` when price can retrace to a valid order block, supply zone, or demand zone.
- BUY LIMIT should be inside a demand OB below current price.
- SELL LIMIT should be inside a supply OB above current price.
- MARKET is allowed only when confidence is above 50% and trade follows trend.
- BUY/SELL must still include SL/TP/preferred entry/R:R.

## Telegram Changes

Trade plan output should show selected entry type and price. Existing formatter already shows `Entry: LIMIT @ price`; add optional SMC zone details later only if result payload is passed into Telegram. First implementation may keep current trade plan output unchanged.

## Tests

Add tests for:

- BUY selects valid demand OB below current ask as LIMIT.
- SELL selects valid supply OB above current bid as LIMIT.
- BUY ignores demand OB above ask.
- SELL ignores supply OB below bid.
- No valid LIMIT plus confidence >50 and trend-following allows MARKET fallback.
- No valid LIMIT plus confidence <=50 rejects execution.
- Order request for LIMIT uses pending order action and BUY_LIMIT/SELL_LIMIT.
- Prompt includes SMC LIMIT preference and MARKET confidence/trend rule.

## Non-Goals

- Do not implement order expiration beyond GTC.
- Do not cancel stale pending orders automatically in this change.
- Do not add new database columns.
- Do not change AI schema unless tests prove existing fields are insufficient.
- Do not invent supply/demand zones outside current SMC payload in first implementation.

## Self-Review

- Placeholder scan: no TBD/TODO placeholders.
- Internal consistency: LIMIT preference, MARKET fallback, and GTC behavior are explicit.
- Scope check: focused on SMC LIMIT selection and execution gating.
- Ambiguity check: MARKET fallback has concrete confidence and trend rules.
