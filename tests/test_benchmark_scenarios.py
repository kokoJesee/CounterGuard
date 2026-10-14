"""Integrity checks for the two-category scope-learning benchmark."""

from collections import defaultdict
from typing import Any

import pytest

from tests.benchmark_support import (
    HOLDOUT_FILES,
    PROJECT_ROOT,
    SCENARIO_FILES,
    TRAIN_FILES,
    implementation_satisfies_contract,
    implementation_violates_minimal_guard,
    load_json,
    load_samples,
)

GUARD_SCOPES = {
    "grd_discount_member_rate_regression_v2": {
        "contract_family": "membership_discount",
        "contract_version": "v1",
        "interface_kind": "final_price",
    },
    "grd_query_limit_zero_regression_v2": {
        "contract_family": "input_limit",
        "contract_version": "v1",
        "interface_kind": "query_parameter",
    },
}


@pytest.mark.parametrize("sample", load_samples(), ids=lambda sample: sample["sample_id"])
def test_contract_compliance_labels_match_execution(sample: dict[str, Any]) -> None:
    assert implementation_satisfies_contract(sample) is sample["labels"]["contract_compliant"]


def test_guard_applicability_and_violation_are_separate_labels() -> None:
    for sample in load_samples():
        labels = sample["labels"]
        expected_scope = GUARD_SCOPES[labels["guard_id"]]
        expected_applicability = all(
            sample["features"][name] == value for name, value in expected_scope.items()
        )

        assert labels["guard_applicable"] is expected_applicability
        if labels["guard_applicable"]:
            assert labels["guard_violation"] is implementation_violates_minimal_guard(sample)
        else:
            assert labels["guard_violation"] is None


@pytest.mark.parametrize("files", [TRAIN_FILES, HOLDOUT_FILES], ids=["train", "holdout"])
def test_each_guard_needs_version_and_interface_kind(files: tuple[Any, ...]) -> None:
    samples_by_guard: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in load_samples(files):
        samples_by_guard[sample["labels"]["guard_id"]].append(sample)

    for samples in samples_by_guard.values():
        applicable = [sample for sample in samples if sample["labels"]["guard_applicable"]]
        inapplicable = [sample for sample in samples if not sample["labels"]["guard_applicable"]]
        version = applicable[0]["features"]["contract_version"]
        interface = applicable[0]["features"]["interface_kind"]

        assert any(
            sample["features"]["contract_version"] == version
            and sample["features"]["interface_kind"] != interface
            for sample in inapplicable
        )
        assert any(
            sample["features"]["contract_version"] != version
            and sample["features"]["interface_kind"] == interface
            for sample in inapplicable
        )


@pytest.mark.parametrize("files", [TRAIN_FILES, HOLDOUT_FILES], ids=["train", "holdout"])
def test_no_single_scope_predicate_perfectly_separates_a_guard(files: tuple[Any, ...]) -> None:
    scalar_features = (
        "contract_family",
        "contract_version",
        "interface_kind",
        "symbol_signature",
        "module_group",
    )
    samples_by_guard: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in load_samples(files):
        samples_by_guard[sample["labels"]["guard_id"]].append(sample)

    for samples in samples_by_guard.values():
        expected = [sample["labels"]["guard_applicable"] for sample in samples]

        for feature_name in scalar_features:
            values = {sample["features"][feature_name] for sample in samples}
            for value in values:
                predicted = [sample["features"][feature_name] == value for sample in samples]
                assert predicted != expected

        ast_features = {
            feature for sample in samples for feature in sample["features"]["ast_features"]
        }
        for feature in ast_features:
            predicted = [feature in sample["features"]["ast_features"] for sample in samples]
            assert predicted != expected


def test_scope_features_exclude_identity_and_oracle_fields() -> None:
    prohibited = {"contract_id", "contract_ref", "module", "symbol", "oracle", "expected"}

    for sample in load_samples():
        assert prohibited.isdisjoint(sample["features"])


def test_scope_features_follow_a_controlled_schema() -> None:
    expected_keys = {
        "ast_features",
        "contract_family",
        "contract_version",
        "interface_kind",
        "module_group",
        "symbol_signature",
    }
    allowed_ast_features = {
        "branch:is_member",
        "branch:none",
        "decimal:multiply",
        "decimal:subtract",
        "int:parse",
        "regex:ascii_digits",
        "range:check",
        "round:half_up",
        "str:isascii",
        "str:isdecimal",
    }

    for sample in load_samples():
        assert sample["features"].keys() == expected_keys
        assert set(sample["features"]["ast_features"]) <= allowed_ast_features


def test_scope_metadata_matches_the_declared_contract() -> None:
    contract_feature_names = {
        "contract_family",
        "contract_version",
        "interface_kind",
        "symbol_signature",
    }

    for sample in load_samples():
        contract = load_json(PROJECT_ROOT / sample["contract_ref"])
        for feature_name in contract_feature_names:
            assert sample["features"][feature_name] == contract[feature_name]
        assert sample["target"]["symbol"] == contract["target_symbol"]


def test_benchmark_size_split_and_identifiers() -> None:
    samples = load_samples()
    train_samples = load_samples(TRAIN_FILES)
    holdout_samples = load_samples(HOLDOUT_FILES)
    sample_ids = [sample["sample_id"] for sample in samples]

    assert 12 <= len(samples) <= 16
    assert 4 <= len(holdout_samples) <= 6
    assert len(samples) == len(train_samples) + len(holdout_samples)
    assert len(sample_ids) == len(set(sample_ids))
    assert {sample["features"]["contract_family"] for sample in samples} == {
        "input_limit",
        "membership_discount",
    }


def test_applicability_is_independent_of_own_contract_compliance() -> None:
    combinations = {
        (
            sample["labels"]["guard_applicable"],
            sample["labels"]["contract_compliant"],
            sample["labels"]["guard_violation"],
        )
        for sample in load_samples()
    }

    assert combinations == {
        (True, True, False),
        (True, False, True),
        (False, True, None),
        (False, False, None),
    }


def test_each_guard_has_both_scope_classes_in_train_and_holdout() -> None:
    for files in (TRAIN_FILES, HOLDOUT_FILES):
        labels_by_guard: dict[str, set[bool]] = defaultdict(set)
        for sample in load_samples(files):
            labels = sample["labels"]
            labels_by_guard[labels["guard_id"]].add(labels["guard_applicable"])

        assert labels_by_guard.keys() == GUARD_SCOPES.keys()
        assert all(labels == {True, False} for labels in labels_by_guard.values())


def test_each_holdout_sample_has_a_code_shape_absent_from_training() -> None:
    train_features_by_guard: dict[str, set[str]] = defaultdict(set)
    for sample in load_samples(TRAIN_FILES):
        train_features_by_guard[sample["labels"]["guard_id"]].update(
            sample["features"]["ast_features"]
        )

    for sample in load_samples(HOLDOUT_FILES):
        guard_id = sample["labels"]["guard_id"]
        holdout_features = set(sample["features"]["ast_features"])
        assert holdout_features - train_features_by_guard[guard_id]


def test_all_scenario_files_are_discovered() -> None:
    assert len(SCENARIO_FILES) == 4
