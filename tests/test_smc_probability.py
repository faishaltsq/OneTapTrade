from app.ai_engine.schemas import Decision, EntryType
from app.analysis.smc_probability import (
    build_rule_based_hold_decision,
    core_decision_from_semantic,
    score_smc_setup,
)


def _payload(direction="bullish", spread=10, rr=2.0, profile="MEDIUM"):
    filter_trend = "BULLISH" if direction == "bullish" else "BEARISH"
    execution_trend = filter_trend
    return {
        "symbol": "EURUSD.m",
        "current_price": {
            "bid": 1.1000,
            "ask": 1.1002,
            "mid": 1.1001,
            "spread_points": spread,
        },
        "risk_config": {"risk_profile": profile, "min_risk_reward": 1.5},
        "major_trend": {
            "bias": "D1_BULLISH" if direction == "bullish" else "D1_BEARISH",
            "allowed_directions": ["BUY" if direction == "bullish" else "SELL"],
        },
        "higher_timeframe": {
            "timeframe": "D1",
            "market_structure": {"trend": filter_trend},
            "current_candle": {"close": 1.1001},
        },
        "secondary_timeframe": {
            "timeframe": "H4",
            "market_structure": {"trend": filter_trend},
            "current_candle": {"close": 1.1001},
        },
        "primary_timeframe": {
            "timeframe": "H1",
            "market_structure": {"trend": execution_trend},
            "current_candle": {"close": 1.1001},
        },
        "entry_timeframe": {
            "timeframe": "M5",
            "market_structure": {"trend": execution_trend},
            "current_candle": {"close": 1.1001},
        },
        "profile_timeframes": {
            "M15": {
                "timeframe": "M15",
                "market_structure": {"trend": execution_trend},
                "current_candle": {"close": 1.1001},
            }
        },
        "smc": {
            "choch": {"m5": {"bullish_choch": [{"price": 1.0990}], "bearish_choch": []}},
            "liquidity_levels": [{"type": "low", "price": 1.0985}],
            "fvg_zones": [{"direction": direction, "top": 1.1010, "bottom": 1.1000}],
            "order_blocks": {
                "demand": [{"low": 1.0980, "high": 1.0990}],
                "supply": [{"low": 1.1020, "high": 1.1030}],
            },
            "h1_swings": {"highs": [{"price": 1.1050}], "lows": [{"price": 1.0950}]},
            "m5_swings": {"highs": [{"price": 1.1030}], "lows": [{"price": 1.0980}]},
        },
        "entry_plan_context": {
            "risk_reward_to_tp1": rr,
            "entry_available": True,
            "sl_available": True,
            "tp_available": True,
        },
    }


def test_aligned_bullish_returns_buy_setup():
    result = score_smc_setup(_payload("bullish"), risk_profile="MEDIUM")

    assert result["pre_ai_decision"] == "BUY_SETUP"
    assert result["bias"] == "bullish"
    assert result["final_score"] >= 70
    assert core_decision_from_semantic(result["pre_ai_decision"]) == "BUY"


def test_structure_conflict_forces_no_trade():
    payload = _payload("bullish")
    payload["primary_timeframe"]["market_structure"]["trend"] = "BEARISH"

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["pre_ai_decision"] == "NO_TRADE"
    assert result["forced_no_trade"] is True
    assert any(adj["factor"] == "structure_conflict" for adj in result["adjustments"])


def test_high_spread_forces_no_trade():
    result = score_smc_setup(_payload("bullish", spread=999), risk_profile="MEDIUM")

    assert result["pre_ai_decision"] == "NO_TRADE"
    assert result["forced_no_trade"] is True
    assert any(adj["factor"] == "spread_high" for adj in result["adjustments"])


def test_low_rr_forces_no_trade():
    result = score_smc_setup(_payload("bullish", rr=1.0), risk_profile="MEDIUM")

    assert result["pre_ai_decision"] == "NO_TRADE"
    assert any(adj["factor"] == "risk_reward_low" for adj in result["adjustments"])


