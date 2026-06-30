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


def test_tradingview_menu_hides_execution_controls():
    from app.config import settings
    from app.telegram_bot.message_templates import build_main_menu_keyboard

    original_source = settings.market_data_source
    try:
        settings.market_data_source = "TRADINGVIEW"
        callbacks = _keyboard_callback_data(build_main_menu_keyboard())
        assert "MENU_CLOSE_ALL" not in callbacks
        assert "MENU_MODE_SIGNAL" not in callbacks
        assert "MENU_MODE_SEMI" not in callbacks
        assert "MENU_MODE_AUTO" not in callbacks
        assert "MENU_POSITIONS" not in callbacks
        assert "MENU_RISK_TRADE_025" not in callbacks
        assert "MENU_RISK_TRADE_050" not in callbacks
        assert "MENU_RISK_TRADE_100" not in callbacks
    finally:
        settings.market_data_source = original_source


def test_tradingview_status_message_shows_signal_only_mode():
    from app.telegram_bot.message_templates import format_status_message

    message = format_status_message(
        {
            "mode": "SIGNAL_ONLY",
            "symbol": "OANDA:XAUUSD",
            "market_data_source": "TRADINGVIEW",
            "execution_enabled": False,
        }
    )

    assert "TRADINGVIEW" in message
    assert "Execution:</b> disabled" in message
    assert "Signal-only TradingView mode" in message


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


class FakeSendBot:
    def __init__(self):
        self.send_message = AsyncMock()
        self.send_photo = AsyncMock()


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


def _buy_decision():
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, MarketRegime, TimeframeBias

    return AIDecisionResponse(
        decision=Decision.BUY,
        confidence=0.72,
        confidence_label=ConfidenceLabel.HIGH,
        market_regime=MarketRegime.TRENDING_UP,
        higher_timeframe_bias=TimeframeBias.BULLISH,
        entry_timeframe_bias=TimeframeBias.BULLISH,
        main_reason="Momentum aligned.",
    )


@pytest.mark.asyncio
async def test_send_trade_signal_sends_private_photo_and_channel_broadcast_for_buy_setup(tmp_path):
    from app.config import settings
    from app.telegram_bot import bot as bot_module

    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"png")
    private_bot = FakeSendBot()
    channel_bot = FakeSendBot()
    fake_app = MagicMock(bot=private_bot)

    originals = {
        "application": bot_module._application,
        "telegram_bot_token": settings.telegram_bot_token,
        "telegram_allowed_chat_id": settings.telegram_allowed_chat_id,
        "signal_bot_token": settings.signal_bot_token,
        "signal_channel_id": settings.signal_channel_id,
        "market_data_source": settings.market_data_source,
    }
    try:
        bot_module._application = fake_app
        settings.telegram_bot_token = "private-token"
        settings.telegram_allowed_chat_id = "123"
        settings.signal_bot_token = "signal-token"
        settings.signal_channel_id = "@signals"
        settings.market_data_source = "TRADINGVIEW"

        with patch("app.telegram_bot.bot._capture_signal_screenshot", new=AsyncMock(return_value=chart_path)) as capture:
            with patch("app.telegram_bot.bot.Bot", return_value=channel_bot) as bot_cls:
                sent = await bot_module.send_trade_signal(
                    _buy_decision(),
                    {"approved": True, "symbol": "OANDA:XAUUSD"},
                    "decision-1",
                    {},
                )

        assert sent is True
        capture.assert_awaited_once_with("OANDA:XAUUSD")
        private_bot.send_photo.assert_awaited_once()
        private_kwargs = private_bot.send_photo.await_args.kwargs
        assert private_kwargs["chat_id"] == "123"
        assert "OANDA:XAUUSD" in private_kwargs["caption"]
        bot_cls.assert_called_once_with("signal-token")
        channel_bot.send_photo.assert_awaited_once()
        channel_kwargs = channel_bot.send_photo.await_args.kwargs
        assert channel_kwargs["chat_id"] == "@signals"
        assert "OANDA:XAUUSD" in channel_kwargs["caption"]
        private_bot.send_message.assert_not_awaited()
    finally:
        bot_module._application = originals["application"]
        settings.telegram_bot_token = originals["telegram_bot_token"]
        settings.telegram_allowed_chat_id = originals["telegram_allowed_chat_id"]
        settings.signal_bot_token = originals["signal_bot_token"]
        settings.signal_channel_id = originals["signal_channel_id"]
        settings.market_data_source = originals["market_data_source"]


