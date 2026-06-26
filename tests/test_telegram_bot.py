import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, r'C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade\ai-trading-executor')


def test_help_command_is_registered():
    from app.telegram_bot.commands import get_command_handlers

    commands = set()
    for handler in get_command_handlers():
        commands.update(handler.commands)

    assert "help" in commands


def _keyboard_callback_data(markup) -> set[str]:
    values = set()
    for row in markup.inline_keyboard:
        for button in row:
            values.add(button.callback_data)
    return values


def _keyboard_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_settings_keyboard_contains_risk_controls():
    from app.telegram_bot.message_templates import build_settings_keyboard

    callbacks = _keyboard_callback_data(build_settings_keyboard())

    assert "MENU_RISK_LOW" in callbacks
    assert "MENU_RISK_MEDIUM" in callbacks
    assert "MENU_RISK_HIGH" in callbacks
    assert "MENU_RISK_TRADE_025" in callbacks
    assert "MENU_RISK_TRADE_050" in callbacks
    assert "MENU_RISK_TRADE_100" in callbacks


def test_signal_message_uses_m5_entry_label():
    from app.ai_engine.schemas import (
        AIDecisionResponse,
        ConfidenceLabel,
        Decision,
        MarketRegime,
        TimeframeBias,
    )
    from app.telegram_bot.message_templates import format_signal_message

    decision = AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.4,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.RANGING,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BEARISH,
    )

    message = format_signal_message(decision, {"approved": False, "reason": "Hold"}, "XAUUSDm")

    assert "M5: BEARISH" in message
    assert "M15" not in message


def test_signal_message_converts_forex_price_distance_to_pips():
    from app.ai_engine.schemas import (
        AIDecisionResponse,
        ConfidenceLabel,
        Decision,
        EntryPlan,
        EntryType,
        MarketRegime,
        TimeframeBias,
    )
    from app.telegram_bot.message_templates import format_signal_message

    decision = AIDecisionResponse(
        decision=Decision.BUY,
        confidence=0.72,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.TRENDING_UP,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BULLISH,
        entry_plan=EntryPlan(
            entry_type=EntryType.LIMIT,
            preferred_entry_price=0.56465,
            stop_loss=0.56440,
            take_profit_1=0.56525,
            risk_reward_to_tp1=2.4,
        ),
    )
    market_payload = {
        "current_price": {"bid": 0.56511, "ask": 0.56513},
        "major_trend": {"bias": "D1_BULLISH", "h1_bias": "BULLISH", "h1_alignment": "ALIGNED"},
        "higher_timeframe": {"market_structure": {"trend": "BULLISH"}, "indicators": {}},
        "primary_timeframe": {"market_structure": {"trend": "BULLISH"}, "indicators": {}},
        "entry_timeframe": {"market_structure": {"trend": "BULLISH"}, "indicators": {}},
    }

    message = format_signal_message(decision, {"approved": True}, "NZDUSD.m", market_payload)

    assert "Risk: 7.30 pips | Reward: 1.20 pips | R:R 0.2" in message
    assert "Risk: 2.50 pips | Reward: 6.00 pips | R:R 2.4" in message


@pytest.mark.asyncio
async def test_send_trade_signal_sends_long_text_before_chart(monkeypatch):
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, MarketRegime, TimeframeBias
    from app.config import settings
    from app.telegram_bot import bot as bot_module

    decision = AIDecisionResponse(
        decision=Decision.BUY,
        confidence=0.65,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.TRENDING_UP,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BULLISH,
    )
    original_token = settings.telegram_bot_token
    original_chat_id = settings.telegram_allowed_chat_id
    original_application = bot_module._application

    class FakeBot:
        def __init__(self):
            self.messages = []
            self.photos = []

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)

        async def send_photo(self, **kwargs):
            self.photos.append(kwargs)

    fake_bot = FakeBot()
    try:
        settings.telegram_bot_token = "token"
        settings.telegram_allowed_chat_id = "123"
        bot_module._application = MagicMock(bot=fake_bot)
        long_signal = "x" * 2000

        async def fake_capture(*args, **kwargs):
            return [{"image": b"img"}]

        monkeypatch.setattr("app.telegram_bot.bot.format_signal_message", lambda *args, **kwargs: long_signal)
        monkeypatch.setattr("app.services.tv_autochart_service.draw_and_capture_multi_tf", fake_capture)
        monkeypatch.setattr("app.signal_bot.broadcast_signal", AsyncMock(return_value=True))

        sent = await bot_module.send_trade_signal(decision, {"symbol": "BTCUSD.m", "approved": True}, "decision-1", {})

        assert sent is True
        assert fake_bot.messages[0]["text"] == long_signal
        assert fake_bot.photos[0]["caption"] == "BTCUSD.m BUY chart"
    finally:
        bot_module._application = original_application
        settings.telegram_bot_token = original_token
        settings.telegram_allowed_chat_id = original_chat_id


