"""Reusable v1 query-limit test whose target can be swapped without editing the test."""

import importlib
import os
from typing import Protocol

import pytest

DEFAULT_TARGET = "examples.validation.implementations.query_limit_v1_fixed"
TARGET_MODULE = os.environ.get("EVIDENCEGUARD_TARGET", DEFAULT_TARGET)
TARGET_SYMBOL = os.environ.get("EVIDENCEGUARD_SYMBOL", "parse_limit")


class LimitParser(Protocol):
    def __call__(self, raw: str | None) -> int: ...


def load_target() -> LimitParser:
    module = importlib.import_module(TARGET_MODULE)
    return getattr(module, TARGET_SYMBOL)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 20), ("1", 1), ("01", 1), ("100", 100)],
)
def test_query_limit_v1_accepts_valid_values(raw: str | None, expected: int) -> None:
    assert load_target()(raw) == expected


@pytest.mark.parametrize("raw", ["0", "101", "ten", "", "+1", " 1 ", "1_0", "１２", "-1"])
def test_query_limit_v1_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        load_target()(raw)
