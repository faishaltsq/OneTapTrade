from types import SimpleNamespace

import pytest
from fastapi import HTTPException


class FakeLoop:
    symbol = "OANDA:XAUUSD"
    status = SimpleNamespace(mode="SIGNAL_ONLY")

    def get_status(self):
        return {"mode": "SIGNAL_ONLY", "symbols": ["OANDA:XAUUSD"]}

    def set_paused(self, paused):
        self.paused = paused

    def set_mode(self, mode):
        self.status.mode = mode
        return None


def make_request(loop=None):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(trading_loop=loop or FakeLoop())))


@pytest.mark.asyncio
async def test_generate_signal_api_delegates_without_mt5(monkeypatch):
    from app.api import signals

    monkeypatch.setattr(
        "app.services.signal_service.generate_signal",
        lambda symbol: {
            "symbol": symbol,
            "ai_decision": SimpleNamespace(
                decision=SimpleNamespace(value="HOLD"),
                confidence=0.4,
                confidence_label=SimpleNamespace(value="LOW"),
                market_regime=SimpleNamespace(value="RANGING"),
                higher_timeframe_bias=SimpleNamespace(value="BULLISH"),
                entry_timeframe_bias=SimpleNamespace(value="BEARISH"),
                main_reason="hold",
                entry_plan=SimpleNamespace(
                    entry_type=SimpleNamespace(value="NONE"),
                    entry_area_low=None,
                    entry_area_high=None,
                    preferred_entry_price=None,
                    stop_loss=None,
                    take_profit_1=None,
                    take_profit_2=None,
                    risk_reward_to_tp1=None,
                    risk_reward_to_tp2=None,
                ),
                execution_permission=SimpleNamespace(ai_allows_execution=False, reason="hold"),
                risk_notes=SimpleNamespace(
                    main_risk="hold",
                    invalidation_condition=None,
                    conditions_to_avoid_trade=[],
                ),
                final_comment="hold",
            ),
            "risk_result": {"approved": False, "reason": "hold", "checks": {}},
            "decision_id": "decision-1",
        },
    )

    response = await signals.generate_signal(make_request())

    assert response["signal"]["decision"] == "HOLD"
    assert response["decision_id"] == "decision-1"


@pytest.mark.asyncio
async def test_status_reports_tradingview_source():
    from app.api.status import get_status

    response = await get_status(make_request())

    assert response["market_data_source"] == "TRADINGVIEW"
    assert response["execution_enabled"] is False
    assert "MT5" not in response.get("warning", "")


@pytest.mark.asyncio
async def test_close_all_disabled_in_tradingview_mode():
    from app.api.controls import close_all

    with pytest.raises(HTTPException) as exc:
        await close_all(make_request())

    assert exc.value.status_code == 400
    assert exc.value.detail == "Execution disabled in TradingView signal-only mode"


@pytest.mark.asyncio
async def test_mode_update_returns_status_mode():
    from app.api.controls import ModeUpdateRequest, update_mode

    response = await update_mode(make_request(), ModeUpdateRequest(mode="SIGNAL_ONLY"))

    assert response == {"status": "ok", "message": "Mode set to SIGNAL_ONLY", "mode": "SIGNAL_ONLY"}