@pytest.mark.asyncio
async def test_send_trade_signal_stores_symbol_metadata_on_pending_decision():
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, MarketRegime, TimeframeBias
    from app.config import settings
    from app.telegram_bot import bot as bot_module

    decision = AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.4,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.RANGING,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BEARISH,
    )
    original_token = settings.telegram_bot_token
    original_chat_id = settings.telegram_allowed_chat_id
    original_application = bot_module._application
    bot_module._pending_decisions.clear()
    bot_module._decision_symbols.clear()
    try:
        settings.telegram_bot_token = "token"
        settings.telegram_allowed_chat_id = "123"
        bot_module._application = MagicMock(bot=object())

        with patch("app.telegram_bot.bot.format_signal_message", return_value="signal"):
            with patch("app.telegram_bot.bot.send_message", new=AsyncMock(return_value=True)):
                sent = await bot_module.send_trade_signal(decision, {"symbol": "EURUSD.c", "approved": True}, "decision-1")

        assert sent is True
        assert bot_module._pending_decisions["decision-1"] is decision
        assert bot_module._decision_symbols["decision-1"] == "EURUSD.c"
    finally:
        bot_module._pending_decisions.clear()
        bot_module._decision_symbols.clear()
        bot_module._application = original_application
        settings.telegram_bot_token = original_token
        settings.telegram_allowed_chat_id = original_chat_id


def _market_payload_fixture():
    return {
        "current_price": {"bid": 2432.10, "ask": 2432.45, "spread_points": 35},
        "higher_timeframe": {
            "market_structure": {"trend": "BULLISH"},
            "indicators": {"rsi_14": 58.2, "rsi_state": "NORMAL", "ema_50": 2430.0, "ema_200": 2420.0},
        },
        "secondary_timeframe": {
            "market_structure": {"trend": "RANGING"},
            "indicators": {"rsi_14": 51.0, "rsi_state": "NORMAL", "ema_50": 2431.0, "ema_200": 2431.5},
        },
        "primary_timeframe": {
            "market_structure": {"trend": "BULLISH"},
            "indicators": {"rsi_14": 56.4, "rsi_state": "NORMAL", "ema_50": 2434.0, "ema_200": 2424.0},
        },
        "entry_timeframe": {
            "market_structure": {"trend": "BEARISH"},
            "indicators": {"rsi_14": 48.1, "rsi_state": "NORMAL", "ema_50": 2430.0, "ema_200": 2435.0},
        },
        "overall_regime": {"regime": "RANGING", "description": "Low momentum"},
        "orderflow_proxy": {"delta_proxy": {"bias": "SELL_PRESSURE"}, "dom_imbalance": None},
        "smc": {
            "choch": {"direction": "BEARISH"},
            "order_blocks": {
                "demand": [{"low": 2427.5, "high": 2429.0}],
                "supply": [{"low": 2440.0, "high": 2440.2}],
            },
            "liquidity_levels": [{"type": "EQUAL_HIGHS", "price": 2441.0}],
        },
    }


def test_market_trend_alert_hold_uses_dashboard_sections():
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, MarketRegime, TimeframeBias
    from app.telegram_bot.message_templates import format_market_trend_alert

    decision = AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.42,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.RANGING,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BEARISH,
        main_reason="M5 conflicts with H1.",
    )

    message = format_market_trend_alert(decision, "XAUUSD.c", _market_payload_fixture())

    assert "Market Trend — XAUUSD.c" in message
    assert "Bias Map" in message
    assert "Price" in message
    assert "Momentum" in message
    assert "SMC" in message
    assert "Orderflow" in message
    assert "Read" in message
    assert "Bid/Ask: 2432.1 / 2432.45" in message
    assert "M5 RSI: 48.1 (Normal)" in message
    assert "EMA50/200" in message


