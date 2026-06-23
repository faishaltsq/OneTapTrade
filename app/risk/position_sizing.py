import math
from app.config import settings
from app.logger import logger


def _confidence_factor(confidence: float | None) -> float:
    if confidence is None:
        return 1.0
    if confidence > 0.70:
        return 1.0
    if confidence >= 0.50:
        return 0.75
    return 0.50


def _zone_factor(zone_quality: str | None) -> float:
    if zone_quality is None:
        return 0.75
    q = str(zone_quality).upper()
    if q == "HIGH":
        return 1.0
    if q == "MEDIUM":
        return 0.75
    return 0.50


def calculate_lot_size(
    account_balance: float,
    stop_loss_distance_points: float,
    symbol_info: dict,
    confidence: float | None = None,
    zone_quality: str | None = None,
) -> dict:
    base_risk_percent = settings.risk_per_trade_percent

    if confidence is None and zone_quality is None:
        effective_risk_percent = base_risk_percent
    else:
        effective_risk_percent = base_risk_percent * _confidence_factor(confidence) * _zone_factor(zone_quality)

    risk_amount = account_balance * (effective_risk_percent / 100.0)
    pip_value = symbol_info.get("trade_tick_value", 1)

    if stop_loss_distance_points <= 0:
        logger.warning("Stop loss distance must be > 0")
        return {
            "lot": 0.0,
            "risk_amount": risk_amount,
            "pip_value": pip_value,
            "is_valid": False,
            "reason": "Stop loss distance must be greater than 0",
        }

    raw_lot = risk_amount / (stop_loss_distance_points * pip_value)

    min_lot = symbol_info.get("volume_min", 0.01)
    max_lot = symbol_info.get("volume_max", 100.0)
    lot_step = symbol_info.get("volume_step", 0.01)

    if raw_lot < min_lot:
        lot = min_lot
        risk_at_min_lot = min_lot * stop_loss_distance_points * pip_value
        risk_percent = (risk_at_min_lot / account_balance) * 100
        logger.warning(
            f"Raw lot {raw_lot:.6f} below min {min_lot}, using min lot "
            f"(actual risk {risk_percent:.2f}% exceeds target {settings.risk_per_trade_percent}%)"
        )
    elif raw_lot > max_lot:
        lot = max_lot
    else:
        lot = raw_lot

    lot = _round_to_step(lot, lot_step)

    if lot > max_lot:
        lot = max_lot

    logger.debug(
        f"Position sizing: balance={account_balance}, SL_distance={stop_loss_distance_points}, "
        f"risk={risk_amount:.2f}, pip_value={pip_value}, lot={lot}"
    )

    return {
        "lot": lot,
        "risk_amount": risk_amount,
        "pip_value": pip_value,
        "is_valid": True,
        "reason": f"Calculated lot size: {lot}",
        "effective_risk_percent": round(effective_risk_percent, 4),
    }


def validate_position_size(lot: float, symbol_info: dict) -> dict:
    min_lot = symbol_info.get("volume_min", 0.01)
    max_lot = symbol_info.get("volume_max", 100.0)
    lot_step = symbol_info.get("volume_step", 0.01)

    errors = []
    warnings = []

    if lot < min_lot:
        errors.append(f"Lot {lot} is below minimum {min_lot}")
    if lot > max_lot:
        errors.append(f"Lot {lot} exceeds maximum {max_lot}")

    remainder = round(lot / lot_step, 10) if lot_step > 0 else 0
    if not remainder.is_integer():
        warnings.append(f"Lot {lot} is not a valid step of {lot_step}")

    is_valid = len(errors) == 0

    logger.debug(
        f"Position size validation: lot={lot}, min={min_lot}, max={max_lot}, "
        f"step={lot_step}, valid={is_valid}"
    )

    return {
        "is_valid": is_valid,
        "lot": lot,
        "min_lot": min_lot,
        "max_lot": max_lot,
        "lot_step": lot_step,
        "errors": errors,
        "warnings": warnings,
    }


def _round_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    decimals = max(0, -math.floor(math.log10(step)) + 1)
    steps = round(value / step)
    return round(steps * step, decimals)