def test_missing_levels_requires_manual_confirmation():
    payload = _payload("bullish")
    payload["entry_plan_context"] = {
        "risk_reward_to_tp1": None,
        "entry_available": False,
        "sl_available": False,
        "tp_available": False,
    }

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["entry_sl_tp_note"] == "manual confirmation required"
    assert "manual confirmation required" in result["risk_notes"]


def test_high_profile_uses_h1_h4_filter_and_m5_m15_execution():
    result = score_smc_setup(_payload("bullish", profile="HIGH"), risk_profile="HIGH")

    assert result["timeframe_model"]["filter_timeframes"] == ["H1", "H4"]
    assert result["timeframe_model"]["execution_timeframes"] == ["M5", "M15"]


def test_trend_alignment_without_real_smc_confluence_waits():
    payload = _payload("bullish")
    payload["current_price"]["mid"] = 1.0999
    payload["smc"]["choch"] = {}
    payload["smc"]["liquidity_levels"] = []
    payload["smc"]["fvg_zones"] = []
    payload["smc"]["order_blocks"] = {"demand": [], "supply": []}

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["final_score"] >= 70
    assert result["pre_ai_decision"] == "WAIT"
    assert any(adj["factor"] == "missing_smc_confluence" for adj in result["adjustments"])


def test_low_profile_override_enforces_profile_min_rr_when_payload_min_absent():
    payload = _payload("bullish", rr=2.0, profile="MEDIUM")
    payload["risk_config"].pop("min_risk_reward")

    result = score_smc_setup(payload, risk_profile="LOW")

    assert result["pre_ai_decision"] == "NO_TRADE"
    assert result["forced_no_trade"] is True
    assert any(
        adj["factor"] == "risk_reward_low" and "2.5" in adj["reason"]
        for adj in result["adjustments"]
    )


def test_low_profile_floor_overrides_lower_payload_min_rr():
    payload = _payload("bullish", rr=2.0, profile="MEDIUM")
    payload["risk_config"]["min_risk_reward"] = 1.5

    result = score_smc_setup(payload, risk_profile="LOW")

    assert result["pre_ai_decision"] == "NO_TRADE"
    assert result["forced_no_trade"] is True
    assert any(
        adj["factor"] == "risk_reward_low" and "2.5" in adj["reason"]
        for adj in result["adjustments"]
    )


def test_liquidity_only_setup_waits_without_strong_smc_confluence():
    payload = _payload("bullish")
    payload["current_price"]["mid"] = 1.0999
    payload["smc"]["choch"] = {}
    payload["smc"]["fvg_zones"] = []
    payload["smc"]["order_blocks"] = {"demand": [], "supply": []}

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["final_score"] >= 70
    assert result["pre_ai_decision"] == "WAIT"
    assert any(adj["factor"] == "liquidity_clue" for adj in result["adjustments"])
    assert any(adj["factor"] == "missing_smc_confluence" for adj in result["adjustments"])


def test_medium_filter_conflict_forces_no_trade_even_with_strong_confluence():
    payload = _payload("bullish")
    payload["current_price"]["mid"] = 1.0999
    payload["higher_timeframe"]["market_structure"]["trend"] = "BULLISH"
    payload["secondary_timeframe"]["market_structure"]["trend"] = "BEARISH"

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["pre_ai_decision"] == "NO_TRADE"
    assert result["forced_no_trade"] is True
    assert any(adj["factor"] == "structure_conflict" for adj in result["adjustments"])


def test_fvg_only_setup_waits_without_entry_grade_confluence():
    payload = _payload("bullish")
    payload["current_price"]["mid"] = 1.0999
    payload["smc"]["choch"] = {}
    payload["smc"]["liquidity_levels"] = []
    payload["smc"]["order_blocks"] = {"demand": [], "supply": []}

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["final_score"] >= 70
    assert result["pre_ai_decision"] == "WAIT"
    assert any(adj["factor"] == "aligned_fvg" for adj in result["adjustments"])
    assert any(adj["factor"] == "missing_smc_confluence" for adj in result["adjustments"])


