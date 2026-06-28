# TradingView MCP Integration — Design Spec

**Date:** 2025-06-25
**Status:** Approved

## Overview

Integrate TradingView MCP server (`tradesdontlie/tradingview-mcp`) into the OneTapTrade Python trading bot. Full bidirectional coupling: TV provides chart data, indicator values, Pine Script output, and visual screenshots as additional AI context; the bot controls TV for auto-charting, drawing, alerts, and replay. The Node.js MCP server runs as a managed subprocess invisible to the user, with all 78 tools exposed as typed Python async functions.

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────┐
│  Telegram   │◄───►│         FastAPI Backend              │
│  Bot        │     │                                      │
└─────────────┘     │  ┌──────────┐  ┌─────────────────┐  │
                    │  │ AI Engine│  │  tv_connector/   │  │
┌─────────────┐     │  │(DeepSeek)│  │  ┌─────────────┐ │  │
│  Supabase   │◄───►│  │          │  │  │TV MCP Client│ │  │
│  (audit)    │     │  └──────────┘  │  │(Python MCP) │ │  │
└─────────────┘     │       │        │  └──────┬──────┘ │  │
                    │       ▼        │         │stdio    │  │
┌─────────────┐     │  ┌──────────┐  │  ┌──────▼──────┐ │  │
│    MT5      │◄───►│  │ Market   │  │  │ Node.js     │ │  │
│  Terminal   │     │  │ Payload  │◄─┼──│ MCP Server  │ │  │
└─────────────┘     │  │ Builder  │  │  └──────┬──────┘ │  │
                    │  └──────────┘  │         │CDP      │  │
                    │       │        │  ┌──────▼──────┐ │  │
                    │       ▼        │  │  TradingView│ │  │
                    │  ┌──────────┐  │  │  Desktop    │ │  │
                    │  │  Risk    │  │  └─────────────┘ │  │
                    │  │  Manager │  │                   │  │
                    │  └────┬─────┘  └───────────────────┘  │
                    │       │                                │
                    │       ▼                                │
                    │  ┌──────────┐                         │
                    │  │Execution │                         │
                    │  │ Service  │                         │
                    │  └──────────┘                         │
                    └───────────────────────────────────────┘
```

### Key Decisions

1. **Approach:** Long-running MCP subprocess with Python MCP stdio client (Approach 2 from brainstorming). Fast, streaming-ready, user only sees Python.
2. **Data strategy:** MT5 and TV data side-by-side in AI prompt. MT5 = execution data (price, orders). TV = analysis layer (indicators, Pine output, chart visuals).
3. **Scope:** TV data is optional/enhancement. If TV is not running or MCP fails, bot degrades gracefully to MT5-only mode — no crash, no hang.

## New Modules

### `app/tv_connector/`

```
app/tv_connector/
├── __init__.py           # Public API: start_tv_mcp, stop_tv_mcp, get_tv_client
├── mcp_client.py          # Python MCP stdio client — spawns Node, sends/receives JSON-RPC
├── process_manager.py     # Start/stop/health-check/restart lifecycle of Node MCP process
├── tools.py               # Typed async wrappers for 78 TV MCP tools
├── schemas.py             # Pydantic models for TV data
└── errors.py              # ConnectionError, TVNotRunningError, ToolError
```

**`process_manager.py` lifecycle:**
- Startup: spawn `node tradingview-mcp/src/server.js` as asyncio subprocess
- Wait for stdio ready, perform MCP handshake, call `tv_health_check`
- Runtime: heartbeat ping every 30s
- On crash: log, auto-restart (max 3 retries in 60s, then log fatal and degrade)
- Shutdown: graceful stdio close, process terminate

**`mcp_client.py`:**
- Implements MCP JSON-RPC over stdio to the Node server
- Methods: `initialize()`, `list_tools()`, `call_tool(name, args)`
- Handles MCP protocol framing, error responses, timeouts
- Single `mcp` Python SDK dependency (`pip install mcp`)

**`tools.py` — key tool wrappers (78 total, prioritized subset):**

```python
# Connection
async def tv_health_check() -> bool
async def tv_launch() -> None
async def tv_status() -> dict

# Chart reading
async def tv_get_chart_state() -> ChartState
async def tv_get_study_values(study_filter: str = None) -> list[IndicatorValue]
async def tv_get_pine_lines(study_filter: str = None) -> list[PriceLevel]
async def tv_get_pine_labels(study_filter: str = None) -> list[TextAnnotation]
async def tv_get_pine_tables(study_filter: str = None) -> list[TableData]
async def tv_get_pine_boxes(study_filter: str = None) -> list[PriceZone]
async def tv_get_quote() -> QuoteData
async def tv_get_ohlcv(summary: bool = True) -> OHLCVData

