"""Training-only fixture contracts. None is an execution authorization."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.baselines import ScopeClause
from counterguard.models import ArtifactRef, Digest, FrozenModel, UtcDateTime
from counterguard.project_config import Identifier
from counterguard.scope import ScopeLearningResult
from counterguard.scope_explanations import ScopeExplanation
from counterguard.standalone_models import ReviewReason
from counterguard.study_models import canonical_ids

Phase = Literal["initial", "refined"]
Purpose = Literal["tool_owned_research_fixture_only"]


class StudySample(FrozenModel):
    schema_version: Literal["study-sample.v1"] = "study-sample.v1"
    purpose: Purpose = "tool_owned_research_fixture_only"
    sample_id: Identifier
    project_group: Identifier
    target_ref: ArtifactRef
    target_digest: Digest
    context_ref: ArtifactRef
    context_digest: Digest
    audit_ref: ArtifactRef
    audit_digest: Digest
    artifact_digest: Digest


class StudyBasisPin(FrozenModel):
    ref: ArtifactRef
    content_digest: Digest


class StudyLabelReview(FrozenModel):
    schema_version: Literal["study-label-review.v1"] = "study-label-review.v1"
    purpose: Purpose = "tool_owned_research_fixture_only"
    authority: Literal["trusted_local_operator_not_authenticated_identity"] = (
        "trusted_local_operator_not_authenticated_identity"
    )
    created_at: UtcDateTime
    operator: ReviewReason
    reason: ReviewReason
    sample_digest: Digest
    target_digest: Digest
    source_digest: Digest
    guard_digest: Digest
    guard_applicable: bool
    confirmed_legal_counterexample: bool
    own_contract_confirmation: Literal["trusted_manual_fixture_review"] = (
        "trusted_manual_fixture_review"
    )
    basis_pins: Annotated[tuple[StudyBasisPin, ...], Field(min_length=1, max_length=8)]
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        if not self.operator.strip() or not self.reason.strip():
            raise ValueError("Fixture labels require a nonblank reviewer and reason")
        if self.confirmed_legal_counterexample != (not self.guard_applicable):
            raise ValueError("Inapplicable fixture labels require independent legal confirmation")
        canonical_ids([p.ref for p in self.basis_pins])
        return self


class StudyTrainMember(FrozenModel):
    sample_id: Identifier
    project_group: Identifier
    repository_identity_digest: Digest
    target_key: Digest
    sample_ref: ArtifactRef
    sample_digest: Digest
    label_ref: ArtifactRef
    label_digest: Digest


class StudyHoldoutCommitment(FrozenModel):
    sample_id: Identifier
    project_group: Identifier
    repository_identity_digest: Digest
    target_key: Digest
    sample_digest: Digest
    label_digest: Digest


class StudySplit(FrozenModel):
    schema_version: Literal["study-split.v1"] = "study-split.v1"
    purpose: Purpose = "tool_owned_research_fixture_only"
    split_id: Identifier
    holdout_exposure: Literal["tool_owned_known"] = "tool_owned_known"
    initial: Annotated[tuple[StudyTrainMember, ...], Field(min_length=1, max_length=32)]
    refinement_additions: Annotated[tuple[StudyTrainMember, ...], Field(max_length=32)] = ()
    holdout: Annotated[tuple[StudyHoldoutCommitment, ...], Field(min_length=1, max_length=32)]
    artifact_digest: Digest

    @model_validator(mode="after")
    def separated(self):
        for rows in (self.initial, self.refinement_additions, self.holdout):
            if rows:
                canonical_ids([r.sample_id for r in rows])
        train = self.initial + self.refinement_additions
        all_rows = train + self.holdout
        if len(train) > 32:
            raise ValueError("Fixture training exceeds its 32-row budget")
        for field in ("sample_id", "target_key"):
            if len({getattr(r, field) for r in all_rows}) != len(all_rows):
                raise ValueError("Study splits cannot alias sample IDs or logical targets")
        for field in ("sample_ref", "label_ref"):
            if len({getattr(r, field) for r in train}) != len(train):
                raise ValueError("Training members must use distinct input references")
        for field in ("project_group", "repository_identity_digest"):
            if {getattr(r, field) for r in train} & {getattr(r, field) for r in self.holdout}:
                raise ValueError("Training and holdout groups/repositories must be disjoint")
        groups = {}
        for row in all_rows:
            previous = groups.setdefault(row.repository_identity_digest, row.project_group)
            if previous != row.project_group:
                raise ValueError("One repository cannot be relabelled as multiple project groups")
        return self


class StudyFitProtocol(FrozenModel):
    schema_version: Literal["study-fit-protocol.v1"] = "study-fit-protocol.v1"
    purpose: Purpose = "tool_owned_research_fixture_only"
    protocol_id: Identifier
    source_ref: ArtifactRef
    source_digest: Digest
    guard_digest: Digest
    source_project_group: Identifier
    split_ref: ArtifactRef
    split_digest: Digest
    learner: Literal["conjunction.v1"] = "conjunction.v1"
    extractor: Literal["ast-features.study.v1"] = "ast-features.study.v1"
    signature_algorithm: Literal["parameter-shape.study.v1"] = "parameter-shape.study.v1"
    vocabulary_digest: Digest
    max_predicates: Literal[32] = 32
    execution_allowed: Literal[False] = False
    artifact_digest: Digest


class StudyFitReview(FrozenModel):
    schema_version: Literal["study-fit-review.v1"] = "study-fit-review.v1"
    purpose: Purpose = "tool_owned_research_fixture_only"
    authority: Literal["trusted_local_operator_not_authenticated_identity"] = (
        "trusted_local_operator_not_authenticated_identity"
    )
    created_at: UtcDateTime
    operator: ReviewReason
    reason: ReviewReason
    action: Literal["approve", "withdraw"] = "approve"
    protocol_digest: Digest
    split_digest: Digest
    source_digest: Digest
    implementation_digests: dict[str, Digest]
    previous_ref: ArtifactRef | None = None
    previous_digest: Digest | None = None
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        if not self.operator.strip() or not self.reason.strip():
            raise ValueError("Fixture fit review requires a nonblank reviewer and reason")
        if (self.previous_ref is None) != (self.previous_digest is None):
            raise ValueError("Review predecessor requires reference and digest together")
        return self


class StudyFitInput(FrozenModel):
    member: StudyTrainMember
    target_digest: Digest
    context_digest: Digest
    audit_digest: Digest


class StudyLearnedScope(FrozenModel):
    schema_version: Literal["study-learned-scope.v1"] = "study-learned-scope.v1"
    purpose: Purpose = "tool_owned_research_fixture_only"
    protocol_digest: Digest
    split_digest: Digest
    source_digest: Digest
    guard_digest: Digest
    review_digest: Digest
    phase: Phase
    training_binding_digest: Digest
    learning_digest: Digest
    explanation_digest: Digest
    clauses: Annotated[tuple[ScopeClause, ...], Field(min_length=1, max_length=3)]
    execution_allowed: Literal[False] = False
    artifact_digest: Digest

    @model_validator(mode="after")
    def canonical(self):
        keys = [(c.field, c.op, c.value) for c in self.clauses]
        if keys != sorted(set(keys)):
            raise ValueError("Study scope clauses must be unique and canonical")
        return self


class StudyFit(FrozenModel):
    schema_version: Literal["study-fit.v1"] = "study-fit.v1"
    purpose: Purpose = "tool_owned_research_fixture_only"
    protocol_ref: ArtifactRef
    protocol_digest: Digest
    split_digest: Digest
    source_digest: Digest
    guard_digest: Digest
    review_ref: ArtifactRef
    review_digest: Digest
    phase: Phase
    inputs: Annotated[tuple[StudyFitInput, ...], Field(min_length=1, max_length=32)]
    training_binding_digest: Digest
    implementation_digests: dict[str, Digest]
    status: Literal["fitted", "refused"]
    refusal_code: Identifier | None
    learning: ScopeLearningResult | None
    explanation: ScopeExplanation | None
    scope: StudyLearnedScope | None
    execution_allowed: Literal[False] = False
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        canonical_ids([r.member.sample_id for r in self.inputs])
        if self.status == "refused":
            if self.refusal_code is None or any(
                v is not None for v in (self.learning, self.explanation, self.scope)
            ):
                raise ValueError("Refused fit requires a reason and cannot publish a rule")
        else:
            if self.refusal_code is not None or any(
                v is None for v in (self.learning, self.explanation, self.scope)
            ):
                raise ValueError("Fitted rule requires learning, explanation and research scope")
            scope = self.scope
            if (
                scope.clauses != self.learning.clauses
                or scope.learning_digest != self.learning.artifact_digest
                or scope.explanation_digest != self.explanation.artifact_digest
                or self.explanation.learning_digest != self.learning.artifact_digest
                or self.explanation.training_dataset_digest != self.learning.training_dataset_digest
                or any(
                    getattr(scope, key) != getattr(self, key)
                    for key in (
                        "protocol_digest",
                        "split_digest",
                        "source_digest",
                        "guard_digest",
                        "review_digest",
                        "phase",
                        "training_binding_digest",
                    )
                )
            ):
                raise ValueError("Research scope must bind the exact fit and learning facts")
        return self
