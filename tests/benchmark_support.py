"""Shared loaders and deterministic contract execution for benchmark integrity tests."""

import importlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[1]
TRAIN_FILES = tuple(sorted((PROJECT_ROOT / "benchmarks/train").glob("*_scope_samples.json")))
HOLDOUT_FILES = tuple(sorted((PROJECT_ROOT / "benchmarks/holdout").glob("*_scope_samples.json")))
SCENARIO_FILES = TRAIN_FILES + HOLDOUT_FILES


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_samples(files: tuple[Path, ...] = SCENARIO_FILES) -> list[dict[str, Any]]:
    return [sample for path in files for sample in load_json(path)]


def convert_value(value: Any, declared_type: str) -> Any:
    if declared_type == "decimal":
        return Decimal(value)
    if declared_type == "boolean":
        if not isinstance(value, bool):
            raise TypeError("boolean contract value must be a JSON boolean")
        return value
    if declared_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("integer contract value must be a JSON integer")
        return value
    if declared_type == "optional_string":
        if value is not None and not isinstance(value, str):
            raise TypeError("optional_string contract value must be a string or null")
        return value
    raise ValueError(f"unsupported contract type: {declared_type}")


def implementation_satisfies_contract(sample: dict[str, Any]) -> bool:
    contract = load_json(PROJECT_ROOT / sample["contract_ref"])
    module = importlib.import_module(sample["target"]["module"])
    target = getattr(module, sample["target"]["symbol"])

    for case in contract["cases"]:
        kwargs = {
            name: convert_value(value, contract["argument_types"][name])
            for name, value in case["args"].items()
        }
        expected_error = case.get("raises")

        try:
            actual = target(**kwargs)
        except Exception as error:  # noqa: BLE001 - execution outcome is benchmark data
            if expected_error == type(error).__name__:
                continue
            return False

        if expected_error is not None:
            return False

        expected = convert_value(case["expected"], contract["return_type"])
        if actual != expected:
            return False

    return True
