from app.logger import logger


def validate_trade_params(
    decision_response,
    symbol: str,
    current_bid: float,
    current_ask: float,
) -> dict:
    errors = []
    warnings = []

    decision = getattr(decision_response, "decision", None)

    entry_plan = getattr(decision_response, "entry_plan", None)
    entry_price = getattr(entry_plan, "preferred_entry_price", None) if entry_plan else None
    stop_loss = getattr(entry_plan, "stop_loss", None) if entry_plan else None
    take_profit_1 = getattr(entry_plan, "take_profit_1", None) if entry_plan else None

    if stop_loss is None:
        errors.append("Stop loss is not set")

    if take_profit_1 is None:
        errors.append("Take profit_1 is not set")

    if entry_price is not None and stop_loss is not None:
        if decision == "BUY":
            if stop_loss >= entry_price:
                errors.append(
                    f"BUY stop_loss ({stop_loss}) must be below entry_price ({entry_price})"
                )
            current_price = current_ask if current_ask else current_bid
            if stop_loss >= current_price:
                errors.append(
                    f"BUY stop_loss ({stop_loss}) must be below current price ({current_price})"
                )

        elif decision == "SELL":
            if stop_loss <= entry_price:
                errors.append(
                    f"SELL stop_loss ({stop_loss}) must be above entry_price ({entry_price})"
                )
            current_price = current_bid if current_bid else current_ask
            if stop_loss <= current_price:
                errors.append(
                    f"SELL stop_loss ({stop_loss}) must be above current price ({current_price})"
                )

    if entry_price is not None and take_profit_1 is not None:
        if decision == "BUY" and take_profit_1 <= entry_price:
            errors.append(
                f"BUY take_profit_1 ({take_profit_1}) must be above entry_price ({entry_price})"
            )
        elif decision == "SELL" and take_profit_1 >= entry_price:
            errors.append(
                f"SELL take_profit_1 ({take_profit_1}) must be below entry_price ({entry_price})"
            )

    valid = len(errors) == 0

    if not valid:
        logger.warning(
            f"Trade validation failed for {symbol} ({decision}): {errors}"
        )
    else:
        logger.debug(f"Trade validation passed for {symbol} ({decision})")

    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
    }
