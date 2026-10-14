"""Execute the selected discount contract without duplicating its oracle."""

import builtins
import importlib
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import pytest

DEFAULT_TARGET = "examples.discount.implementations.final_price_v1_fixed"
TARGET_MODULE = os.environ.get("EVIDENCEGUARD_TARGET", DEFAULT_TARGET)
TARGET_SYMBOL = os.environ.get("EVIDENCEGUARD_SYMBOL", "calculate_price")
DEFAULT_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "examples/discount/contracts/membership_discount_final_price_v1.json"
)
CONTRACT_PATH = Path(os.environ.get("EVIDENCEGUARD_CONTRACT", str(DEFAULT_CONTRACT)))
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


class PriceCalculator(Protocol):
    def __call__(self, amount: Decimal, is_member: bool) -> Decimal: ...


def load_target() -> PriceCalculator:
    module = importlib.import_module(TARGET_MODULE)
    return getattr(module, TARGET_SYMBOL)


@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case["case_id"]) for case in CONTRACT["cases"]],
)
def test_membership_discount_contract(case: dict[str, Any]) -> None:
    calculate_price = load_target()
    kwargs = {
        "amount": Decimal(case["args"]["amount"]),
        "is_member": case["args"]["is_member"],
    }
    if "raises" in case:
        with pytest.raises(getattr(builtins, case["raises"])):
            calculate_price(**kwargs)
    else:
        assert calculate_price(**kwargs) == Decimal(case["expected"])
