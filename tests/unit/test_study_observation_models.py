"""External observation is a new closed purpose, not a boolean on fixture records."""

import json

import pytest
from pydantic import ValidationError

from counterguard.standalone_capture import ZERO, _seal
from counterguard.study_fitted_models import StudyFittedPlan
from counterguard.study_models import StudyReplayPlan
from counterguard.study_observation_models import StudyObservationPlan


def observation_plan():
    return _seal(
        StudyObservationPlan(
            source_ref="s.json",
            target_ref="t.json",
            map_ref="m.json",
            witness_ref="w.json",
            review_ref="external-review.json",
            artifact_digest=ZERO,
        )
    )


def test_observation_requires_distinct_version_and_purpose_and_original_parsers_reject_it():
    plan = observation_plan()
    assert StudyObservationPlan.model_validate_json(plan.model_dump_json()) == plan
    for model in (StudyReplayPlan, StudyFittedPlan):
        with pytest.raises(ValidationError):
            model.model_validate_json(plan.model_dump_json())
    for patch in (
        {"schema_version": "study-replay-plan.v1"},
        {"schema_version": "study-replay-plan.v2"},
        {"purpose": "tool_owned_research_fixture_only"},
        {"purpose": "production"},
        {"witness_ref": None},
    ):
        with pytest.raises(ValidationError):
            StudyObservationPlan.model_validate_json(
                json.dumps(plan.model_dump(mode="json") | patch)
            )


@pytest.mark.parametrize("method", ["b2_interface", "learned_initial", "learned_refined"])
def test_observation_cannot_request_learning_or_predictive_scope(method):
    raw = observation_plan().model_dump(mode="json") | {"method": method}
    with pytest.raises(ValidationError):
        StudyObservationPlan.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "field",
    [
        "fit_ref",
        "fit_review_digest",
        "training_repository",
        "guard_applicable",
        "contract_compliant",
        "execution_allowed",
        "approved",
        "environment",
    ],
)
def test_plan_cannot_inject_training_labels_approval_or_environment(field):
    raw = observation_plan().model_dump(mode="json") | {field: True}
    with pytest.raises(ValidationError):
        StudyObservationPlan.model_validate_json(json.dumps(raw))