def test_market_trend_alert_uses_readable_fallbacks_and_ema_bias():
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, MarketRegime, TimeframeBias
    from app.telegram_bot.message_templates import format_market_trend_alert

    decision = AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.0,
        confidence_label=ConfidenceLabel.LOW,
        market_regime=MarketRegime.UNCLEAR,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
        main_reason="No clear trade setup.",
    )
    payload = {
        "current_price": {"bid": 113.036, "ask": 113.056, "spread_points": 20},
        "higher_timeframe": {
            "bars_count": 100,
            "market_structure": {"trend": "UNCLEAR"},
            "indicators": {"rsi_14": 50.0, "rsi_state": "NORMAL", "ema_50": 113.2, "ema_200": 112.9},
        },
        "secondary_timeframe": {
            "bars_count": 0,
            "market_structure": {},
            "indicators": {"rsi_14": None, "rsi_state": "MENUNGGU_DATA", "ema_50": None, "ema_200": None},
        },
        "primary_timeframe": {
            "bars_count": 100,
            "market_structure": {"trend": "UNCLEAR"},
            "indicators": {"rsi_14": 48.8701, "rsi_state": "NORMAL", "ema_50": 113.0, "ema_200": 113.2},
        },
        "entry_timeframe": {
            "bars_count": 100,
            "market_structure": {"trend": "UNCLEAR"},
            "indicators": {"rsi_14": 41.7974, "rsi_state": "NORMAL", "ema_50": 113.0, "ema_200": 113.1},
        },
        "overall_regime": {"regime": "UNCLEAR", "description": "Price range contracted."},
        "orderflow_proxy": {"delta_proxy": None, "dom_imbalance": None},
        "smc": {"choch": {}, "order_blocks": {}, "liquidity_levels": []},
    }

    message = format_market_trend_alert(decision, "AUDJPY.c", payload)

    assert "D1: Bullish" in message
    assert "H4: Menunggu data" in message
    assert "H1: Bearish" in message
    assert "M5: Bearish" in message
    assert "Regime: Belum ada bias jelas" in message
    assert "M5 RSI: 41.7974 (Normal) | EMA50/200: Bearish" in message
    assert "Delta: Menunggu data" in message
    assert "DOM: Menunggu data" in message
    assert "N/A" not in message
    assert "UNCLEAR" not in message


def test_market_trend_alert_buy_includes_trade_plan_and_risk_check():
    from app.ai_engine.schemas import (
        AIDecisionResponse,
        ConfidenceLabel,
        Decision,
        EntryPlan,
        EntryType,
        MarketRegime,
        TimeframeBias,
    )
    from app.telegram_bot.message_templates import format_market_trend_alert

    decision = AIDecisionResponse(
        decision=Decision.BUY,
        confidence=0.66,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.TRENDING_UP,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BULLISH,
        entry_plan=EntryPlan(
            entry_type=EntryType.MARKET,
            preferred_entry_price=2432.45,
            stop_loss=2427.5,
            take_profit_1=2440.2,
            risk_reward_to_tp1=1.8,
        ),
        main_reason="Momentum aligned.",
    )

    message = format_market_trend_alert(
        decision,
        "XAUUSD.c",
        _market_payload_fixture(),
        {"approved": True, "reason": "Risk OK"},
    )

    assert "Trade Plan" in message
    assert "Risk Check" in message
    assert "Entry:" in message
    assert "TP1: 2440.2" in message
    assert "Approved" in message


