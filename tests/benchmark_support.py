"""Shared loaders and deterministic contract execution for benchmark integrity tests."""

import importlib
import json
from pathlib import Path
from typing import Any

from evidenceguard.contracts import convert_contract_value, resolve_exception

PROJECT_ROOT = Path(__file__).parents[1]
TRAIN_FILES = tuple(sorted((PROJECT_ROOT / "benchmarks/train").glob("*_scope_samples.json")))
HOLDOUT_FILES = tuple(sorted((PROJECT_ROOT / "benchmarks/holdout").glob("*_scope_samples.json")))
SCENARIO_FILES = TRAIN_FILES + HOLDOUT_FILES


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_samples(files: tuple[Path, ...] = SCENARIO_FILES) -> list[dict[str, Any]]:
    return [sample for path in files for sample in load_json(path)]


def convert_value(value: Any, declared_type: str) -> Any:
    return convert_contract_value(value, declared_type)


def implementation_satisfies_contract(sample: dict[str, Any]) -> bool:
    contract = load_json(PROJECT_ROOT / sample["contract_ref"])
    return _satisfies_cases(sample, contract)


def implementation_violates_minimal_guard(sample: dict[str, Any]) -> bool:
    guards = {
        "grd_discount_member_rate_regression": (
            "examples/discount/contracts/membership_discount_final_price_v1.json",
            {"member-price", "member-rounding"},
        ),
        "grd_query_limit_zero_regression": (
            "examples/validation/contracts/input_limit_query_v1.json",
            {"below-minimum"},
        ),
    }
    contract_ref, case_ids = guards[sample["labels"]["guard_id"]]
    contract = load_json(PROJECT_ROOT / contract_ref)
    contract["cases"] = [case for case in contract["cases"] if case["case_id"] in case_ids]
    assert len(contract["cases"]) == len(case_ids)
    return not _satisfies_cases(sample, contract)


def _satisfies_cases(sample: dict[str, Any], contract: dict[str, Any]) -> bool:
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
            if expected_error is not None and isinstance(error, resolve_exception(expected_error)):
                continue
            return False

        if expected_error is not None:
            return False

        expected = convert_value(case["expected"], contract["return_type"])
        if actual != expected:
            return False

    return True
