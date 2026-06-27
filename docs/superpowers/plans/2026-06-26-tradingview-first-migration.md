# TradingView-First Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate signal analysis to TradingView MCP as primary data source, keeping MT5 as fallback + execution only.

**Architecture:** Add TV data fetcher that collects OHLCV, quote, indicators, and SMC zones in one pass. Signal service tries TV first, falls back to MT5. Feature builder accepts TV-sourced data. SMC probability scorer reads from mapped pine_boxes.

**Tech Stack:** Python 3.13, pytest, TradingView MCP client, existing pandas/loguru stack.

---

## File Structure

- Create `app/tv_connector/tv_data_fetcher.py`: unified TV data fetch (OHLCV multi-TF, quote, studies, pine boxes/lines/labels)
- Create `tests/test_tv_data_fetcher.py`: unit tests for TV data mapping
- Modify `app/config.py`: add `tv_first_mode: bool = True`
- Modify `.env.example`: document `TV_FIRST_MODE`
- Modify `app/services/signal_service.py`: TV-first path with MT5 fallback
- Modify `app/analysis/feature_builder.py`: accept TV OHLCV + studies + SMC zones
- Modify `app/ai_engine/tv_data_adapter.py`: map pine_boxes/labels to smc structure
- Modify `app/analysis/smc_probability.py`: skip spread gate if spread=0 (TV mode)
- Tests: update `tests/test_signal_service.py` for TV-first path

---

### Task 1: Add TV-First Config

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config test**

```python
def test_tv_first_mode_defaults():
    from app.config import Settings
    s = Settings(_env_file=None)
    assert s.tv_first_mode is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_tv_first_mode_defaults -v`
Expected: FAIL — field does not exist.

- [ ] **Step 3: Add config field**

In `app/config.py`, add near `tv_enabled`:
```python
    tv_first_mode: bool = True
```

- [ ] **Step 4: Document env**

Add to `.env.example`:
```env
# TradingView first mode — use TV for signal analysis, MT5 for execution only
TV_FIRST_MODE=true
```

- [ ] **Step 5: Verify test passes**

Run: `pytest tests/test_config.py::test_tv_first_mode_defaults -v`
Expected: PASS.

---

### Task 2: Create TV Data Fetcher

**Files:**
- Create: `app/tv_connector/tv_data_fetcher.py`
- Test: `tests/test_tv_data_fetcher.py`

- [ ] **Step 1: Write failing tests**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_fetch_tv_ohlcv_returns_dataframes():
    from app.tv_connector.tv_data_fetcher import fetch_tv_ohlcv
    from app.tv_connector.schemas import OHLCVData

    mock_tools = MagicMock()
    mock_tools.get_ohlcv = AsyncMock(return_value=OHLCVData(
        symbol="EURUSD",
        timeframe="D1",
        summary=True,
        candles=[{"time": 1, "open": 1.1, "high": 1.11, "low": 1.09, "close": 1.105, "volume": 100}],
    ))
    mock_tools.set_timeframe = AsyncMock(return_value=True)

    result = await fetch_tv_ohlcv(mock_tools, "EURUSD", ["D1", "H1"])

    assert "D1" in result
    assert "H1" in result
    assert len(result["D1"]) > 0
    assert "close" in result["D1"].columns


@pytest.mark.asyncio
async def test_fetch_tv_quote_returns_tick():
    from app.tv_connector.tv_data_fetcher import fetch_tv_quote
    from app.tv_connector.schemas import QuoteData

    mock_tools = MagicMock()
    mock_tools.get_quote = AsyncMock(return_value=QuoteData(
        symbol="EURUSD", bid=1.1, ask=1.1002, last=1.1001, change=0.001, change_percent=0.09,
    ))

    result = await fetch_tv_quote(mock_tools)

    assert result["bid"] == 1.1
    assert result["ask"] == 1.1002
    assert result["spread_points"] == 0


@pytest.mark.asyncio
async def test_fetch_tv_smc_zones_maps_pine_boxes():
    from app.tv_connector.tv_data_fetcher import fetch_tv_smc_zones
    from app.tv_connector.schemas import PriceZone

    mock_tools = MagicMock()
    mock_tools.get_pine_boxes = AsyncMock(return_value=[
        PriceZone(study="Smart Money Concepts", name="Demand OB", price_low=1.098, price_high=1.099, color="#00FF00", time=1),
        PriceZone(study="Smart Money Concepts", name="Supply OB", price_low=1.102, price_high=1.103, color="#FF0000", time=2),
        PriceZone(study="Smart Money Concepts", name="FVG", price_low=1.100, price_high=1.101, color="#0000FF", time=3),
    ])
    mock_tools.get_pine_labels = AsyncMock(return_value=[])
    mock_tools.get_pine_lines = AsyncMock(return_value=[])

    result = await fetch_tv_smc_zones(mock_tools)

    assert len(result["order_blocks"]["demand"]) >= 1
    assert len(result["order_blocks"]["supply"]) >= 1
    assert len(result["fvg_zones"]) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tv_data_fetcher.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement TV data fetcher**

