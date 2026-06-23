import math
import pytest

from app.risk.position_sizing import calculate_lot_size, validate_position_size


def _make_symbol_info(
    volume_min=0.01,
    volume_max=100.0,
    volume_step=0.01,
    point=0.01,
    trade_contract_size=100.0,
) -> dict:
    return {
        "volume_min": volume_min,
        "volume_max": volume_max,
        "volume_step": volume_step,
        "point": point,
        "trade_contract_size": trade_contract_size,
        "volume_limit": 100.0,
        "trade_tick_value": 1,
    }


class TestCalculateLotSize:

    def test_basic_calculation(self):
        sym = _make_symbol_info(point=0.01, trade_contract_size=100.0)
        result = calculate_lot_size(account_balance=10000.0, stop_loss_distance_points=100.0, symbol_info=sym)

        assert result["is_valid"] is True
        assert result["lot"] > 0
        assert result["risk_amount"] > 0

    def test_min_lot_enforcement(self):
        sym = _make_symbol_info(volume_min=0.10, volume_step=0.10)
        result = calculate_lot_size(account_balance=50000.0, stop_loss_distance_points=50.0, symbol_info=sym)

        # raw_lot = 250 / 50 = 5.0, above min 0.10, so should be valid
        assert result["is_valid"] is True
        assert result["lot"] >= sym["volume_min"]

    def test_max_lot_capping(self):
        sym = _make_symbol_info(volume_max=0.50, volume_step=0.01)
        result = calculate_lot_size(account_balance=1000000.0, stop_loss_distance_points=10.0, symbol_info=sym)

        assert result["is_valid"] is True
        assert result["lot"] <= sym["volume_max"]
        assert result["lot"] == 0.50

    def test_lot_step_rounding(self):
        sym = _make_symbol_info(volume_step=0.10, volume_min=0.10)
        result = calculate_lot_size(account_balance=15000.0, stop_loss_distance_points=100.0, symbol_info=sym)

        # raw_lot = 75 / 100 = 0.75, rounded to step 0.10 = 0.80
        assert result["is_valid"] is True
        remainder = result["lot"] % sym["volume_step"]
        assert math.isclose(remainder, 0.0, abs_tol=1e-6) or math.isclose(remainder, sym["volume_step"], abs_tol=1e-6)

    def test_over_risk_approved_with_min_lot(self):
        sym = _make_symbol_info(volume_min=0.05)
        # balance=100, SL=200pts -> raw_lot = 0.50/200 = 0.0025 < min 0.05
        # risk_at_min_lot = 0.05 * 200 = 10, risk% = 10/100 = 10% > 0.5%
        # should still execute with min_lot, no rejection
        result = calculate_lot_size(account_balance=100.0, stop_loss_distance_points=200.0, symbol_info=sym)

        assert result["is_valid"] is True
        assert result["lot"] == 0.05

    def test_zero_balance_raises_zero_division(self):
        sym = _make_symbol_info()
        with pytest.raises(ZeroDivisionError):
            calculate_lot_size(account_balance=0.0, stop_loss_distance_points=100.0, symbol_info=sym)

    def test_zero_sl_distance_returns_invalid(self):
        sym = _make_symbol_info()
        result = calculate_lot_size(account_balance=10000.0, stop_loss_distance_points=0.0, symbol_info=sym)

        assert result["is_valid"] is False


class TestValidatePositionSizing:

    def test_valid_lot_passes(self):
        sym = _make_symbol_info()
        result = validate_position_size(lot=0.05, symbol_info=sym)

        assert result["is_valid"] is True
        assert result["lot"] == 0.05
        assert len(result["errors"]) == 0

    def test_below_min_lot_fails(self):
        sym = _make_symbol_info(volume_min=0.10)
        result = validate_position_size(lot=0.01, symbol_info=sym)

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    def test_above_max_lot_fails(self):
        sym = _make_symbol_info(volume_max=1.00)
        result = validate_position_size(lot=5.00, symbol_info=sym)

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    def test_invalid_lot_step_warns(self):
        sym = _make_symbol_info(volume_step=0.10)
        result = validate_position_size(lot=0.15, symbol_info=sym)

        assert result["is_valid"] is True
        assert len(result["warnings"]) > 0

    def test_lot_step_ok_no_warnings(self):
        sym = _make_symbol_info(volume_step=0.10, volume_min=0.10)
        result = validate_position_size(lot=0.20, symbol_info=sym)

        assert result["is_valid"] is True
        assert len(result["warnings"]) == 0

    def test_valid_lot_with_small_step(self):
        sym = _make_symbol_info(volume_min=0.01, volume_step=0.01)
        result = validate_position_size(lot=0.15, symbol_info=sym)

        assert result["is_valid"] is True
        assert result["lot"] == 0.15


class TestConfidenceZoneScaling:

    def test_high_confidence_high_zone_uses_full_risk(self):
        from app.config import settings
        base = settings.risk_per_trade_percent
        sym = _make_symbol_info()
        result = calculate_lot_size(
            account_balance=10000.0,
            stop_loss_distance_points=100.0,
            symbol_info=sym,
            confidence=0.80,
            zone_quality="HIGH",
        )
        assert result["is_valid"] is True
        assert abs(result["effective_risk_percent"] - base) < 0.001

    def test_medium_confidence_medium_zone_scales_down(self):
        from app.config import settings
        base = settings.risk_per_trade_percent
        sym = _make_symbol_info()
        result = calculate_lot_size(
            account_balance=10000.0,
            stop_loss_distance_points=100.0,
            symbol_info=sym,
            confidence=0.60,
            zone_quality="MEDIUM",
        )
        assert result["is_valid"] is True
        assert abs(result["effective_risk_percent"] - base * 0.75 * 0.75) < 0.001

    def test_low_confidence_low_zone_scales_heavily(self):
        from app.config import settings
        base = settings.risk_per_trade_percent
        sym = _make_symbol_info()
        result = calculate_lot_size(
            account_balance=10000.0,
            stop_loss_distance_points=100.0,
            symbol_info=sym,
            confidence=0.45,
            zone_quality="LOW",
        )
        assert result["is_valid"] is True
        assert abs(result["effective_risk_percent"] - base * 0.50 * 0.50) < 0.001

    def test_market_order_zone_none_uses_neutral_factor(self):
        from app.config import settings
        base = settings.risk_per_trade_percent
        sym = _make_symbol_info()
        result = calculate_lot_size(
            account_balance=10000.0,
            stop_loss_distance_points=100.0,
            symbol_info=sym,
            confidence=0.80,
            zone_quality=None,
        )
        assert result["is_valid"] is True
        assert abs(result["effective_risk_percent"] - base * 1.0 * 0.75) < 0.001

    def test_no_confidence_no_zone_uses_base_risk(self):
        from app.config import settings
        base = settings.risk_per_trade_percent
        sym = _make_symbol_info()
        result = calculate_lot_size(
            account_balance=10000.0,
            stop_loss_distance_points=100.0,
            symbol_info=sym,
        )
        assert result["is_valid"] is True
        assert abs(result["effective_risk_percent"] - base) < 0.001
