from app.config import settings
from app.logger import logger


def is_spread_acceptable(current_spread_points: int, max_spread_points: int = None) -> dict:
    if max_spread_points is None:
        max_spread_points = settings.max_spread_points

    acceptable = current_spread_points <= max_spread_points

    if acceptable:
        reason = f"Spread {current_spread_points} pts within limit {max_spread_points} pts"
    else:
        reason = f"Spread {current_spread_points} pts exceeds limit {max_spread_points} pts"

    logger.debug(f"Spread check: {reason}")

    return {
        "acceptable": acceptable,
        "current_spread": current_spread_points,
        "max_allowed": max_spread_points,
        "reason": reason,
    }