def test_positions_message_shows_floating_realized_and_total_pnl():
    from app.telegram_bot.message_templates import format_positions_message

    positions = [
        {"ticket": 1, "symbol": "XAUUSD.c", "type": 0, "volume": 0.01, "price_open": 2010, "sl": 2000, "tp": 2020, "profit": 5.0, "swap": -0.5},
        {"ticket": 2, "symbol": "EURUSD.c", "type": 1, "volume": 0.01, "price_open": 1.1, "sl": 1.2, "tp": 1.0, "profit": 3.0, "swap": 0.0},
    ]

    message = format_positions_message(positions, "ALL", realized_pnl=3.25)

    assert "Floating P&amp;L: $+7.50" in message
    assert "Today Realized P&amp;L: $+3.25" in message
    assert "Today Total P&amp;L: $+10.75" in message


def test_positions_message_shows_realized_pnl_when_no_positions():
    from app.telegram_bot.message_templates import format_positions_message

    message = format_positions_message([], "ALL", realized_pnl=-4.25)

    assert "Floating P&amp;L: $+0.00" in message
    assert "Today Realized P&amp;L: $-4.25" in message
    assert "Today Total P&amp;L: $-4.25" in message
    assert "No open positions" in message


class FakeUpdater:
    def __init__(self):
        self.polling_started = asyncio.Event()
        self.start_kwargs = None
        self.stopped = False

    async def start_polling(self, **kwargs):
        self.start_kwargs = kwargs
        self.polling_started.set()

    async def stop(self):
        self.stopped = True


class FakeApplication:
    def __init__(self):
        self.bot = object()
        self.updater = FakeUpdater()
        self.initialized = False
        self.started = False
        self.stopped = False
        self.shutdown_called = False

    async def initialize(self):
        self.initialized = True

    async def start(self):
        self.started = True

    def run_polling(self, **kwargs):
        raise AssertionError("run_polling must not be used inside the FastAPI event loop")

    async def stop(self):
        self.stopped = True

    async def shutdown(self):
        self.shutdown_called = True


@pytest.mark.asyncio
async def test_run_bot_uses_async_lifecycle_for_embedded_polling():
    from app.telegram_bot import bot as bot_module

    fake = FakeApplication()
    bot_module._application = fake

    task = asyncio.create_task(bot_module.run_bot())

    try:
        await asyncio.wait_for(fake.updater.polling_started.wait(), timeout=0.2)

        assert fake.initialized is True
        assert fake.started is True
        assert fake.updater.start_kwargs == {"drop_pending_updates": True}
        assert task.done() is False

        await bot_module.stop_bot()
        await asyncio.wait_for(task, timeout=0.2)

        assert fake.updater.stopped is True
        assert fake.stopped is True
        assert fake.shutdown_called is True
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        bot_module._application = None


class FakeCallbackUpdate:
    def __init__(self):
        self.effective_chat = MagicMock(id="123")
        self.callback_query = MagicMock()
        self.callback_query.message = MagicMock()
        self.callback_query.message.reply_text = AsyncMock()
        self.callback_query.answer = AsyncMock()
        self.callback_query.edit_message_text = AsyncMock()


class FakeMessageUpdate:
    def __init__(self):
        self.effective_chat = MagicMock(id="123")
        self.message = MagicMock()
        self.message.reply_text = AsyncMock()


@pytest.mark.asyncio
async def test_risk_callback_updates_runtime_profile_when_db_fails():
    from app.config import settings
    from app.telegram_bot.callbacks import menu_risk_callback

    original_chat_id = settings.telegram_allowed_chat_id
    original_profile = settings.risk_profile
    try:
        settings.telegram_allowed_chat_id = "123"
        settings.risk_profile = "LOW"
        update = FakeCallbackUpdate()

        with patch("app.database.repositories.update_bot_settings", side_effect=RuntimeError("db down")):
            with patch("app.telegram_bot.callbacks.send_main_menu", new=AsyncMock(return_value=True)):
                await menu_risk_callback(update, "HIGH")

        assert settings.risk_profile == "HIGH"
        update.callback_query.answer.assert_awaited()
    finally:
        settings.telegram_allowed_chat_id = original_chat_id
        settings.risk_profile = original_profile