Create `app/tv_connector/tv_data_fetcher.py`:

```python
import pandas as pd
from typing import Optional
from app.logger import logger


async def fetch_tv_ohlcv(tools, symbol: str, timeframes: list[str]) -> dict[str, pd.DataFrame]:
    result = {}
    for tf in timeframes:
        try:
            await tools.set_timeframe(tf)
            data = await tools.get_ohlcv(symbol=symbol, timeframe=tf, summary=True)
            if data and data.candles:
                df = pd.DataFrame(data.candles)
                if "time" in df.columns:
                    df["time"] = pd.to_datetime(df["time"], unit="s")
                result[tf] = df
                logger.debug(f"TV OHLCV {symbol} {tf}: {len(df)} candles")
            else:
                result[tf] = pd.DataFrame()
        except Exception as e:
            logger.warning(f"TV OHLCV fetch failed for {symbol} {tf}: {e}")
            result[tf] = pd.DataFrame()
    return result


async def fetch_tv_quote(tools) -> dict:
    try:
        quote = await tools.get_quote()
        if quote:
            return {
                "bid": float(quote.bid),
                "ask": float(quote.ask),
                "mid": (float(quote.bid) + float(quote.ask)) / 2,
                "spread_points": 0,
            }
    except Exception as e:
        logger.warning(f"TV quote fetch failed: {e}")
    return {"bid": 0, "ask": 0, "mid": 0, "spread_points": 0}


async def fetch_tv_indicators(tools, study_filter: str = None) -> dict:
    try:
        studies = await tools.get_study_values(study_filter=study_filter)
        result = {}
        for s in studies or []:
            name = getattr(s, "name", str(s)).lower()
            val = getattr(s, "value", None)
            if "rsi" in name and "14" in name:
                result["rsi_14"] = float(val) if val else None
            elif "ema" in name and "50" in name:
                result["ema_50"] = float(val) if val else None
            elif "ema" in name and "200" in name:
                result["ema_200"] = float(val) if val else None
            elif "atr" in name and "14" in name:
                result["atr_14"] = float(val) if val else None
        return result
    except Exception as e:
        logger.warning(f"TV indicators fetch failed: {e}")
    return {}


async def fetch_tv_smc_zones(tools) -> dict:
    boxes = []
    try:
        boxes = await tools.get_pine_boxes() or []
    except Exception as e:
        logger.warning(f"TV pine_boxes fetch failed: {e}")

    demand = []
    supply = []
    fvg = []
    liquidity = []

    for box in boxes:
        name = str(getattr(box, "name", "")).lower()
        pl = float(getattr(box, "price_low", 0))
        ph = float(getattr(box, "price_high", 0))
        entry = {"low": pl, "high": ph, "time": getattr(box, "time", None)}
        if "demand" in name or "bull" in name and "ob" in name:
            demand.append(entry)
        elif "supply" in name or "bear" in name and "ob" in name:
            supply.append(entry)
        elif "fvg" in name or "fair value" in name or "gap" in name:
            fvg.append({"top": ph, "bottom": pl, "direction": "bullish" if ph > pl else "bearish"})
        elif "liquid" in name or "equal" in name:
            liquidity.append({"price": (pl + ph) / 2, "type": "high" if "high" in name else "low"})

    choch = {"h1": {"bullish_choch": [], "bearish_choch": []}, "m5": {"bullish_choch": [], "bearish_choch": []}}
    try:
        labels = await tools.get_pine_labels() or []
        for label in labels:
            text = str(getattr(label, "text", "")).lower()
            price = float(getattr(label, "price", 0))
            if "choch" in text:
                if "bull" in text:
                    choch["m5"]["bullish_choch"].append({"price": price})
                elif "bear" in text:
                    choch["m5"]["bearish_choch"].append({"price": price})
    except Exception:
        pass

    return {
        "order_blocks": {"demand": demand, "supply": supply},
        "fvg_zones": fvg,
        "liquidity_levels": liquidity,
        "choch": choch,
    }


async def fetch_all_tv_data(tools, symbol: str, timeframes: list[str]) -> dict:
    ohlcv = await fetch_tv_ohlcv(tools, symbol, timeframes)
    quote = await fetch_tv_quote(tools)
    indicators = await fetch_tv_indicators(tools)
    smc = await fetch_tv_smc_zones(tools)
    return {"ohlcv": ohlcv, "quote": quote, "indicators": indicators, "smc": smc}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_tv_data_fetcher.py -v`
Expected: PASS.

---

### Task 3: Integrate TV-First Path in Signal Service

**Files:**
- Modify: `app/services/signal_service.py`
- Test: `tests/test_signal_service.py`

- [ ] **Step 1: Write failing test for TV-first signal**

