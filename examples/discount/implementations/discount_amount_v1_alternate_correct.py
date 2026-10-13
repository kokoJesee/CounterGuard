"""A holdout discount-amount implementation with a different code shape."""

from decimal import ROUND_HALF_UP, Decimal


def calculate_discount(amount: Decimal, is_member: bool) -> Decimal:
    if amount < 0:
        raise ValueError("amount must be non-negative")

    payable_factor = Decimal("0.80") if is_member else Decimal("1.00")
    return (amount - amount * payable_factor).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
