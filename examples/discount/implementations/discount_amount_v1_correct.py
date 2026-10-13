"""A legal v1 implementation with a different interface meaning."""

from decimal import ROUND_HALF_UP, Decimal


def calculate_discount(amount: Decimal, is_member: bool) -> Decimal:
    if amount < 0:
        raise ValueError("amount must be non-negative")

    discount = amount * Decimal("0.20") if is_member else Decimal("0.00")
    return discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