@pytest.mark.asyncio
async def test_send_trade_signal_does_not_channel_broadcast_hold(tmp_path):
    from app.ai_engine.schemas import AIDecisionResponse, ConfidenceLabel, Decision, MarketRegime, TimeframeBias
    from app.config import settings
    from app.telegram_bot import bot as bot_module

    private_bot = FakeSendBot()
    fake_app = MagicMock(bot=private_bot)
    hold_decision = AIDecisionResponse(
        decision=Decision.HOLD,
        confidence=0.3,
        confidence_label=ConfidenceLabel.LOW,
        market_regime=MarketRegime.RANGING,
        higher_timeframe_bias=TimeframeBias.UNCLEAR,
        entry_timeframe_bias=TimeframeBias.UNCLEAR,
    )

    originals = {
        "application": bot_module._application,
        "telegram_bot_token": settings.telegram_bot_token,
        "telegram_allowed_chat_id": settings.telegram_allowed_chat_id,
        "signal_bot_token": settings.signal_bot_token,
        "signal_channel_id": settings.signal_channel_id,
        "market_data_source": settings.market_data_source,
    }
    try:
        bot_module._application = fake_app
        settings.telegram_bot_token = "private-token"
        settings.telegram_allowed_chat_id = "123"
        settings.signal_bot_token = "signal-token"
        settings.signal_channel_id = "@signals"
        settings.market_data_source = "TRADINGVIEW"

        with patch("app.telegram_bot.bot._capture_signal_screenshot", new=AsyncMock()) as capture:
            with patch("app.telegram_bot.bot.Bot") as bot_cls:
                sent = await bot_module.send_trade_signal(hold_decision, {"approved": True, "symbol": "OANDA:XAUUSD"}, "decision-2", {})

        assert sent is True
        capture.assert_not_awaited()
        bot_cls.assert_not_called()
        private_bot.send_message.assert_awaited_once()
        private_bot.send_photo.assert_not_awaited()
    finally:
        bot_module._application = originals["application"]
        settings.telegram_bot_token = originals["telegram_bot_token"]
        settings.telegram_allowed_chat_id = originals["telegram_allowed_chat_id"]
        settings.signal_bot_token = originals["signal_bot_token"]
        settings.signal_channel_id = originals["signal_channel_id"]
        settings.market_data_source = originals["market_data_source"]


@pytest.mark.asyncio
async def test_channel_broadcast_falls_back_to_text_when_photo_unreadable(tmp_path):
    from app.config import settings
    from app.telegram_bot import bot as bot_module

    channel_bot = FakeSendBot()
    missing_chart = tmp_path / "missing.png"

    original_token = settings.signal_bot_token
    original_channel = settings.signal_channel_id
    try:
        settings.signal_bot_token = "signal-token"
        settings.signal_channel_id = "@signals"

        with patch("app.telegram_bot.bot.Bot", return_value=channel_bot):
            sent = await bot_module._broadcast_signal_to_channel("<b>BUY OANDA:XAUUSD</b>", missing_chart)

        assert sent is True
        channel_bot.send_photo.assert_not_awaited()
        channel_bot.send_message.assert_awaited_once_with(
            chat_id="@signals",
            text="<b>BUY OANDA:XAUUSD</b>",
            parse_mode="HTML",
        )
    finally:
        settings.signal_bot_token = original_token
        settings.signal_channel_id = original_channel


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
    original_market_data_source = settings.market_data_source
    try:
        settings.telegram_allowed_chat_id = "123"
        settings.default_symbol = "XAUUSD.c"
        settings.market_data_source = "MT5"
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
        settings.market_data_source = original_market_data_source


@pytest.mark.asyncio
async def test_positions_button_shows_today_realized_pnl():
    from app.config import settings
    from app.telegram_bot.callbacks import menu_positions_callback

    original_chat_id = settings.telegram_allowed_chat_id
    original_market_data_source = settings.market_data_source
    try:
        settings.telegram_allowed_chat_id = "123"
        settings.market_data_source = "MT5"
        update = FakeCallbackUpdate()

        positions = [
            {"ticket": 1, "symbol": "XAUUSD.c", "type": 0, "volume": 0.01, "price_open": 2010, "sl": 2000, "tp": 2020, "profit": 2.0, "swap": 0.0},
        ]

        with patch("app.mt5_connector.connection.is_mt5_connected", return_value=True):
            with patch("app.mt5_connector.positions.get_open_positions", return_value=positions):
                with patch("app.mt5_connector.positions.get_today_realized_pnl", return_value=3.0):
                    await menu_positions_callback(update, MagicMock())

        text = update.callback_query.edit_message_text.await_args.args[0]
        assert "Today Realized P&amp;L: $+3.00" in text
        assert "Today Total P&amp;L: $+5.00" in text
    finally:
        settings.telegram_allowed_chat_id = original_chat_id
        settings.market_data_source = original_market_data_source


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
