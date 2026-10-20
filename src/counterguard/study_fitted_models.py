"""New research execution versions; C1's v1/v6 models remain closed."""

from typing import Literal

from pydantic import model_validator

from counterguard.baselines import ScopeDecision
from counterguard.models import ArtifactRef, Digest
from counterguard.study_models import (
    StudyAdmission,
    StudyAuthorization,
    StudyReplay,
    StudyReplayPlan,
    StudyReview,
)


class StudyFittedPlan(StudyReplayPlan):
    schema_version: Literal["study-replay-plan.v2"] = "study-replay-plan.v2"
    initial_fit_ref: ArtifactRef
    refined_fit_ref: ArtifactRef
    context_ref: ArtifactRef
    audit_ref: ArtifactRef


class StudyFittedReview(StudyReview):
    schema_version: Literal["study-review.v2"] = "study-review.v2"
    fit_review_digest: Digest
    initial_fit_digest: Digest
    refined_fit_digest: Digest
    context_digest: Digest
    audit_digest: Digest


class StudyFittedAdmission(StudyAdmission):
    schema_version: Literal["study-admission.v2"] = "study-admission.v2"
    fit_review_digest: Digest
    initial_fit_digest: Digest
    refined_fit_digest: Digest
    context_digest: Digest
    audit_digest: Digest
    scope_digest: Digest | None
    scope_decision: ScopeDecision

    @model_validator(mode="after")
    def consistent_decision(self):
        if self.scope_decision.decision != self.decision:
            raise ValueError("Research admission must preserve the actual predicate decision")
        return self


class StudyFittedAuthorization(StudyAuthorization):
    schema_version: Literal["docker-execution-authorization.v7"] = (
        "docker-execution-authorization.v7"
    )
    fit_review_digest: Digest
    initial_fit_digest: Digest
    refined_fit_digest: Digest
    context_digest: Digest
    audit_digest: Digest
    scope_digest: Digest | None


class StudyFittedReplay(StudyReplay):
    schema_version: Literal["study-replay.v2"] = "study-replay.v2"
    admission: StudyFittedAdmission | None
    fit_review_anchor: Digest
