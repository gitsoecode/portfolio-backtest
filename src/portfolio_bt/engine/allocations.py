from __future__ import annotations

from portfolio_bt.errors import ValidationError


def validate_weights(weights: dict[str, float], tolerance: float = 1e-6) -> dict[str, float]:
    """Validate and normalize user-supplied weights."""
    if not isinstance(weights, dict) or not weights:
        raise ValidationError("Weights must be a non-empty dictionary of ticker -> weight.")

    cleaned: dict[str, float] = {}
    for ticker, raw_weight in weights.items():
        symbol = str(ticker).upper().strip()
        if not symbol:
            raise ValidationError("Ticker symbols must be non-empty strings.")
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Weight for {symbol} must be numeric.") from exc
        if weight < 0:
            raise ValidationError(f"Negative weight is not allowed for {symbol}.")
        cleaned[symbol] = weight

    total = sum(cleaned.values())
    if abs(total - 1.0) > tolerance:
        raise ValidationError(
            f"Weights must sum to 1.0 within tolerance {tolerance}; received {total:.8f}."
        )
    return cleaned
