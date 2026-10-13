"""Reference implementation of the v2 final-price contract."""

from decimal import ROUND_HALF_UP, Decimal


def calculate_price(amount: Decimal, is_member: bool) -> Decimal:
    if amount < 0:
        raise ValueError("amount must be non-negative")

    factor = Decimal("0.90") if is_member else Decimal("1.00")
    return (amount * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
