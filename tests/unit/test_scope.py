"""Independent cases verify deterministic search and the runtime type boundary."""

import json
import random
from pathlib import Path

import pytest
from pydantic import ValidationError

from evidenceguard.baselines import ScopeClause
from evidenceguard.digests import digest_json_artifact
from evidenceguard.errors import InsufficientScopeEvidence
from evidenceguard.features import FeatureRecord
from evidenceguard.predicates import FeatureVector
from evidenceguard.scope import ScopeLearningResult, TrainingExample, learn_scope


def vector(**changes):
    base = FeatureVector(
        contract_family="family",
        contract_version="v1",
        interface_kind="final_price",
        symbol_signature="signature",
        module_group="retail",
        ast_features=frozenset(),
    )
    return base.model_copy(update=changes) if changes else base


def row(applicable, **changes):
    return TrainingExample(features=vector(**changes), guard_applicable=applicable)


def test_initial_and_refined_rules_are_learned_without_ast_or_module_group_shortcuts():
    initial = (row(True), row(True), row(False, contract_version="v2"))
    refined = (*initial, row(False, interface_kind="discount_amount"))
    first = learn_scope(initial)
    second = learn_scope(refined)
    assert first.clauses == (ScopeClause(field="contract_version", op="eq", value="v1"),)
    assert second.clauses == (
        ScopeClause(field="contract_version", op="eq", value="v1"),
        ScopeClause(field="interface_kind", op="eq", value="final_price"),
    )
    assert second.training_confusion.model_dump() == {"tp": 2, "fp": 0, "tn": 2, "fn": 0}


def test_twenty_shuffles_produce_identical_rule_and_learning_digest():
    examples = [
        row(True),
        row(True),
        row(False, contract_version="v2"),
        row(False, interface_kind="other"),
    ]
    expected = learn_scope(tuple(examples)).model_dump_json()
    for seed in range(20):
        random.Random(seed).shuffle(examples)
        assert learn_scope(tuple(examples)).model_dump_json() == expected


def test_fixed_tie_break_prefers_declared_field_order_and_scalar_over_ast():
    examples = (
        row(True, ast_features=frozenset({"branch:none"})),
        row(True, ast_features=frozenset({"branch:none"})),
        row(False, contract_version="v2", interface_kind="other"),
    )
    result = learn_scope(examples)
    assert result.clauses[0].field == "contract_version"


def test_audited_module_group_can_be_discriminative_when_other_features_match():
    result = learn_scope(
        (row(True), row(True), row(False, module_group="another_architecture_group"))
    )
    assert result.clauses == (ScopeClause(field="module_group", op="eq", value="retail"),)


@pytest.mark.parametrize(
    "examples, reason",
    [
        ((row(True), row(False, contract_version="v2")), "too_few_positives"),
        ((row(True), row(True)), "no_counterexample"),
        ((row(True), row(True), row(False)), "conflicting_labels"),
        (
            (
                row(True),
                row(True),
                row(False, contract_version="v2"),
                row(False, interface_kind="other"),
                row(False, symbol_signature="other"),
                row(False, module_group="other"),
            ),
            "no_supported_rule",
        ),
    ],
)
def test_insufficient_or_conflicting_evidence_is_refused(examples, reason):
    with pytest.raises(InsufficientScopeEvidence) as error:
        learn_scope(examples)
    assert error.value.reason_code == reason


def test_learner_accepts_only_the_exact_feature_and_training_types():
    class LeakingVector(FeatureVector):
        oracle: str

    with pytest.raises(ValidationError, match="forbidden fields"):
        TrainingExample(
            features=LeakingVector(
                **vector().model_dump(exclude={"ast_features"}),
                ast_features=frozenset(),
                oracle="answer",
            ),
            guard_applicable=True,
        )
    with pytest.raises(ValidationError):
        TrainingExample.model_validate(
            {"features": vector(), "guard_applicable": True, "target": "buggy"}
        )
    with pytest.raises(ValidationError):
        TrainingExample.model_validate(
            {"features": {**vector().model_dump(), "sample_id": "buggy"}, "guard_applicable": True}
        )
    for value in (
        (vector(),),
        (FeatureRecord.model_construct(),),
        (row(True).model_dump(),),
        [row(True)],
    ):
        with pytest.raises(TypeError, match="exact TrainingExample"):
            learn_scope(value)
    forged = TrainingExample.model_construct(
        features=FeatureRecord.model_construct(), guard_applicable=True
    )
    with pytest.raises(TypeError, match="exact FeatureVector"):
        learn_scope((forged,))
    with pytest.raises(ValidationError):
        TrainingExample.model_validate({"features": vector(), "guard_applicable": 1})


def test_feature_record_json_and_provenance_are_rejected_as_learning_input():
    payload = {
        "schema_version": "feature-extraction.v2",
        "target": {"module": "buggy"},
        "features": vector().model_dump(mode="json"),
        "guard_applicable": True,
        "contract_ref": "oracle.json",
    }
    with pytest.raises(ValidationError):
        TrainingExample.model_validate_json(json.dumps(payload))


def test_actual_frozen_training_rows_have_stable_results_for_both_phases():
    root = Path(__file__).resolve().parents[2]
    split = json.loads((root / "benchmarks/splits/scope_v1.json").read_bytes())
    samples = {
        sample["sample_id"]: sample
        for path in (root / "benchmarks/train").glob("*_scope_samples.json")
        for sample in json.loads(path.read_bytes())
    }
    for guard_id, phases in split["phases"].items():
        for ids in (phases["initial"], phases["initial"] + phases["refinement_additions"]):
            examples = [
                TrainingExample(
                    features=FeatureVector.model_validate_json(
                        json.dumps(samples[sid]["features"])
                    ),
                    guard_applicable=samples[sid]["labels"]["guard_applicable"],
                )
                for sid in ids
            ]
            expected = learn_scope(tuple(examples)).model_dump_json()
            result = learn_scope(tuple(examples))
            counts = (8, 92) if "discount" in guard_id else (10, 175)
            assert (result.predicate_count, result.combination_count) == counts
            assert "candidate_count" not in result.model_dump(mode="json")
            for seed in range(20):
                random.Random(seed).shuffle(examples)
                assert learn_scope(tuple(examples)).model_dump_json() == expected


def test_legacy_combination_count_retains_its_original_digest_shape():
    result = learn_scope((row(True), row(True), row(False, contract_version="v2")))
    payload = result.model_dump(mode="json")
    payload["schema_version"] = "scope-learning.v1"
    payload["candidate_count"] = payload.pop("combination_count")
    payload.pop("predicate_count")
    payload["artifact_digest"] = digest_json_artifact(payload)
    loaded = ScopeLearningResult.model_validate_json(json.dumps(payload))
    assert loaded.model_dump(mode="json") == payload
    assert digest_json_artifact(loaded) == payload["artifact_digest"]
