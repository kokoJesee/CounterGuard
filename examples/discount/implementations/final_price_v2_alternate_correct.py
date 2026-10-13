"""A holdout implementation that satisfies the v2 contract."""

from decimal import ROUND_HALF_UP, Decimal


def calculate_price(amount: Decimal, is_member: bool) -> Decimal:
    if amount < 0:
        raise ValueError("amount must be non-negative")

    discount = Decimal("0.10") if is_member else Decimal("0.00")
    return (amount * (Decimal("1.00") - discount)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