@pytest.mark.asyncio
async def test_status_button_uses_global_open_positions_count():
    from app.config import settings
    from app.telegram_bot.callbacks import menu_status_callback

    original_chat_id = settings.telegram_allowed_chat_id
    original_default_symbol = settings.default_symbol
    try:
        settings.telegram_allowed_chat_id = "123"
        settings.default_symbol = "XAUUSD.c"
        update = FakeCallbackUpdate()

        def fake_open_positions_count(symbol=None):
            return 2 if symbol is None else 0

        with patch("app.mt5_connector.connection.is_mt5_connected", return_value=True):
            with patch("app.mt5_connector.account.get_balance", return_value=1000.0):
                with patch("app.mt5_connector.account.get_equity", return_value=1005.0):
                    with patch("app.mt5_connector.account.get_daily_drawdown_percent", return_value=0.0):
                        with patch("app.mt5_connector.positions.get_open_positions_count", side_effect=fake_open_positions_count):
                            await menu_status_callback(update, MagicMock())

        text = update.callback_query.edit_message_text.await_args.args[0]
        assert "Open Positions:</b> 2" in text
    finally:
        settings.telegram_allowed_chat_id = original_chat_id
        settings.default_symbol = original_default_symbol


@pytest.mark.asyncio
async def test_positions_button_shows_today_realized_pnl():
    from app.config import settings
    from app.telegram_bot.callbacks import menu_positions_callback

    original_chat_id = settings.telegram_allowed_chat_id
    try:
        settings.telegram_allowed_chat_id = "123"
        update = FakeCallbackUpdate()

        positions = [
            {"ticket": 1, "symbol": "XAUUSD.c", "type": 0, "volume": 0.01, "price_open": 2010, "sl": 2000, "tp": 2020, "profit": 2.0, "swap": 0.0},
        ]

        with patch("app.mt5_connector.connection.is_mt5_connected", return_value=True):
            with patch("app.mt5_connector.positions.get_open_positions", return_value=positions):
                with patch("app.telegram_bot.callbacks.get_today_realized_pnl", return_value=3.0):
                    await menu_positions_callback(update, MagicMock())

        text = update.callback_query.edit_message_text.await_args.args[0]
        assert "Today Realized P&amp;L: $+3.00" in text
        assert "Today Total P&amp;L: $+5.00" in text
    finally:
        settings.telegram_allowed_chat_id = original_chat_id


@pytest.mark.asyncio
async def test_edit_message_ignores_message_not_modified_error():
    from app.telegram_bot.callbacks import _edit_message

    update = FakeCallbackUpdate()
    update.callback_query.edit_message_text.side_effect = Exception(
        "Message is not modified: specified new message content and reply markup are exactly the same"
    )

    await _edit_message(update, "same message")

    update.callback_query.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_settings_command_sends_keyboard():
    from app.config import settings
    from app.telegram_bot.commands import settings_command

    original_chat_id = settings.telegram_allowed_chat_id
    try:
        settings.telegram_allowed_chat_id = "123"
        update = FakeMessageUpdate()

        await settings_command(update, MagicMock())

        kwargs = update.message.reply_text.await_args.kwargs
        assert kwargs["reply_markup"] is not None
    finally:
        settings.telegram_allowed_chat_id = original_chat_id


@pytest.mark.asyncio
async def test_risk_trade_callback_updates_runtime_percent():
    from app.config import settings
    from app.telegram_bot.callbacks import menu_risk_trade_callback

    original_chat_id = settings.telegram_allowed_chat_id
    original_risk = settings.risk_per_trade_percent
    try:
        settings.telegram_allowed_chat_id = "123"
        settings.risk_per_trade_percent = 0.5
        update = FakeCallbackUpdate()

        with patch("app.database.repositories.update_bot_settings", return_value={"risk_per_trade_percent": 1.0}) as update_settings:
            await menu_risk_trade_callback(update, 1.0)

        assert settings.risk_per_trade_percent == 1.0
        update_settings.assert_called_once_with({"risk_per_trade_percent": 1.0})
        update.callback_query.answer.assert_awaited()
    finally:
        settings.telegram_allowed_chat_id = original_chat_id
        settings.risk_per_trade_percent = original_risk


