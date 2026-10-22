"""Closed N-by-four fixture evaluation contracts, separate from any formal holdout."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.evaluation_metrics import Prediction
from counterguard.models import Digest, FrozenModel, UtcDateTime
from counterguard.project_config import Identifier, RepositoryPath
from counterguard.protocol import SampleLabels
from counterguard.snapshot_study_models import PURPOSE
from counterguard.standalone_models import ReviewReason
from counterguard.study_fit_models import StudyBasisPin
from counterguard.study_metrics import StudyMetricSummary
from counterguard.study_models import Method

METHODS = ("b1_always", "b2_interface", "learned_initial", "learned_refined")


class SnapshotStudyQueryLabel(FrozenModel):
    schema_version: Literal["snapshot-study-query-label.v1"] = "snapshot-study-query-label.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    authority: Literal["trusted_manual_fixture_labels_not_semantic_proof"] = (
        "trusted_manual_fixture_labels_not_semantic_proof"
    )
    created_at: UtcDateTime
    operator: ReviewReason
    reason: ReviewReason
    sample_id: Identifier
    project_group: Identifier
    guard_digest: Digest
    target_digest: Digest
    labels: SampleLabels
    basis_pins: Annotated[tuple[StudyBasisPin, ...], Field(min_length=1, max_length=8)]
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        refs = tuple(p.ref for p in self.basis_pins)
        if refs != tuple(sorted(set(refs))) or not self.operator.strip() or not self.reason.strip():
            raise ValueError("Fixture query labels require nonblank review and canonical basis")
        return self


class SnapshotStudyEvaluationMember(FrozenModel):
    row_id: Identifier
    sample_id: Identifier
    project_group: Identifier
    guard_digest: Digest
    target_key: Digest
    plan_ref: RepositoryPath
    label_ref: RepositoryPath
    label_digest: Digest


class SnapshotStudyEvaluationPlan(FrozenModel):
    schema_version: Literal["snapshot-study-evaluation-plan.v1"] = (
        "snapshot-study-evaluation-plan.v1"
    )
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    evaluation_id: Identifier
    dataset_role: Literal["known_tool_owned_fixture_queries_not_formal_holdout"] = (
        "known_tool_owned_fixture_queries_not_formal_holdout"
    )
    methods: tuple[
        Literal["b1_always"],
        Literal["b2_interface"],
        Literal["learned_initial"],
        Literal["learned_refined"],
    ] = METHODS
    members: Annotated[
        tuple[SnapshotStudyEvaluationMember, ...], Field(min_length=1, max_length=32)
    ]
    execution_allowed: Literal[False] = False
    artifact_digest: Digest

    @model_validator(mode="after")
    def canonical(self):
        ids = tuple(row.row_id for row in self.members)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("Evaluation rows must be unique and sorted")
        logical = [(r.guard_digest, r.target_key) for r in self.members]
        labels = [(r.guard_digest, r.sample_id) for r in self.members]
        if len(set(logical)) != len(logical) or len(set(labels)) != len(labels):
            raise ValueError("Renaming a row cannot duplicate a Guard/target or Guard/sample pair")
        return self


class SnapshotStudyEvaluationPin(FrozenModel):
    row_id: Identifier
    plan_digest: Digest
    label_digest: Digest
    guard_digest: Digest
    target_digest: Digest
    execution_review_digest: Digest
    fit_review_digest: Digest
    initial_fit_digest: Digest
    refined_fit_digest: Digest


class SnapshotStudyEvaluationReview(FrozenModel):
    schema_version: Literal["snapshot-study-evaluation-review.v1"] = (
        "snapshot-study-evaluation-review.v1"
    )
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    authority: Literal["trusted_local_operator_not_authenticated_identity"] = (
        "trusted_local_operator_not_authenticated_identity"
    )
    created_at: UtcDateTime
    operator: ReviewReason
    reason: ReviewReason
    action: Literal["approve", "withdraw"] = "approve"
    plan_digest: Digest
    members: tuple[SnapshotStudyEvaluationPin, ...]
    implementation_digests: dict[str, Digest]
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        ids = tuple(row.row_id for row in self.members)
        if not ids or ids != tuple(sorted(set(ids))):
            raise ValueError("Evaluation review rows must be canonical and nonempty")
        if not self.operator.strip() or not self.reason.strip():
            raise ValueError("Evaluation review requires a nonblank operator and reason")
        return self


class SnapshotStudyEvaluationSlot(FrozenModel):
    row_id: Identifier
    method: Method
    replay_ref: RepositoryPath
    replay_digest: Digest
    prediction: Prediction


class SnapshotStudySourceBug(FrozenModel):
    role: Literal["unscoped_guard_self_check_not_learned_scope_replay"] = (
        "unscoped_guard_self_check_not_learned_scope_replay"
    )
    guard_id: Identifier
    guard_digest: Digest
    buggy_run_digest: Digest
    fixed_run_digest: Digest
    detected: bool
    fixed_passed: bool


class SnapshotStudyEvaluation(FrozenModel):
    schema_version: Literal["snapshot-study-evaluation.v1"] = "snapshot-study-evaluation.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    research_support: Literal["fixture_engineering_only_not_scientific_evidence"] = (
        "fixture_engineering_only_not_scientific_evidence"
    )
    created_at: UtcDateTime
    plan_ref: RepositoryPath
    plan_digest: Digest
    review_ref: RepositoryPath
    review_digest: Digest
    slots: Annotated[tuple[SnapshotStudyEvaluationSlot, ...], Field(min_length=4, max_length=128)]
    source_bugs: tuple[SnapshotStudySourceBug, ...]
    metrics: StudyMetricSummary
    integrity: Literal["complete"] = "complete"
    execution_failures: Annotated[int, Field(ge=0, le=128)]
    implementation_digests: dict[str, Digest]
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        keys = [(s.row_id, METHODS.index(s.method)) for s in self.slots]
        if keys != sorted(set(keys)):
            raise ValueError("Evaluation slots must be unique and canonical")
        if any(slot.method != slot.prediction.method for slot in self.slots):
            raise ValueError("A slot and its prediction cannot use different methods")
        return self


class SnapshotStudyEvaluationFailure(FrozenModel):
    schema_version: Literal["snapshot-study-evaluation-failure.v1"] = (
        "snapshot-study-evaluation-failure.v1"
    )
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    complete: Literal[False] = False
    plan_digest: Digest
    review_digest: Digest
    reason_code: Literal["snapshot_evaluation_incomplete_inputs_or_execution"] = (
        "snapshot_evaluation_incomplete_inputs_or_execution"
    )
    completed_slots: Annotated[tuple[SnapshotStudyEvaluationSlot, ...], Field(max_length=128)]
    artifact_digest: Digest
