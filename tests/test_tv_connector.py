import pytest
from app.tv_connector.schemas import (
    ChartState, IndicatorValue, PriceLevel, QuoteData, PaneInfo, Alert, ReplayStatus
)
from app.tv_connector.errors import TVConnectionError, TVNotRunningError, TVToolError


class TestTVSchemas:
    def test_chart_state_defaults(self):
        cs = ChartState()
        assert cs.symbol == ""
        assert cs.timeframe == ""
        assert cs.indicators == []

    def test_chart_state_with_data(self):
        cs = ChartState(symbol="XAUUSD", timeframe="M5")
        assert cs.symbol == "XAUUSD"
        assert cs.timeframe == "M5"

    def test_indicator_value(self):
        iv = IndicatorValue(name="RSI", id="study_1", values={"value": 65.5})
        assert iv.name == "RSI"
        assert iv.values["value"] == 65.5

    def test_price_level(self):
        pl = PriceLevel(price=2150.00, text="Support", color="#FF0000")
        assert pl.price == 2150.00

    def test_quote_data(self):
        q = QuoteData(symbol="XAUUSD", bid=2150.00, ask=2150.50, last=2150.25)
        assert q.bid == 2150.00

    def test_pane_info(self):
        pi = PaneInfo(index=0, symbol="XAUUSD", active=True)
        assert pi.active is True

    def test_alert(self):
        a = Alert(id="alert_1", condition="cross", message="Price alert", active=True)
        assert a.id == "alert_1"

    def test_replay_status(self):
        rs = ReplayStatus(active=True, date="2025-01-15", position="BUY", pnl=100.0)
        assert rs.active is True


class TestTVErrors:
    def test_tv_connection_error(self):
        with pytest.raises(TVConnectionError):
            raise TVConnectionError("test")

    def test_tv_not_running_error_is_connection_error(self):
        with pytest.raises(TVConnectionError):
            raise TVNotRunningError("test")

    def test_tv_tool_error_is_connection_error(self):
        with pytest.raises(TVConnectionError):
            raise TVToolError("test")


class TestTVDataAdapter:
    def test_format_tv_context_empty(self):
        from app.ai_engine.tv_data_adapter import format_tv_context
        result = format_tv_context(None, [], [], [], [], [], "XAUUSD")
        assert result["tv_available"] is False
        assert result["tv_chart_context"] == {}

    def test_format_tv_context_with_chart(self):
        from app.ai_engine.tv_data_adapter import format_tv_context
        chart = {"symbol": "XAUUSD", "timeframe": "M5", "indicators": []}
        result = format_tv_context(chart, [], [], [], [], [], "XAUUSD")
        assert result["tv_available"] is True
        assert result["tv_chart_context"]["symbol"] == "XAUUSD"

    def test_format_tv_context_with_levels(self):
        from app.ai_engine.tv_data_adapter import format_tv_context
        chart = {"symbol": "XAUUSD", "timeframe": "M5", "indicators": []}
        lines = [
            {"price": 2150.0, "text": "Support level", "color": "#00FF00"},
            {"price": 2160.0, "text": "Resistance zone", "color": "#FF0000"},
        ]
        result = format_tv_context(chart, [], lines, [], [], [], "XAUUSD")
        assert result["tv_available"] is True
        ctx = result["tv_chart_context"]
        assert len(ctx["pine_levels"]["support"]) > 0
        assert len(ctx["pine_levels"]["resistance"]) > 0

    def test_format_tv_context_with_labels(self):
        from app.ai_engine.tv_data_adapter import format_tv_context
        chart = {"symbol": "XAUUSD", "timeframe": "M5", "indicators": []}
        labels = [{"text": "PDH", "price": 2160.0}, {"text": "Bias: Long", "price": None}]
        result = format_tv_context(chart, [], [], labels, [], [], "XAUUSD")
        assert result["tv_available"] is True
        assert len(result["tv_chart_context"]["pine_annotations"]) == 2


class TestConfluenceScoring:
    def test_confluence_score_no_tv(self):
        from app.analysis.tv_enrichment import compute_confluence_score
        payload = {"tv_available": False}
        result = compute_confluence_score(payload)
        assert result["total_score"] == 0

    def test_confluence_score_empty_chart_context(self):
        from app.analysis.tv_enrichment import compute_confluence_score
        payload = {
            "tv_available": True,
            "tv_chart_context": {},
            "major_trend": {"bias": "D1_BULLISH", "allowed_directions": ["BUY"]},
        }
        result = compute_confluence_score(payload)
        assert result["total_score"] == 0

    def test_confluence_score_with_trend(self):
        from app.analysis.tv_enrichment import compute_confluence_score
        payload = {
            "tv_available": True,
            "tv_chart_context": {"pine_annotations": []},
            "major_trend": {"bias": "D1_BULLISH", "allowed_directions": ["BUY"]},
        }
        result = compute_confluence_score(payload)
        assert result["breakdown"]["d1_trend"] == 3
        assert result["total_score"] >= 3

    def test_confluence_score_d1_ranging(self):
        from app.analysis.tv_enrichment import compute_confluence_score
        payload = {
            "tv_available": True,
            "tv_chart_context": {"pine_annotations": []},
            "major_trend": {"bias": "D1_RANGING"},
        }
        result = compute_confluence_score(payload)
        assert result["breakdown"]["d1_trend"] == 1


class TestTVLevels:
    def test_optimize_sl_tp_no_tv(self):
        from app.risk.tv_levels import optimize_sl_tp_from_tv
        result = optimize_sl_tp_from_tv({"tv_available": False}, 2150.0, 2170.0, 2155.0, "BUY")
        assert result["sl"] == 2150.0
        assert result["tp1"] == 2170.0
        assert result["sl_source"] == "ai"

    def test_optimize_sl_tp_with_tv_buy(self):
        from app.risk.tv_levels import optimize_sl_tp_from_tv
        payload = {
            "tv_available": True,
            "tv_chart_context": {
                "pine_levels": {
                    "support": [2152.0, 2145.0],
                    "resistance": [2160.0, 2168.0],
                }
            },
        }
        result = optimize_sl_tp_from_tv(payload, 2148.0, 2170.0, 2157.0, "BUY")
        assert result["tv_levels_available"] is True
        assert result["tp1"] == 2160.0

    def test_optimize_sl_tp_with_tv_sell(self):
        from app.risk.tv_levels import optimize_sl_tp_from_tv
        payload = {
            "tv_available": True,
            "tv_chart_context": {
                "pine_levels": {
                    "support": [2152.0, 2145.0],
                    "resistance": [2160.0, 2168.0],
                }
            },
        }
        result = optimize_sl_tp_from_tv(payload, 2165.0, 2145.0, 2157.0, "SELL")
        assert result["tv_levels_available"] is True
        assert result["sl"] == 2160.0