@pytest.mark.asyncio
async def test_risk_trade_callback_rejects_invalid_percent():
    from app.config import settings
    from app.telegram_bot.callbacks import menu_risk_trade_callback

    original_chat_id = settings.telegram_allowed_chat_id
    original_risk = settings.risk_per_trade_percent
    try:
        settings.telegram_allowed_chat_id = "123"
        settings.risk_per_trade_percent = 0.5
        update = FakeCallbackUpdate()

        await menu_risk_trade_callback(update, 2.0)

        assert settings.risk_per_trade_percent == 0.5
        update.callback_query.answer.assert_awaited_with("Invalid risk", show_alert=True)
    finally:
        settings.telegram_allowed_chat_id = original_chat_id
        settings.risk_per_trade_percent = original_risk


def test_settings_message_says_sl_tp_are_ai_owned():
    from app.telegram_bot.message_templates import format_settings_message

    message = format_settings_message()

    assert "SL range:" in message
    assert "TP range:" in message
    assert "AI-owned" not in message
    assert "Scalping Settings" not in message
    assert "Strategy:" in message


def test_main_menu_contains_strategy_toggle_buttons():
    from app.telegram_bot.message_templates import build_main_menu_keyboard

    callbacks = _keyboard_callback_data(build_main_menu_keyboard(strategy_mode="SMC_AI"))

    assert "MENU_STRATEGY_SMC" in callbacks
    assert "MENU_STRATEGY_AI" in callbacks


def test_main_menu_shows_stop_trade_when_running():
    from app.telegram_bot.message_templates import build_main_menu_keyboard

    texts = _keyboard_texts(build_main_menu_keyboard(is_paused=False))

    assert "🛑 Stop Trade" in texts
    assert "⏸️ Pause" not in texts


def test_main_menu_shows_resume_trade_when_stopped():
    from app.telegram_bot.message_templates import build_main_menu_keyboard

    texts = _keyboard_texts(build_main_menu_keyboard(is_paused=True))

    assert "▶️ Resume Trade" in texts
    assert "▶️ Resume" not in texts


def test_status_message_uses_stop_trade_wording():
    from app.telegram_bot.message_templates import format_status_message

    stopped = format_status_message({"paused": True, "mode": "AUTO_DEMO", "symbol": "XAUUSD"})
    running = format_status_message({"paused": False, "mode": "AUTO_DEMO", "symbol": "XAUUSD"})

    assert "TRADING STOPPED" in stopped
    assert "TRADING PAUSED" not in stopped
    assert "Trading Running" in running


def test_welcome_message_uses_stop_trade_wording():
    from app.telegram_bot.message_templates import format_welcome_message

    message = format_welcome_message()

    assert "/pause - Stop Trade" in message
    assert "/resume - Resume Trade" in message
    assert "Pause trading loop" not in message
    assert "Resume trading loop" not in message


def test_callback_menu_keyboard_uses_runtime_stopped_state():
    from app.telegram_bot.callbacks import _current_main_menu_keyboard

    loop = MagicMock()
    loop.is_paused.return_value = False
    loop.status.mode = "AUTO_DEMO"
    loop.status.active_symbol = "ALL"

    with patch("app.telegram_bot.callbacks.get_trading_loop", return_value=loop):
        texts = _keyboard_texts(_current_main_menu_keyboard())

    assert "🛑 Stop Trade" in texts
    assert "▶️ Resume Trade" not in texts


@pytest.mark.asyncio
async def test_main_menu_header_uses_stop_trade_wording():
    from app.telegram_bot import bot

    original_loop = bot._trading_loop_ref
    loop = MagicMock()
    loop.is_paused.return_value = True
    loop.status.mode = "AUTO_DEMO"
    loop.status.active_symbol = "ALL"
    try:
        bot._trading_loop_ref = loop
        with patch("app.telegram_bot.bot.send_message", new=AsyncMock(return_value=True)) as send_message:
            await bot.send_main_menu()

        header = send_message.await_args.args[0]
        assert "🛑 Stop Trade" in header
        assert "Paused" not in header
    finally:
        bot._trading_loop_ref = original_loop


def test_main_menu_uses_runtime_strategy_mode_by_default():
    from app.telegram_bot.message_templates import build_main_menu_keyboard
    from app.config import settings

    original_mode = settings.strategy_mode
    try:
        settings.strategy_mode = "AI_ONLY"
        markup = build_main_menu_keyboard()
        labels = [button.text for row in markup.inline_keyboard for button in row]

        assert any("AI Only" in label and "\u2705" in label for label in labels)
        assert all(not ("SMC+AI" in label and "\u2705" in label) for label in labels)
    finally:
        settings.strategy_mode = original_mode