def test_ob_only_setup_waits_without_entry_grade_confluence():
    payload = _payload("bullish")
    payload["current_price"]["mid"] = 1.0999
    payload["smc"]["choch"] = {}
    payload["smc"]["liquidity_levels"] = []
    payload["smc"]["fvg_zones"] = []

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["final_score"] >= 70
    assert result["pre_ai_decision"] == "WAIT"
    assert any(adj["factor"] == "aligned_order_block" for adj in result["adjustments"])
    assert any(adj["factor"] == "missing_smc_confluence" for adj in result["adjustments"])


def test_bos_only_setup_waits_without_entry_grade_confluence():
    payload = _payload("bullish")
    payload["current_price"]["mid"] = 1.0999
    payload["smc"]["choch"] = {}
    payload["smc"]["liquidity_levels"] = []
    payload["smc"]["fvg_zones"] = []
    payload["smc"]["order_blocks"] = {"demand": [], "supply": []}
    payload["smc"]["bos"] = {"m5": {"bullish_bos": [{"price": 1.1010}], "bearish_bos": []}}

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["final_score"] >= 70
    assert result["pre_ai_decision"] == "WAIT"
    assert any(adj["factor"] == "bos_confirmation" for adj in result["adjustments"])
    assert any(adj["factor"] == "missing_smc_confluence" for adj in result["adjustments"])


def test_high_news_risk_forces_no_trade_for_supported_payload_shapes():
    for news_risk in ("high", {"level": "high"}, {"risk": "high"}):
        payload = _payload("bullish")
        payload["news_risk"] = news_risk

        result = score_smc_setup(payload, risk_profile="MEDIUM")

        assert result["pre_ai_decision"] == "NO_TRADE"
        assert result["forced_no_trade"] is True
        assert any(adj["factor"] == "news_risk_high" for adj in result["adjustments"])


def test_unknown_rr_penalizes_but_does_not_force_no_trade_pre_ai():
    payload = _payload("bullish")
    payload["entry_plan_context"]["risk_reward_to_tp1"] = None
    payload["entry_plan_context"]["entry_available"] = True
    payload["entry_plan_context"]["sl_available"] = True
    payload["entry_plan_context"]["tp_available"] = True

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["forced_no_trade"] is False
    assert any(adj["factor"] == "risk_reward_unknown" for adj in result["adjustments"])
    assert any("R:R unknown" in w for w in result["weaknesses"])
    assert result["final_score"] < 80


def test_malformed_swings_do_not_crash_and_skip_premium_discount():
    payload = _payload("bullish")
    payload["smc"]["h1_swings"] = {"highs": [None], "lows": [None]}

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert "Premium/discount unavailable from swing range" in result["weaknesses"]


def test_aligned_bearish_returns_sell_setup():
    payload = _payload("bearish")
    payload["smc"]["choch"] = {"m5": {"bullish_choch": [], "bearish_choch": [{"price": 1.1010}]}}

    result = score_smc_setup(payload, risk_profile="MEDIUM")

    assert result["pre_ai_decision"] == "SELL_SETUP"
    assert result["bias"] == "bearish"
    assert result["final_score"] >= 70
    assert core_decision_from_semantic(result["pre_ai_decision"]) == "SELL"


def test_high_profile_m15_fallback_weakness_when_m15_missing():
    payload = _payload("bullish", profile="HIGH")
    payload["profile_timeframes"] = {}

    result = score_smc_setup(payload, risk_profile="HIGH")

    assert result["timeframe_model"]["timeframe_fallback"] is not None
    assert any(adj["factor"] == "timeframe_fallback" for adj in result["adjustments"])
    assert any("M15 unavailable" in w for w in result["weaknesses"])


def test_rule_based_hold_decision_never_allows_execution():
    score = {
        "final_score": 65,
        "pre_ai_decision": "BUY_SETUP",
        "risk_notes": ["manual confirmation required"],
        "invalidation": "manual confirmation required",
    }

    result = build_rule_based_hold_decision(score, _payload("bullish"))

    assert result.decision == Decision.HOLD
    assert result.confidence == 0.65
    assert result.entry_plan.entry_type == EntryType.NONE
    assert result.execution_permission.ai_allows_execution is False
    assert result.risk_notes.main_risk == "manual confirmation required"
