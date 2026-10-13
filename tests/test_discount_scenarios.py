"""Integrity checks for the first scope-learning benchmark fixture."""

import importlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
SCENARIO_FILES = (
    PROJECT_ROOT / "benchmarks/train/discount_scope_samples.json",
    PROJECT_ROOT / "benchmarks/holdout/discount_scope_samples.json",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_samples() -> list[dict[str, Any]]:
    return [sample for path in SCENARIO_FILES for sample in load_json(path)]


def implementation_satisfies_contract(sample: dict[str, Any]) -> bool:
    contract = load_json(PROJECT_ROOT / sample["contract_ref"])
    module = importlib.import_module(sample["target"]["module"])
    target = getattr(module, sample["target"]["symbol"])

    for case in contract["cases"]:
        args = case["args"]
        amount = Decimal(args["amount"])
        is_member = args["is_member"]

        if case.get("raises") == "ValueError":
            try:
                target(amount, is_member)
            except ValueError:
                continue
            return False

        if target(amount, is_member) != Decimal(case["expected"]):
            return False

    return True


@pytest.mark.parametrize("sample", load_samples(), ids=lambda sample: sample["sample_id"])
def test_contract_compliance_labels_match_execution(sample: dict[str, Any]) -> None:
    assert implementation_satisfies_contract(sample) is sample["labels"]["contract_compliant"]


def test_guard_applicability_and_violation_are_separate_labels() -> None:
    samples = load_samples()

    for sample in samples:
        labels = sample["labels"]
        if labels["guard_applicable"]:
            assert labels["guard_violation"] is (not labels["contract_compliant"])
        else:
            assert labels["guard_violation"] is None


def test_scope_requires_contract_version_and_interface_kind() -> None:
    samples = load_samples()
    applicable = [sample for sample in samples if sample["labels"]["guard_applicable"]]
    inapplicable = [sample for sample in samples if not sample["labels"]["guard_applicable"]]

    assert applicable
    assert any(
        sample["features"]["contract_version"] == "v1"
        and sample["features"]["interface_kind"] != "final_price"
        for sample in inapplicable
    )
    assert any(
        sample["features"]["contract_version"] != "v1"
        and sample["features"]["interface_kind"] == "final_price"
        for sample in inapplicable
    )


def test_scope_features_exclude_identity_and_oracle_fields() -> None:
    prohibited = {"contract_id", "contract_ref", "module", "symbol", "oracle", "expected"}

    for sample in load_samples():
        assert prohibited.isdisjoint(sample["features"])


def test_training_and_holdout_sets_each_cover_both_scope_classes() -> None:
    for path in SCENARIO_FILES:
        labels = {sample["labels"]["guard_applicable"] for sample in load_json(path)}
        assert labels == {True, False}