```python
@pytest.mark.asyncio
async def test_generate_signal_uses_tv_first(monkeypatch):
    from app.services import signal_service
    from app.config import settings

    monkeypatch.setattr(settings, "tv_first_mode", True)

    # Mock TV fetcher
    async def fake_fetch_all(tools, symbol, tfs):
        return {
            "ohlcv": {"D1": _fake_df(), "H4": _fake_df(), "H1": _fake_df(), "M5": _fake_df()},
            "quote": {"bid": 1.1, "ask": 1.1002, "mid": 1.1001, "spread_points": 0},
            "indicators": {"rsi_14": 55, "ema_50": 1.099, "ema_200": 1.095, "atr_14": 0.002},
            "smc": {"order_blocks": {"demand": [{"low": 1.098, "high": 1.099}], "supply": []}, "fvg_zones": [], "liquidity_levels": [], "choch": {}},
        }

    monkeypatch.setattr("app.tv_connector.tv_data_fetcher.fetch_all_tv_data", fake_fetch)
    monkeypatch.setattr("app.tv_connector.get_tv_tools", lambda: MagicMock())
    monkeypatch.setattr("app.tv_connector.is_tv_available", lambda: True)
    # ... rest of MT5/DB/noise/AI mocks same as existing tests
    result = signal_service.generate_signal("EURUSD.m")
    assert "smc_probability" in result["market_payload"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_signal_service.py::test_generate_signal_uses_tv_first -v`
Expected: FAIL — TV-first path not implemented.

- [ ] **Step 3: Add TV-first path in generate_signal**

At start of `generate_signal()`, before MT5 candle fetch:

```python
    if settings.tv_first_mode:
        from app.tv_connector import get_tv_tools, is_tv_available
        if is_tv_available():
            tools = get_tv_tools()
            if tools:
                from app.tv_connector.tv_data_fetcher import fetch_all_tv_data
                tv_data = await fetch_all_tv_data(tools, sym, ["D1", "H4", "H1", "M15", "M5"])
                if tv_data["ohlcv"].get("D1") is not None and len(tv_data["ohlcv"]["D1"]) > 0:
                    # Build market payload from TV data
                    market_payload = _build_payload_from_tv(sym, tv_data, account_context, depth_data)
                    # Skip MT5 candle fetch, continue to SMC scoring + AI
                    ...
```

Add helper `_build_payload_from_tv` that calls `feature_builder.build_market_payload` with TV DataFrames.

- [ ] **Step 4: Handle spread=0 in TV mode**

In `smc_probability.py`, skip spread gate if spread is 0:
```python
    if spread > 0 and spread > settings.max_spread_points:
        ...
```

- [ ] **Step 5: Run test**

Run: `pytest tests/test_signal_service.py::test_generate_signal_uses_tv_first -v`
Expected: PASS.

---

### Task 4: Map Pine Boxes to SMC Structure in tv_data_adapter

**Files:**
- Modify: `app/ai_engine/tv_data_adapter.py`
- Test: `tests/test_tv_data_fetcher.py`

- [ ] **Step 1: Write failing test for SMC mapping**

```python
def test_pine_box_name_mapping():
    from app.tv_connector.tv_data_fetcher import _classify_box

    assert _classify_box("Demand OB") == "demand"
    assert _classify_box("Supply OB") == "supply"
    assert _classify_box("Bullish FVG") == "fvg"
    assert _classify_box("Equal Highs") == "liquidity"
    assert _classify_box("Unknown") == "other"
```

- [ ] **Step 2: Implement classifier**

Extract `_classify_box` helper in `tv_data_fetcher.py`.

- [ ] **Step 3: Run test**

Run: `pytest tests/test_tv_data_fetcher.py::test_pine_box_name_mapping -v`
Expected: PASS.

---

### Task 5: Fallback to MT5 When TV Unavailable

**Files:**
- Modify: `app/services/signal_service.py`

- [ ] **Step 1: Add fallback logic**

After TV-first attempt:
```python
    if settings.tv_first_mode and tv_available and tv_data_ok:
        # use TV data
    else:
        logger.info("TV unavailable or failed, falling back to MT5")
        # existing MT5 candle fetch code
```

- [ ] **Step 2: Test fallback**

Add test: TV unavailable → MT5 path used → signal still generates.

---

### Task 6: Final Verification

- [ ] **Step 1: Run all focused tests**

```bash
pytest tests/test_tv_data_fetcher.py tests/test_signal_service.py tests/test_smc_probability.py tests/test_config.py -v
```

- [ ] **Step 2: Manual runtime check**

Start app with TV connected, MT5 connected. Verify logs show "TV OHLCV" instead of MT5 candles.

- [ ] **Step 3: Test TV-only mode**

Disconnect MT5, keep TV. Verify signal still generates (SIGNAL_ONLY mode).

- [ ] **Step 4: Test fallback**

Disconnect TV, keep MT5. Verify signal falls back to MT5 data.