# Chart control
async def tv_set_symbol(symbol: str) -> None
async def tv_set_timeframe(timeframe: str) -> None
async def tv_set_chart_type(chart_type: str) -> None
async def tv_manage_indicator(action: str, name: str, inputs: dict = None) -> None
async def tv_scroll_to_date(date: str) -> None

# Multi-pane
async def tv_pane_list() -> list[PaneInfo]
async def tv_pane_set_layout(layout: str) -> None
async def tv_pane_set_symbol(pane_index: int, symbol: str) -> None
async def tv_pane_focus(pane_index: int) -> None

# Drawing
async def tv_draw_shape(shape_type: str, **kwargs) -> str  # returns shape_id
async def tv_draw_list() -> list[Shape]
async def tv_draw_clear() -> None

# Alerts
async def tv_alert_list() -> list[Alert]
async def tv_alert_create(condition: str, message: str) -> str
async def tv_alert_delete(alert_id: str) -> None

# Pine Script
async def tv_pine_set_source(source: str) -> None
async def tv_pine_smart_compile() -> dict
async def tv_pine_get_errors() -> list[str]
async def tv_pine_get_console() -> list[str]

# Replay
async def tv_replay_start(date: str) -> None
async def tv_replay_step() -> dict
async def tv_replay_stop() -> None
async def tv_replay_status() -> dict
async def tv_replay_autoplay(speed_ms: int) -> None
async def tv_replay_trade(action: str) -> dict

# Screenshot
async def tv_capture_screenshot(region: str = "chart") -> bytes

# Streaming (for live monitoring)
async def tv_stream_quote() -> AsyncIterator[QuoteData]
async def tv_stream_all() -> AsyncIterator[dict]
```

### Config additions

```python
# app/config.py additions
tv_enabled: bool = True              # master toggle
tv_launch_on_startup: bool = False   # auto-launch TV with debug port
tv_debug_port: int = 9222            # CDP port
tv_health_check_interval: int = 30   # seconds between heartbeats
tv_mcp_max_retries: int = 3          # restart attempts
tv_mcp_path: str = "tradingview-mcp" # path to cloned subdirectory
```

### `app/services/tv_autochart_service.py` (new)

Auto-draw on TV chart based on bot signals:
- On BUY/SELL signal → draw entry line, SL line, TP line with labels
- On position open → draw position box with entry price
- On breakeven hit → redraw SL at breakeven, add annotation
- On position close → draw result annotation (win/loss with P&L)
- Telegram `/chart` → redraw full chart with current state, screenshot to Telegram

### `app/services/tv_replay_service.py` (new)

Replay mode bridge for manual/automated backtesting:
- Load historical date, step through bars
- AI analyzes replay data but does NOT execute real trades
- Log decisions vs actual price movement
- Export replay session results as performance report

### `app/services/alert_bridge.py` (new)

Bidirectional alert sync:
- TV alerts → read by bot → can trigger Telegram notification
- Bot signal levels → create TV alerts at SL/TP/entry prices
- Sync on startup: list TV alerts, reconcile with bot state

### `app/ai_engine/tv_data_adapter.py` (new)

Formats raw TV tool outputs into structured JSON sections for the AI prompt:
```json
{
  "tv_chart_context": {
    "symbol": "XAUUSD",
    "timeframe": "M5",
    "indicators": [
      {"name": "RSI", "value": 62.4, "signal": "neutral"},
      {"name": "MACD", "value": {"histogram": 1.2, "signal_line": 0.8}, "signal": "bullish"}
    ],
    "pine_levels": {
      "support": [2150.00, 2145.50],
      "resistance": [2160.00, 2165.80]
    },
    "pine_labels": [
      {"text": "PDH 2162.30", "price": 2162.30},
      {"text": "Bias: Long", "price": null}
    ],
    "chart_structure": {
      "trend": "bullish",
      "swing_high": 2165.80,
      "swing_low": 2145.50
    }
  },
  "mt5_market_context": {
    // existing MT5 data unchanged
  }
}
```

### `app/ai_engine/vision_analyzer.py` (new)

When DeepSeek Vision model is available:
- Capture TV screenshot
- Send to vision API for chart pattern recognition
- Extract: trendlines, support/resistance, candlestick patterns, volume profile
- Merge text analysis with structured data analysis

### `app/analysis/tv_enrichment.py` (new)

Enrich existing SMC/analysis with TV data:
- **Confluence scoring:** Score = D1 trend (0-3) + TV indicator agreement (0-2) + SMC zone match (0-2) + TV Pine level confluence (0-2). Max 9.
- **Profile thresholds:** LOW ≥ 7, MEDIUM ≥ 5, HIGH ≥ 3
- Compare TV-calculated indicator values vs MT5-calculated → higher confidence when aligned
- TV Pine labels ("PDH", "Bias Long") feed into market bias assessment

### `app/risk/tv_levels.py` (new)

Dynamic SL/TP from TV chart structure:
- `data_get_pine_lines` → nearest S/R level as dynamic SL (not fixed pips)
- `data_get_pine_boxes` → box boundaries as partial TP zones
- Partial close: first TP at nearest TV box boundary (50%), second at next level
- SL moves to breakeven after first partial TP hit

## Modified Existing Files

### `app/ai_engine/prompt_builder.py`
- Add `tv_chart_context` section to user prompt
- Merge MT5 and TV data sections in unified structured JSON
- Include confluence score and TV-derived levels

### `app/services/trading_loop.py`
- Before AI call per symbol: fetch TV chart data (set symbol, get state, get studies, get pine data)
- Wrap in try/except: TV failure → log warning, continue with MT5-only
- After AI decision: if BUY/SELL, call autochart service to draw levels

### `app/analysis/` (smc_detector, market_structure, regime_detector)
- Accept optional `tv_enrichment` parameter
- When TV data available, enhance detection with Pine levels and indicator confluence

### `app/risk/risk_manager.py`
- Accept optional TV levels for dynamic SL/TP validation
- Apply confluence score as confidence multiplier

### `app/main.py` lifespan
- Add `tv_connector` startup sequence after MT5 init
- Graceful shutdown of TV MCP subprocess
- Log TV connection status

### `app/telegram_bot/` (bot, commands, callbacks, message_templates)
- New `/chart` command → screenshot TV chart, send to Telegram
- Signal messages include TV chart screenshot when available
- Inline menu: toggle TV features, request chart

### `requirements.txt`
- Add `mcp>=1.0.0` (MCP Python SDK)
- Add optional: `Pillow>=11.0.0` (screenshot processing)

### `.env.example`
- Add TV config vars

## Data Flow: Trading Loop with TV

```
TradingLoop.run_once(symbol)
│
├─► 1. Set symbol on TV         → tv_set_symbol(symbol)
├─► 2. Get TV chart state       → tv_get_chart_state()
├─► 3. Get TV study values      → tv_get_study_values()
├─► 4. Get TV Pine output       → tv_get_pine_lines/labels/tables/boxes()
├─► 5. Get MT5 market data      → existing MT5 pipeline
├─► 6. Build unified payload    → tv_data_adapter + existing feature_builder
├─► 7. Enrich SMC analysis      → tv_enrichment.enhance()
├─► 8. Apply confluence scoring → tv_enrichment.compute_score()
├─► 9. Run noise filter         → existing (enhanced with TV data)
├─►10. Call DeepSeek AI         → unified prompt with MT5 + TV
├─►11. Parse decision           → existing decision_parser
├─►12. Dynamic SL/TP from TV    → tv_levels.optimize()
├─►13. Risk check               → existing (enhanced)
├─►14. Execute if approved      → existing (MT5 execution)
├─►15. Auto-chart result        → tv_autochart.draw()
└─►16. Send Telegram update     → with chart screenshot

