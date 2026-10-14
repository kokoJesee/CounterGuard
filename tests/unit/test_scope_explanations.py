"""Certificates expose real removal witnesses without changing learning digests."""

import random

import pytest
from pydantic import ValidationError

from evidenceguard.digests import canonical_json_bytes, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.scope import ScopeLearningResult, learn_scope
from evidenceguard.scope_explanations import (
    ScopeExplanation,
    explain_scope,
    verify_scope_explanation,
)
from tests.unit.test_scope import row


def examples():
    return (
        row(True),
        row(True),
        row(False, contract_version="v2"),
        row(False, interface_kind="other"),
        row(False, interface_kind="other"),
        # Rejected by both clauses, so it witnesses neither clause alone.
        row(False, contract_version="v2", interface_kind="other"),
    )


def test_each_clause_has_only_counterexamples_admitted_by_its_removal():
    rows = examples()
    learning = learn_scope(rows)
    before = canonical_json_bytes(learning)
    explanation = explain_scope(learning, rows)
    assert before == canonical_json_bytes(learning)
    assert explanation.artifact_digest == digest_json_artifact(explanation)
    assert explanation.learning_digest == learning.artifact_digest
    assert explanation.training_dataset_digest == learning.training_dataset_digest
    assert (explanation.positive_count, explanation.negative_count) == (2, 4)
    version, interface = explanation.clause_witnesses
    assert version.counterexample_features == (rows[2].features,)
    assert interface.counterexample_features == (rows[3].features,)
    assert "sample_id" not in explanation.model_dump_json()
    assert "created_at" not in explanation.model_dump_json()


def test_twenty_shuffles_produce_identical_certificate_bytes_and_digest():
    rows = list(examples())
    result = learn_scope(tuple(rows))
    expected = canonical_json_bytes(explain_scope(result, tuple(rows)))
    for seed in range(20):
        random.Random(seed).shuffle(rows)
        assert canonical_json_bytes(explain_scope(result, tuple(rows))) == expected


def test_single_clause_removal_means_empty_conjunction_and_all_negative_witnesses():
    rows = (row(True), row(True), row(False, contract_version="v2"))
    result = explain_scope(learn_scope(rows), rows)
    assert result.clause_witnesses[0].counterexample_features == (rows[2].features,)


def test_self_digest_training_multiset_and_rehashed_wrong_rule_are_rejected():
    rows = examples()
    result = learn_scope(rows)
    with pytest.raises(ArtifactIntegrityError, match="self digest"):
        explain_scope(result.model_copy(update={"artifact_digest": "sha256:" + "0" * 64}), rows)
    with pytest.raises(ArtifactIntegrityError, match="training multiset"):
        explain_scope(result, rows + (rows[2],))
    forged = result.model_copy(update={"clauses": result.clauses[:1]})
    forged = forged.model_copy(update={"artifact_digest": digest_json_artifact(forged)})
    with pytest.raises(ArtifactIntegrityError, match="training multiset"):
        explain_scope(forged, rows)


def test_legacy_learning_can_be_explained_without_reserializing_it_as_v2():
    rows = examples()
    payload = learn_scope(rows).model_dump()
    payload.update(
        schema_version="scope-learning.v1", candidate_count=payload.pop("combination_count")
    )
    payload.pop("predicate_count")
    payload["artifact_digest"] = digest_json_artifact(payload)
    legacy = ScopeLearningResult.model_validate(payload)
    explanation = explain_scope(legacy, rows)
    assert explanation.learning_digest == legacy.artifact_digest
    assert "predicate_count" not in legacy.model_dump_json()


def test_certificate_model_rejects_fake_positive_or_cross_clause_witnesses():
    explanation = explain_scope(learn_scope(examples()), examples())
    witnesses = explanation.clause_witnesses
    for features in (examples()[0].features, examples()[-1].features):
        forged = witnesses[0].model_copy(update={"counterexample_features": (features,)})
        with pytest.raises(ValidationError, match="removed clause"):
            ScopeExplanation.model_validate(
                {
                    **explanation.model_dump(),
                    "clause_witnesses": (forged, witnesses[1]),
                }
            )


def test_verifier_rejects_tampering_and_rehashed_unsupported_claims():
    rows = examples()
    learning = learn_scope(rows)
    explanation = explain_scope(learning, rows)
    verify_scope_explanation(explanation, learning, rows)
    forged = explanation.model_copy(update={"negative_count": 100})
    with pytest.raises(ArtifactIntegrityError, match="self digest"):
        verify_scope_explanation(forged, learning, rows)
    forged = forged.model_copy(update={"artifact_digest": digest_json_artifact(forged)})
    with pytest.raises(ArtifactIntegrityError, match="bound training evidence"):
        verify_scope_explanation(forged, learning, rows)
