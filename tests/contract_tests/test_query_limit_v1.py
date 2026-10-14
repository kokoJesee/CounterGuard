"""Execute the selected query-limit contract without duplicating its oracle."""

import builtins
import importlib
import json
import os
from pathlib import Path
from typing import Any, Protocol

import pytest

DEFAULT_TARGET = "examples.validation.implementations.query_limit_v1_fixed"
TARGET_MODULE = os.environ.get("EVIDENCEGUARD_TARGET", DEFAULT_TARGET)
TARGET_SYMBOL = os.environ.get("EVIDENCEGUARD_SYMBOL", "parse_limit")
DEFAULT_CONTRACT = (
    Path(__file__).resolve().parents[2] / "examples/validation/contracts/input_limit_query_v1.json"
)
CONTRACT_PATH = Path(os.environ.get("EVIDENCEGUARD_CONTRACT", str(DEFAULT_CONTRACT)))
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


class LimitParser(Protocol):
    def __call__(self, raw: str | None) -> int: ...


def load_target() -> LimitParser:
    module = importlib.import_module(TARGET_MODULE)
    return getattr(module, TARGET_SYMBOL)


@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case["case_id"]) for case in CONTRACT["cases"]],
)
def test_query_limit_contract(case: dict[str, Any]) -> None:
    parse_limit = load_target()
    if "raises" in case:
        with pytest.raises(getattr(builtins, case["raises"])):
            parse_limit(**case["args"])
    else:
        assert parse_limit(**case["args"]) == case["expected"]