All TV steps wrapped in try/except → degrade to MT5-only on failure
```

## Error Handling & Graceful Degradation

- TV MCP process crash → auto-restart (3 retries), then degrade
- Individual tool call timeout (5s) → return None, continue
- TV not running at all → `tv_enabled` flag auto-set to False after retry exhaustion
- All TV data fetches return Optional → None means "not available"
- AI prompt builder handles missing TV section gracefully
- Log all TV errors to `bot_events` table
- Telegram `/status` shows TV connection health

## Testing Strategy

- `tests/tv_connector/` — process manager lifecycle, mock MCP client, tool wrappers
- `tests/tv_enrichment/` — confluence scoring, data adapter formatting
- `tests/test_trading_loop_tv.py` — loop with mocked TV data
- Existing tests must pass unchanged (TV is additive, not breaking)
- Integration tests require TradingView Desktop running

## Implementation Order

1. Clone `tradingview-mcp` subdirectory, `npm install`
2. Build `app/tv_connector/` — process manager + MCP client + schemas
3. Build core tool wrappers in `tools.py` (priority subset: chart reading + drawing + screenshot)
4. Build `tv_data_adapter.py` + `tv_enrichment.py` → feed into prompt builder
5. Modify `trading_loop.py` to fetch TV data each cycle
6. Build `tv_autochart_service.py` → draw on TV from signals
7. Build `alert_bridge.py` + `tv_replay_service.py`
8. Add Telegram `/chart` command and screenshot to signal messages
9. Add `vision_analyzer.py` (depends on DeepSeek Vision availability)
10. Add config, env vars, graceful degradation wiring
11. Tests
12. Update README

## Dependencies

- **New Python:** `mcp>=1.0.0`, `Pillow>=11.0.0` (optional)
- **New system:** Node.js 18+ (already needed by MCP server), TradingView Desktop (user must have)
- **Subdirectory:** `tradingview-mcp/` cloned from GitHub

## Open Questions

- DeepSeek Vision model availability — need to check API support and pricing
- TradingView Desktop version pinning — MCP uses undocumented APIs, may break on TV updates
