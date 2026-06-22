import sys

sys.path.insert(0, r'C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade\ai-trading-executor')


def test_user_prompt_includes_active_profile_thresholds():
    from app.ai_engine.prompt_builder import build_user_prompt
    from app.config import settings

    original_profile = settings.risk_profile
    try:
        settings.risk_profile = "HIGH"

        prompt = build_user_prompt({"symbol": "XAUUSDm", "bid": 2010.0})

        assert "Risk profile: HIGH" in prompt
        assert "Minimum confidence: 40%" in prompt
        assert "Minimum R:R" not in prompt
        assert "SL range" not in prompt
    finally:
        settings.risk_profile = original_profile


def test_system_prompt_explains_high_profile_aggressive_entries():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original_profile = settings.risk_profile
    original_mode = settings.strategy_mode
    try:
        settings.risk_profile = "HIGH"
        settings.strategy_mode = "SMC_AI"
        prompt = build_system_prompt()

        assert "HIGH profile" in prompt
        assert "Min confidence 40%" in prompt
        assert "H1 trend" in prompt
        assert "M5 is trigger" in prompt
        assert "M5 momentum" in prompt
        assert "ignore spread" in prompt.lower()
        assert "stop_loss" in prompt
        assert "take_profit_1" in prompt
        assert "D1 major trend" in prompt
    finally:
        settings.risk_profile = original_profile
        settings.strategy_mode = original_mode


def test_prompt_does_not_hardcode_sl_or_rr_constraints():
    from app.ai_engine.prompt_builder import build_system_prompt, build_user_prompt
    from app.config import settings

    original_mode = settings.strategy_mode
    original_profile = settings.risk_profile
    try:
        settings.strategy_mode = "SMC_AI"
        settings.risk_profile = "MEDIUM"
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt({"symbol": "XAUUSDm", "current_price": {"bid": 2000, "ask": 2001}})
        combined = system_prompt + "\n" + user_prompt

        assert "SL range" not in combined
        assert "Minimum R:R" not in combined
        assert "minimum profile R:R" not in combined
        assert "AI chooses stop_loss and take_profit_1" in combined
    finally:
        settings.strategy_mode = original_mode
        settings.risk_profile = original_profile


def test_system_prompt_includes_d1_and_position_lock_rules():
    from app.ai_engine.prompt_builder import build_system_prompt

    prompt = build_system_prompt()

    assert "D1 major trend is a hard filter" in prompt
    assert "D1_BULLISH" in prompt and "only BUY" in prompt
    assert "D1_BEARISH" in prompt and "only SELL" in prompt
    assert "D1_RANGING" in prompt and "breakout + retest" in prompt
    assert "Same-direction add-ons are allowed" in prompt
    assert "Opposite direction is blocked" in prompt


def test_system_prompt_uses_ema50_ema200_and_rsi_25_75_thresholds():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original_mode = settings.strategy_mode
    try:
        settings.strategy_mode = "SMC_AI"
        prompt = build_system_prompt()

        assert "EMA50 above EMA200" in prompt
        assert "EMA50 below EMA200" in prompt
        assert ">75" in prompt
        assert "<25" in prompt
        assert ">70" not in prompt
        assert "<30" not in prompt
    finally:
        settings.strategy_mode = original_mode


def test_system_prompt_prefers_smc_limit_entries_and_restricts_market():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original_mode = settings.strategy_mode
    try:
        settings.strategy_mode = "SMC_AI"
        prompt = build_system_prompt()

        assert "Prefer LIMIT entries" in prompt
        assert "BUY_LIMIT" in prompt and "demand order block" in prompt
        assert "SELL_LIMIT" in prompt and "supply order block" in prompt
        assert "MARKET only when confidence is above 50%" in prompt
        assert "trend-following" in prompt
    finally:
        settings.strategy_mode = original_mode


def test_smc_ai_prompt_contains_smc_keywords():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original = settings.strategy_mode
    original_profile = settings.risk_profile
    try:
        settings.strategy_mode = "SMC_AI"
        settings.risk_profile = "MEDIUM"
        prompt = build_system_prompt()

        assert "order blocks" in prompt.lower()
        assert "FVG" in prompt or "fair value gap" in prompt.lower()
        assert "CHoCH" in prompt
        assert "liquidity" in prompt.lower()
        assert "D1 major trend" in prompt
    finally:
        settings.strategy_mode = original
        settings.risk_profile = original_profile


def test_ai_only_prompt_omits_smc_priority_and_uses_first_principles():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original = settings.strategy_mode
    original_profile = settings.risk_profile
    try:
        settings.strategy_mode = "AI_ONLY"
        settings.risk_profile = "MEDIUM"
        prompt = build_system_prompt()

        assert "first principles" in prompt.lower()
        assert "INDEPENDENTLY" in prompt
        assert "D1 major trend" in prompt
        assert "ORDER BLOCKS" not in prompt
    finally:
        settings.strategy_mode = original
        settings.risk_profile = original_profile


def test_swing_style_block_present_for_low_profile():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original_profile = settings.risk_profile
    original_mode = settings.strategy_mode
    try:
        settings.risk_profile = "LOW"
        settings.strategy_mode = "SMC_AI"
        prompt = build_system_prompt()

        assert "SWING" in prompt
        assert "days to weeks" in prompt
        assert "H4/D1" in prompt
        assert "100-500" in prompt
    finally:
        settings.risk_profile = original_profile
        settings.strategy_mode = original_mode


def test_daytrade_style_block_present_for_medium_profile():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original_profile = settings.risk_profile
    original_mode = settings.strategy_mode
    try:
        settings.risk_profile = "MEDIUM"
        settings.strategy_mode = "AI_ONLY"
        prompt = build_system_prompt()

        assert "DAYTRADE" in prompt
        assert "hours to days" in prompt
        assert "H1/H4" in prompt
        assert "50-150" in prompt
    finally:
        settings.risk_profile = original_profile
        settings.strategy_mode = original_mode


def test_scalping_style_block_present_for_high_profile():
    from app.ai_engine.prompt_builder import build_system_prompt
    from app.config import settings

    original_profile = settings.risk_profile
    original_mode = settings.strategy_mode
    try:
        settings.risk_profile = "HIGH"
        settings.strategy_mode = "SMC_AI"
        prompt = build_system_prompt()

        assert "SCALPING" in prompt
        assert "minutes to hours" in prompt
        assert "M5/M15" in prompt
        assert "15-50" in prompt
    finally:
        settings.risk_profile = original_profile
        settings.strategy_mode = original_mode


def test_user_prompt_includes_strategy_mode_and_style_header():
    from app.ai_engine.prompt_builder import build_user_prompt
    from app.config import settings

    original_mode = settings.strategy_mode
    original_profile = settings.risk_profile
    try:
        settings.strategy_mode = "AI_ONLY"
        settings.risk_profile = "HIGH"
        prompt = build_user_prompt({"symbol": "XAUUSD"})

        assert "Strategy mode:" in prompt
        assert "Strategy mode: AI Only" in prompt
        assert "Trading style:" in prompt
        assert "SCALPING" in prompt
        assert "Entry TF:" in prompt
        assert "Hold:" in prompt
    finally:
        settings.strategy_mode = original_mode
        settings.risk_profile = original_profile
