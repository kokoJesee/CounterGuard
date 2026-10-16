"""Baseline behavior must match the frozen definitions without reading oracle data."""

from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from counterguard.baselines import (
    ScopeClause,
    ScopePredicate,
    count_predictions,
    decide_scope,
    make_baseline,
)
from counterguard.digests import digest_json_artifact
from counterguard.models import Guard
from counterguard.protocol import EXPECTED_TRAIN
from tests.benchmark_support import TRAIN_FILES, load_samples
from tests.unit.test_guard import guard_payload
from tests.unit.test_models import SHA_A


class OnlyInterface(Mapping):
    def __init__(self, value):
        self.value = value
        self.reads = []

    def __getitem__(self, key):
        self.reads.append(key)
        assert key == "interface_kind", f"Forbidden feature read: {key}"
        if self.value is None:
            raise KeyError(key)
        return self.value

    def __iter__(self):
        raise AssertionError("Cannot enumerate non-clause fields")

    def __len__(self):
        raise AssertionError("Cannot enumerate non-clause fields")


def baseline(method="b2_interface"):
    guard = Guard.model_validate(guard_payload())
    return make_baseline(guard, method, interface_kind="final_price", protocol_digest=SHA_A)


def test_b1_is_always_applicable_and_reads_no_features():
    features = OnlyInterface(None)
    scope = baseline("b1_always")
    assert decide_scope(scope, features).decision == "applicable"
    assert decide_scope(scope, features).trace == ()
    assert features.reads == []
    assert scope.artifact_digest == digest_json_artifact(scope)


@pytest.mark.parametrize(
    "interface, expected",
    [
        ("final_price", "applicable"),
        ("discount_amount", "inapplicable"),
        (None, "unknown"),
        (123, "unknown"),
        ("", "unknown"),
    ],
)
def test_b2_reads_only_interface_and_records_missing_values(interface, expected):
    features = OnlyInterface(interface)
    decision = decide_scope(baseline(), features)
    assert decision.decision == expected
    assert features.reads == ["interface_kind"]
    assert len(decision.trace) == 1
    assert decision.trace[0].field == "interface_kind"


def test_b2_does_not_change_with_version_or_oracle_values():
    scope = baseline()
    first = decide_scope(scope, {"interface_kind": "final_price", "contract_version": "v1"})
    altered = decide_scope(
        scope,
        {
            "interface_kind": "final_price",
            "contract_version": "v999",
            "module_group": "other",
            "guard_applicable": False,
            "guard_violation": True,
            "ast_features": ["anything"],
            "path": "bad",
            "sample_id": "buggy",
        },
    )
    assert first == altered


def test_baseline_schema_rejects_extra_conditions_or_training_labels():
    scope = baseline()
    with pytest.raises(ValidationError, match="only one interface_kind"):
        ScopePredicate.model_validate(
            {
                **scope.model_dump(),
                "clauses": (
                    ScopeClause(field="contract_version", op="eq", value="v1"),
                    *scope.clauses,
                ),
            }
        )
    with pytest.raises(ValidationError, match="fitted training metadata"):
        ScopePredicate.model_validate({**scope.model_dump(), "training_sample_ids": ("fixed",)})
    with pytest.raises(ValueError, match="match the verified Guard"):
        make_baseline(
            Guard.model_validate(guard_payload()),
            "b2_interface",
            interface_kind="discount_amount",
            protocol_digest=SHA_A,
        )


def test_frozen_training_confusion_counts():
    for method in EXPECTED_TRAIN:
        decisions = []
        for sample in load_samples(TRAIN_FILES):
            interface = (
                "final_price"
                if sample["features"]["contract_family"] == "membership_discount"
                else "query_parameter"
            )
            payload = guard_payload()
            payload["target_interface"]["interface_kind"] = interface
            scope = make_baseline(
                Guard.model_validate(payload),
                method,
                interface_kind=interface,
                protocol_digest=SHA_A,
            )
            result = decide_scope(scope, sample["features"])
            decisions.append((sample["labels"]["guard_applicable"], result.decision))
        assert count_predictions(decisions).model_dump() == EXPECTED_TRAIN[method]


@pytest.mark.parametrize("label", [True, False])
@pytest.mark.parametrize("decision", ["unknown", "skipped_unknown", "pass", "", None])
def test_binary_counts_refuse_unknown_and_execution_verdicts(label, decision):
    with pytest.raises(ValueError, match="known scope decisions"):
        count_predictions([(label, decision)])


@pytest.mark.parametrize("label", [0, 1, "false", None])
def test_confusion_counts_require_explicit_bool_labels(label):
    with pytest.raises(ValueError, match="bool labels"):
        count_predictions([(label, "applicable")])
