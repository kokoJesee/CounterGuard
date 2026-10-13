"""Reusable v1 contract test whose target can be swapped without editing the test."""

import importlib
import os
from decimal import Decimal
from typing import Protocol

import pytest

DEFAULT_TARGET = "examples.discount.implementations.final_price_v1_fixed"
TARGET_MODULE = os.environ.get("EVIDENCEGUARD_TARGET", DEFAULT_TARGET)
TARGET_SYMBOL = os.environ.get("EVIDENCEGUARD_SYMBOL", "calculate_price")


class PriceCalculator(Protocol):
    def __call__(self, amount: Decimal, is_member: bool) -> Decimal: ...


def load_target() -> PriceCalculator:
    module = importlib.import_module(TARGET_MODULE)
    return getattr(module, TARGET_SYMBOL)


@pytest.mark.parametrize(
    ("amount", "is_member", "expected"),
    [
        ("100.00", True, "80.00"),
        ("100.00", False, "100.00"),
        ("12.55", True, "10.04"),
    ],
)
def test_membership_discount_final_price_v1(
    amount: str,
    is_member: bool,
    expected: str,
) -> None:
    calculate_price = load_target()

    actual = calculate_price(Decimal(amount), is_member)

    assert actual == Decimal(expected)


def test_membership_discount_rejects_negative_amounts() -> None:
    calculate_price = load_target()

    with pytest.raises(ValueError, match="non-negative"):
        calculate_price(Decimal("-0.01"), True)