def test_settings_keyboard_contains_strategy_toggle_buttons():
    from app.telegram_bot.message_templates import build_settings_keyboard

    callbacks = _keyboard_callback_data(build_settings_keyboard())

    assert "MENU_STRATEGY_SMC" in callbacks
    assert "MENU_STRATEGY_AI" in callbacks


def test_settings_message_shows_strategy_and_style():
    from app.telegram_bot.message_templates import format_settings_message
    from app.config import settings

    original_mode = settings.strategy_mode
    original_profile = settings.risk_profile
    try:
        settings.strategy_mode = "AI_ONLY"
        settings.risk_profile = "MEDIUM"
        msg = format_settings_message()

        assert "AI Only" in msg or "AI_ONLY" in msg
        assert "Daytrade" in msg
        assert "H1/H4" in msg
        assert "hours-days" in msg
    finally:
        settings.strategy_mode = original_mode
        settings.risk_profile = original_profile


def test_settings_message_shows_swing_for_low_profile():
    from app.telegram_bot.message_templates import format_settings_message
    from app.config import settings

    original_profile = settings.risk_profile
    try:
        settings.risk_profile = "LOW"
        msg = format_settings_message()

        assert "Swing" in msg
        assert "H4/D1" in msg
    finally:
        settings.risk_profile = original_profile


def test_strategy_smc_callback_sets_settings_and_persists():
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.telegram_bot.callbacks import menu_strategy_smc_cb
    from app.config import settings

    original_mode = settings.strategy_mode
    try:
        settings.strategy_mode = "AI_ONLY"
        query = MagicMock()
        query.answer = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        update.effective_chat.id = 123

        with patch("app.config.settings.telegram_allowed_chat_id", "123"), \
             patch("app.database.repositories.update_bot_settings") as mock_update:
            import asyncio
            asyncio.new_event_loop().run_until_complete(menu_strategy_smc_cb(update, MagicMock()))

        assert settings.strategy_mode == "SMC_AI"
        mock_update.assert_called_once_with({"strategy_mode": "SMC_AI"})
    finally:
        settings.strategy_mode = original_mode


def test_strategy_ai_callback_sets_settings_and_persists():
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.telegram_bot.callbacks import menu_strategy_ai_cb
    from app.config import settings

    original_mode = settings.strategy_mode
    try:
        settings.strategy_mode = "SMC_AI"
        query = MagicMock()
        query.answer = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        update.effective_chat.id = 123

        with patch("app.config.settings.telegram_allowed_chat_id", "123"), \
             patch("app.database.repositories.update_bot_settings") as mock_update:
            import asyncio
            asyncio.new_event_loop().run_until_complete(menu_strategy_ai_cb(update, MagicMock()))

        assert settings.strategy_mode == "AI_ONLY"
        mock_update.assert_called_once_with({"strategy_mode": "AI_ONLY"})
    finally:
        settings.strategy_mode = original_mode


def test_get_callback_handlers_includes_strategy_handlers():
    from app.telegram_bot.callbacks import get_callback_handlers

    patterns = []
    for handler in get_callback_handlers():
        if hasattr(handler, "pattern"):
            patterns.append(str(handler.pattern))

    assert any("MENU_STRATEGY_SMC" in p for p in patterns)
    assert any("MENU_STRATEGY_AI" in p for p in patterns)


def test_pending_and_close_pending_commands_registered():
    from app.telegram_bot.commands import get_command_handlers

    commands = set()
    for handler in get_command_handlers():
        commands.update(handler.commands)

    assert "pending" in commands
    assert "close_pending" in commands


def test_main_menu_has_pending_and_close_pending_buttons():
    from app.telegram_bot.message_templates import build_main_menu_keyboard

    callbacks = _keyboard_callback_data(build_main_menu_keyboard())

    assert "MENU_PENDING" in callbacks
    assert "MENU_CLOSE_PENDING" in callbacks


