from app.config import settings
from app.logger import logger


def is_drawdown_acceptable(daily_drawdown_percent: float) -> dict:
    max_allowed = settings.max_daily_drawdown_percent
    ratio = daily_drawdown_percent / max_allowed if max_allowed > 0 else 0.0
    remaining = max_allowed - daily_drawdown_percent

    if ratio < 0.50:
        severity = "OK"
    elif ratio < 0.90:
        severity = "WARNING"
    else:
        severity = "CRITICAL"

    acceptable = daily_drawdown_percent < max_allowed

    logger.debug(
        f"Drawdown check: {daily_drawdown_percent:.2f}% / "
        f"{max_allowed:.2f}% -> severity={severity}, acceptable={acceptable}"
    )

    return {
        "acceptable": acceptable,
        "current_drawdown_percent": daily_drawdown_percent,
        "max_allowed": max_allowed,
        "remaining": remaining,
        "severity": severity,
    }
