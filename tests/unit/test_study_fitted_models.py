"""New version and decision invariants, without provenance I/O or processes."""

import json

import pytest
from pydantic import ValidationError

from counterguard.baselines import ScopeClause, evaluate_clauses
from counterguard.standalone_capture import ZERO, _seal
from counterguard.study_fitted_models import StudyFittedAdmission, StudyFittedPlan
from counterguard.study_models import StudyAdmission, StudyReplayPlan


def plan():
    return _seal(
        StudyFittedPlan(
            source_ref="source.json",
            target_ref="target.json",
            map_ref="map.json",
            review_ref="review.json",
            method="learned_initial",
            initial_fit_ref="initial.json",
            refined_fit_ref="refined.json",
            context_ref="context.json",
            audit_ref="audit.json",
            artifact_digest=ZERO,
        )
    )


def test_new_plan_requires_all_fit_and_query_inputs_and_old_parser_rejects_it():
    current = plan()
    assert StudyFittedPlan.model_validate_json(current.model_dump_json()) == current
    with pytest.raises(ValidationError):
        StudyReplayPlan.model_validate_json(current.model_dump_json())
    for field in ("initial_fit_ref", "refined_fit_ref", "context_ref", "audit_ref"):
        raw = current.model_dump(mode="json")
        raw.pop(field)
        with pytest.raises(ValidationError):
            StudyFittedPlan.model_validate_json(json.dumps(raw))
    raw = current.model_dump(mode="json") | {"schema_version": "study-replay-plan.v1"}
    with pytest.raises(ValidationError):
        StudyFittedPlan.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "features,expected",
    [
        ({"contract_version": "v2", "interface_kind": "value_return"}, "applicable"),
        ({"contract_version": "v2", "interface_kind": "stdout_write"}, "inapplicable"),
        ({"contract_version": "v2"}, "unknown"),
    ],
)
def test_new_admission_must_match_three_way_predicate_trace(features, expected):
    clauses = (
        ScopeClause(field="contract_version", op="eq", value="v2"),
        ScopeClause(field="interface_kind", op="eq", value="value_return"),
    )
    decision = evaluate_clauses(clauses, features)
    assert decision.decision == expected
    payload = dict(
        decision=expected,
        reason_code="study_fitted_scope_evaluated",
        source_digest=ZERO,
        target_digest=ZERO,
        map_digest=ZERO,
        review_digest=ZERO,
        witness_digest=None,
        method="learned_refined",
        lane="guard",
        fit_review_digest=ZERO,
        initial_fit_digest=ZERO,
        refined_fit_digest=ZERO,
        context_digest=ZERO,
        audit_digest=ZERO,
        scope_digest=ZERO,
        scope_decision=decision,
        artifact_digest=ZERO,
    )
    value = StudyFittedAdmission(**payload)
    assert StudyFittedAdmission.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        StudyAdmission.model_validate_json(value.model_dump_json())
    payload["decision"] = "unknown" if expected != "unknown" else "inapplicable"
    with pytest.raises(ValidationError):
        StudyFittedAdmission(**payload)


def test_fit_trust_and_explicit_decisions_cannot_be_injected_into_plan():
    for key in (
        "fit_review_digest",
        "decision",
        "scope_digest",
        "execution_allowed",
        "guard_applicable",
    ):
        raw = plan().model_dump(mode="json") | {key: True}
        with pytest.raises(ValidationError):
            StudyFittedPlan.model_validate_json(json.dumps(raw))
