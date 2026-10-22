"""Independent four-method snapshot fixture types; old observation parsers stay closed."""

from typing import Literal

from pydantic import model_validator

from counterguard.baselines import ScopeDecision
from counterguard.models import Digest
from counterguard.project_config import RepositoryPath
from counterguard.snapshot_comparison_models import (
    SnapshotComparisonAdmission,
    SnapshotComparisonAuthorization,
    SnapshotComparisonPlan,
    SnapshotComparisonReplay,
    SnapshotComparisonReview,
)
from counterguard.snapshot_study_models import PURPOSE, _fields


class SnapshotStudyPlan(_fields(SnapshotComparisonPlan)):
    schema_version: Literal["snapshot-study-replay-plan.v1"] = "snapshot-study-replay-plan.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    lane: Literal["guard"] = "guard"
    initial_fit_ref: RepositoryPath
    refined_fit_ref: RepositoryPath
    context_ref: RepositoryPath
    audit_ref: RepositoryPath


class SnapshotStudyExecutionReview(_fields(SnapshotComparisonReview)):
    schema_version: Literal["snapshot-study-execution-review.v1"] = (
        "snapshot-study-execution-review.v1"
    )
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    fit_review_digest: Digest
    initial_fit_digest: Digest
    refined_fit_digest: Digest
    context_digest: Digest
    audit_digest: Digest


class SnapshotStudyAdmission(_fields(SnapshotComparisonAdmission)):
    schema_version: Literal["snapshot-study-admission.v1"] = "snapshot-study-admission.v1"
    lane: Literal["guard"] = "guard"
    fit_review_digest: Digest
    initial_fit_digest: Digest
    refined_fit_digest: Digest
    context_digest: Digest
    audit_digest: Digest
    scope_digest: Digest | None
    scope_decision: ScopeDecision

    @model_validator(mode="after")
    def consistent_decision(self):
        if self.decision != self.scope_decision.decision:
            raise ValueError("Snapshot study admission must preserve the three-way scope decision")
        return self


class SnapshotStudyAuthorization(_fields(SnapshotComparisonAuthorization)):
    schema_version: Literal["snapshot-study-execution-authorization.v1"] = (
        "snapshot-study-execution-authorization.v1"
    )
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    fit_review_digest: Digest
    initial_fit_digest: Digest
    refined_fit_digest: Digest
    context_digest: Digest
    audit_digest: Digest
    scope_digest: Digest | None


class SnapshotStudyReplay(_fields(SnapshotComparisonReplay)):
    schema_version: Literal["snapshot-study-replay.v1"] = "snapshot-study-replay.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    admission: SnapshotStudyAdmission
    fit_review_digest: Digest
