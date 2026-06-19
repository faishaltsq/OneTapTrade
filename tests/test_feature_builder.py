import pandas as pd
import numpy as np

from app.analysis.feature_builder import build_market_payload


def _make_df(count=100, base=2000.0, volatility=5.0) -> pd.DataFrame:
    np.random.seed(42)
    times = pd.date_range(start="2026-06-18 00:00", periods=count, freq="15min")
    close = base + np.cumsum(np.random.randn(count) * volatility)
    high = close + abs(np.random.randn(count) * 2)
    low = close - abs(np.random.randn(count) * 2)
    open_ = close - np.random.randn(count)

    df = pd.DataFrame(
        {
            "time": times,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": np.random.randint(100, 1000, count),
            "spread": np.random.randint(1, 10, count),
        }
    )
    df.set_index("time", inplace=True)
    return df


class TestBuildMarketPayload:

    def test_output_has_all_required_keys(self):
        df_d1 = _make_df(20)
        df_h4 = _make_df(50)
        df_h1 = _make_df(100)
        df_m15 = _make_df(200)

        result = build_market_payload(
            symbol="XAUUSD",
            df_d1=df_d1,
            df_h4=df_h4,
            df_h1=df_h1,
            df_m15=df_m15,
            bid=2010.0,
            ask=2010.5,
            spread_points=5,
            account_info={
                "balance": 10000.0,
                "equity": 10050.0,
                "daily_drawdown_percent": 0.3,
                "open_positions_count": 0,
            },
        )

        expected_keys = [
            "symbol",
            "timestamp",
            "current_price",
            "higher_timeframe",
            "primary_timeframe",
            "secondary_timeframe",
            "entry_timeframe",
            "overall_regime",
            "orderflow_proxy",
            "account_context",
            "risk_config",
        ]

        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

        assert result["symbol"] == "XAUUSD"
        assert result["current_price"]["bid"] == 2010.0
        assert result["current_price"]["ask"] == 2010.5
        assert result["current_price"]["spread_points"] == 5

        assert result["higher_timeframe"]["timeframe"] == "D1"
        assert result["primary_timeframe"]["timeframe"] == "H1"
        assert result["entry_timeframe"]["timeframe"] == "M5"

    def test_entry_timeframe_is_m5(self):
        df_entry = _make_df(100)

        result = build_market_payload(
            symbol="XAUUSD",
            df_d1=None,
            df_h4=None,
            df_h1=None,
            df_m15=df_entry,
            bid=2010.0,
            ask=2010.5,
            spread_points=5,
        )

        assert result["entry_timeframe"]["timeframe"] == "M5"
        assert "orderflow" in result["entry_timeframe"]

    def test_indicators_include_ema200_and_rsi_state(self):
        df_entry = _make_df(250)

        result = build_market_payload(
            symbol="XAUUSD",
            df_d1=None,
            df_h4=None,
            df_h1=None,
            df_m15=df_entry,
            bid=2010.0,
            ask=2010.5,
            spread_points=5,
        )

        indicators = result["entry_timeframe"]["indicators"]
        assert "ema_50" in indicators
        assert "ema_200" in indicators
        assert "rsi_state" in indicators
        assert indicators["ema_200"] is not None
        assert indicators["rsi_state"] in {"OVERSOLD", "NORMAL", "OVERBOUGHT", "MENUNGGU_DATA"}
        assert "ema_20" not in indicators

    def test_handles_empty_dataframe(self):
        empty_df = pd.DataFrame()

        result = build_market_payload(
            symbol="XAUUSD",
            df_d1=None,
            df_h4=None,
            df_h1=empty_df,
            df_m15=None,
            bid=2010.0,
            ask=2010.5,
            spread_points=5,
        )

        assert "higher_timeframe" in result
        assert "primary_timeframe" in result
        assert "entry_timeframe" in result

        assert result["higher_timeframe"]["bars_count"] == 0
        assert result["primary_timeframe"]["bars_count"] == 0

    def test_handles_none_optional_inputs(self):
        df_m15 = _make_df(100)

        result = build_market_payload(
            symbol="XAUUSD",
            df_d1=None,
            df_h4=None,
            df_h1=None,
            df_m15=df_m15,
            bid=2010.0,
            ask=2010.5,
            spread_points=5,
            tick_data=None,
            depth_data=None,
            account_info=None,
        )

        assert "entry_timeframe" in result
        assert result["entry_timeframe"]["bars_count"] > 0
        assert result["account_context"] is not None
        assert "balance" in result["account_context"]

    def test_account_context_defaults(self):
        df_m15 = _make_df(50)

        result = build_market_payload(
            symbol="XAUUSD",
            df_d1=None,
            df_h4=None,
            df_h1=None,
            df_m15=df_m15,
            bid=2010.0,
            ask=2010.5,
            spread_points=5,
            account_info=None,
        )

        ctx = result["account_context"]
        assert ctx["balance"] is None
        assert ctx["has_open_position"] is False

    def test_risk_config_present(self):
        df_m15 = _make_df(50)

        result = build_market_payload(
            symbol="XAUUSD",
            df_d1=None,
            df_h4=None,
            df_h1=None,
            df_m15=df_m15,
            bid=2010.0,
            ask=2010.5,
            spread_points=5,
        )

        cfg = result["risk_config"]
        assert "risk_profile" in cfg
        assert "min_risk_reward" in cfg
        assert "max_open_positions" in cfg

    def test_major_trend_and_open_position_state_present(self, monkeypatch):
        df_d1 = _make_df(60)
        df_h1 = _make_df(100)
        df_m5 = _make_df(100)
        monkeypatch.setattr(
            "app.services.position_state_service.get_open_position_state",
            lambda symbol: {"symbol": symbol, "side": "BUY", "ticket": 1},
        )

        result = build_market_payload(
            symbol="XAUUSD.c",
            df_d1=df_d1,
            df_h4=None,
            df_h1=df_h1,
            df_m15=df_m5,
            bid=2010.0,
            ask=2010.5,
            spread_points=5,
        )

        assert "major_trend" in result
        assert "bias" in result["major_trend"]
        assert "allowed_directions" in result["major_trend"]
        assert result["open_position_state"]["side"] == "BUY"

    def test_current_price_calculates_mid(self):
        df_m15 = _make_df(50)

        result = build_market_payload(
            symbol="XAUUSD",
            df_d1=None,
            df_h4=None,
            df_h1=None,
            df_m15=df_m15,
            bid=2010.0,
            ask=2016.0,
            spread_points=6,
        )

        assert result["current_price"]["mid"] == 2013.0

    def test_multiple_timeframes_produces_different_counts(self):
        df_d1 = _make_df(15)
        df_h4 = _make_df(30)
        df_h1 = _make_df(60)
        df_m15 = _make_df(120)

        result = build_market_payload(
            symbol="XAUUSD",
            df_d1=df_d1,
            df_h4=df_h4,
            df_h1=df_h1,
            df_m15=df_m15,
            bid=2010.0,
            ask=2010.5,
            spread_points=5,
        )

        assert result["higher_timeframe"]["bars_count"] <= 15
        assert result["primary_timeframe"]["bars_count"] <= 60
        assert result["entry_timeframe"]["bars_count"] <= 120