def test_callback_handlers_include_pending_handlers():
    from app.telegram_bot.callbacks import get_callback_handlers

    patterns = []
    for handler in get_callback_handlers():
        if hasattr(handler, "pattern"):
            patterns.append(str(handler.pattern))

    assert any("MENU_PENDING" in p for p in patterns)
    assert any("MENU_CLOSE_PENDING" in p for p in patterns)
    assert any("CLOSE_PENDING_CONFIRM" in p for p in patterns)


def test_format_pending_orders_empty():
    from app.telegram_bot.message_templates import format_pending_orders_message

    text = format_pending_orders_message([])

    assert "No pending orders" in text


def test_format_pending_orders_with_orders():
    from app.telegram_bot.message_templates import format_pending_orders_message

    orders = [
        {"ticket": 101, "symbol": "XAUUSD.c", "type": 2, "price_open": 1980.0, "sl": 1970.0, "tp": 2000.0, "volume": 0.01},
        {"ticket": 102, "symbol": "EURUSD.c", "type": 3, "price_open": 1.0850, "sl": 1.0900, "tp": 1.0750, "volume": 0.05},
    ]
    text = format_pending_orders_message(orders)

    assert "2 order(s)" in text
    assert "101" in text
    assert "102" in text


def test_signal_message_renders_smc_probability_block():
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, EntryPlan, EntryType, ExecutionPermission, MarketRegime, TimeframeBias
    from app.telegram_bot.message_templates import format_signal_message

    decision = AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.72,
        confidence_label=ConfidenceLabel.MEDIUM,
        market_regime=MarketRegime.TRENDING_UP,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BULLISH,
        entry_plan=EntryPlan(entry_type=EntryType.NONE),
        execution_permission=ExecutionPermission(ai_allows_execution=False, reason="manual"),
    )
    payload = {
        "current_price": {"bid": 1.1, "ask": 1.1002, "spread_points": 10},
        "smc_probability": {
            "final_score": 72,
            "setup_quality": "medium",
            "pre_ai_decision": "WAIT",
            "bias": "bullish",
            "timeframe_model": {"filter_timeframes": ["D1", "H4"], "execution_timeframes": ["H1"], "timeframe_fallback": None},
            "main_confluence": ["Profile filter and execution bias align bullish"],
            "weaknesses": ["CHoCH has no liquidity confirmation"],
            "risk_notes": ["manual confirmation required"],
            "entry_sl_tp_note": "manual confirmation required",
            "invalidation": "manual confirmation required",
            "adjustments": [],
        },
    }

    message = format_signal_message(decision, {"approved": False, "symbol": "EURUSD.m"}, "EURUSD.m", payload)

    assert "EURUSD.m" in message
    assert "Probability" in message
    assert "Score: 72%" in message
    assert "WAIT" in message
    assert "Manual confirmation required" in message
    assert "Multi-Timeframe Analysis" in message


@pytest.mark.asyncio
async def test_send_trade_signal_suppresses_no_trade_alert(monkeypatch):
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, MarketRegime, TimeframeBias
    from app.config import settings
    from app.telegram_bot import bot as bot_module

    decision = AIDecisionResponse(
        decision=Decision.BUY,
        confidence=0.8,
        confidence_label=ConfidenceLabel.HIGH,
        market_regime=MarketRegime.TRENDING_UP,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BULLISH,
    )
    original_token = settings.telegram_bot_token
    original_chat_id = settings.telegram_allowed_chat_id
    original_send_no_trade = settings.send_no_trade_alert
    original_application = bot_module._application
    try:
        settings.telegram_bot_token = "token"
        settings.telegram_allowed_chat_id = "123"
        settings.send_no_trade_alert = False
        bot_module._application = MagicMock(bot=object())
        monkeypatch.setattr("app.telegram_bot.bot.send_message", AsyncMock(return_value=True))

        sent = await bot_module.send_trade_signal(
            decision,
            {"symbol": "EURUSD.m", "approved": False},
            "decision-1",
            {"smc_probability": {"pre_ai_decision": "NO_TRADE", "final_score": 20}},
        )

        assert sent is False
    finally:
        settings.telegram_bot_token = original_token
        settings.telegram_allowed_chat_id = original_chat_id
        settings.send_no_trade_alert = original_send_no_trade
        bot_module._application = original_application
