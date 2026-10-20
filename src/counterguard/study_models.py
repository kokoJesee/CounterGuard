"""Closed research-only persistence; none of these records authorize production replay."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.models import ArtifactRef, Digest, FrozenModel, RunRecord, RunRole, UtcDateTime
from counterguard.project_config import Identifier, Module, Symbol
from counterguard.runner_catalog import RunnerReview
from counterguard.runners.docker import ExecutionInputPin
from counterguard.standalone_contracts import CommitId
from counterguard.standalone_models import CaptureTimeout, ReviewReason

CaseId = Annotated[str, Field(pattern=r"^case_[a-f0-9]{24}$", strict=True)]
Method = Literal["b1_always", "b2_interface", "learned_initial", "learned_refined"]
Lane = Literal["guard", "witness"]
FixtureInterface = Literal["value_return", "stdout_write"]


def canonical_ids(values):
    if not values or list(values) != sorted(set(values)):
        raise ValueError("Study members must be nonempty, unique and sorted")


class StudySource(FrozenModel):
    schema_version: Literal["study-source.v1"] = "study-source.v1"
    source_id: Identifier
    repository_identity_digest: Digest
    guard_ref: ArtifactRef
    guard_digest: Digest
    evidence_digest: Digest
    binding_digest: Digest
    buggy_commit: CommitId
    fixed_commit: CommitId
    assertion_head: CommitId
    contract_ref: ArtifactRef
    contract_digest: Digest
    case_ids: Annotated[tuple[CaseId, ...], Field(min_length=1, max_length=256)]
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        canonical_ids(self.case_ids)
        return self


class StudyTarget(FrozenModel):
    schema_version: Literal["study-target.v1"] = "study-target.v1"
    target_id: Identifier
    repository_identity_digest: Digest
    revision: CommitId
    module: Module
    symbol: Symbol
    import_root: Literal[".", "src"]
    profile: Literal["direct", "static-reexport-v2"]
    source_ref: ArtifactRef
    license_ref: ArtifactRef
    tree_pins: Annotated[tuple[ExecutionInputPin, ...], Field(min_length=1, max_length=2048)]
    closure_pins: Annotated[tuple[ExecutionInputPin, ...], Field(min_length=1, max_length=256)]
    assessment_digest: Digest
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        for pins in (self.tree_pins, self.closure_pins):
            canonical_ids([p.path for p in pins])
        tree = {p.path: p for p in self.tree_pins}
        if any(tree.get(p.path) != p for p in self.closure_pins):
            raise ValueError("Study closure must be part of its full committed tree")
        if self.source_ref not in tree or self.license_ref not in tree:
            raise ValueError("Study target must pin its source and license")
        return self


class StudyCaseMap(FrozenModel):
    case_id: CaseId
    source_assertion_digest: Digest
    keyword_renames: dict[Symbol, Symbol]
    source_only_keywords: tuple[Literal["force_color"], ...] = ()


class StudyCallMap(FrozenModel):
    schema_version: Literal["study-call-map.v1"] = "study-call-map.v1"
    map_id: Identifier
    source_digest: Digest
    target_digest: Digest
    cases: Annotated[tuple[StudyCaseMap, ...], Field(min_length=1, max_length=256)]
    generator: Literal["study-mapped-test.v1"] = "study-mapped-test.v1"
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        canonical_ids([c.case_id for c in self.cases])
        for case in self.cases:
            if len(set(case.keyword_renames.values())) != len(case.keyword_renames):
                raise ValueError("Study keyword mapping must be injective")
            if len(set(case.source_only_keywords)) != len(case.source_only_keywords):
                raise ValueError("Study controls must be unique")
        return self


class StdoutWitnessCase(FrozenModel):
    case_id: CaseId
    stdout: Annotated[str, Field(max_length=4096, strict=True)]


class StudyWitness(FrozenModel):
    schema_version: Literal["study-stdout-witness.v1"] = "study-stdout-witness.v1"
    oracle: Literal["stdout_eq"] = "stdout_eq"
    target_digest: Digest
    map_digest: Digest
    basis_refs: Annotated[tuple[ArtifactRef, ...], Field(min_length=1, max_length=16)]
    cases: Annotated[tuple[StdoutWitnessCase, ...], Field(min_length=1, max_length=256)]
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        canonical_ids(self.basis_refs)
        canonical_ids([c.case_id for c in self.cases])
        return self


class StudyReview(FrozenModel):
    schema_version: Literal["study-review.v1"] = "study-review.v1"
    purpose: Literal["tool_owned_research_fixture_only"] = "tool_owned_research_fixture_only"
    authority: Literal["trusted_local_operator_not_authenticated_identity"] = (
        "trusted_local_operator_not_authenticated_identity"
    )
    review_id: Identifier
    created_at: UtcDateTime
    operator: ReviewReason
    reason: ReviewReason
    action: Literal["approve", "withdraw"] = "approve"
    source_digest: Digest
    target_digest: Digest
    map_digest: Digest
    witness_digest: Digest | None = None
    interface_vocabulary: Literal["tool-fixture-interface.v1"] = "tool-fixture-interface.v1"
    source_interface: FixtureInterface
    target_interface: FixtureInterface
    runner: RunnerReview
    policy_digest: Digest
    implementation_digests: dict[str, Digest]
    previous_review_ref: ArtifactRef | None = None
    previous_review_digest: Digest | None = None
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        if (self.previous_review_ref is None) != (self.previous_review_digest is None):
            raise ValueError("Study review predecessor requires both reference and digest")
        if not self.operator.strip() or not self.reason.strip():
            raise ValueError("Study review requires an operator and reason")
        return self


class StudyReplayPlan(FrozenModel):
    schema_version: Literal["study-replay-plan.v1"] = "study-replay-plan.v1"
    purpose: Literal["tool_owned_research_fixture_only"] = "tool_owned_research_fixture_only"
    source_ref: ArtifactRef
    target_ref: ArtifactRef
    map_ref: ArtifactRef
    review_ref: ArtifactRef
    witness_ref: ArtifactRef | None = None
    method: Method
    lane: Lane = "guard"
    timeout_seconds: CaptureTimeout = 10.0
    artifact_digest: Digest


class StudyAdmission(FrozenModel):
    schema_version: Literal["study-admission.v1"] = "study-admission.v1"
    decision: Literal["applicable", "inapplicable", "unknown"]
    reason_code: Identifier
    source_digest: Digest
    target_digest: Digest
    map_digest: Digest
    review_digest: Digest
    witness_digest: Digest | None
    method: Method
    lane: Lane
    artifact_digest: Digest


class StudyInputOrigin(FrozenModel):
    path: ArtifactRef
    origin: Literal["source_contract", "target_source"]
    repository_identity_digest: Digest
    revision: CommitId
    original_ref: ArtifactRef


class StudyAuthorization(FrozenModel):
    schema_version: Literal["docker-execution-authorization.v6"] = (
        "docker-execution-authorization.v6"
    )
    purpose: Literal["tool_owned_research_fixture_only"] = "tool_owned_research_fixture_only"
    backend: Literal["docker"] = "docker"
    role: Literal[RunRole.REPLAY] = RunRole.REPLAY
    source_head: CommitId
    target_revision: CommitId
    source_digest: Digest
    target_digest: Digest
    map_digest: Digest
    review_digest: Digest
    witness_digest: Digest | None
    admission_digest: Digest
    plan_digest: Digest
    image_digest: Digest
    runner_review_digest: Digest
    policy_digest: Digest
    implementation_digests: dict[str, Digest]
    request_digest: Digest
    input_pins: tuple[ExecutionInputPin, ...]
    input_origins: tuple[StudyInputOrigin, ...]
    import_root: Literal[".", "src"]
    test_ref: ArtifactRef
    test_digest: Digest
    known_case_ids: tuple[str, ...]
    artifact_digest: Digest


class StudyReplay(FrozenModel):
    schema_version: Literal["study-replay.v1"] = "study-replay.v1"
    purpose: Literal["tool_owned_research_fixture_only"] = "tool_owned_research_fixture_only"
    created_at: UtcDateTime
    plan_ref: ArtifactRef
    plan_digest: Digest
    review_anchor: Digest
    admission: StudyAdmission | None
    integrity: Literal["current", "invalid", "stale"]
    outcome: Literal[
        "skipped_inapplicable",
        "skipped_unknown",
        "passed",
        "test_failed",
        "infrastructure_error",
        "integrity_error",
    ]
    reason_code: Identifier
    run: RunRecord | None
    authorization_ref: ArtifactRef | None
    record_ref: ArtifactRef | None
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        if (self.run is None) != (self.record_ref is None):
            raise ValueError("Study execution must retain its actual record")
        if self.run is None and self.outcome in {"passed", "test_failed"}:
            raise ValueError("A skipped study is never a pass")
        return self
