"""New persistence versions for reviewed, Docker-only generic capture."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from counterguard.models import ArtifactRef, Digest, FrozenModel, RunRecord, RunRole, UtcDateTime
from counterguard.runner_catalog import RunnerReview
from counterguard.runners.docker import ExecutionInputPin

EvidenceId = Annotated[
    str, StringConstraints(pattern=r"^evd_[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$", strict=True)
]
ReviewReason = Annotated[str, StringConstraints(min_length=1, max_length=1024, strict=True)]
CaptureTimeout = Annotated[float, Field(gt=0, le=30, allow_inf_nan=False, strict=True)]


class StandaloneCapture(FrozenModel):
    schema_version: Literal["standalone-capture.v1"] = "standalone-capture.v1"
    evidence_id: EvidenceId
    created_at: UtcDateTime
    output_ref: ArtifactRef
    binding_ref: ArtifactRef
    binding_digest: Digest
    runner: RunnerReview
    review_reason: ReviewReason
    review_authority: Literal["trusted_local_operator_not_authenticated_identity"] = (
        "trusted_local_operator_not_authenticated_identity"
    )
    generator_version: Literal["standalone-test.v1"] = "standalone-test.v1"
    timeout_seconds: CaptureTimeout
    implementation_digests: dict[str, Digest]
    policy_digest: Digest
    artifact_digest: Digest


class StandaloneAuthorization(FrozenModel):
    schema_version: Literal["docker-execution-authorization.v4"] = (
        "docker-execution-authorization.v4"
    )
    profile: Literal["standalone-literals-docker.v1"] = "standalone-literals-docker.v1"
    backend: Literal["docker"] = "docker"
    role: Literal[RunRole.BUGGY, RunRole.FIXED]
    capture_digest: Digest
    binding_digest: Digest
    target_revision: str
    assertion_head: str
    runner_review_digest: Digest
    image_digest: Digest
    policy_digest: Digest
    implementation_digests: dict[str, Digest]
    request_digest: Digest
    input_pins: tuple[ExecutionInputPin, ...]
    input_origins: dict[ArtifactRef, ArtifactRef]
    import_root: Literal[".", "src"]
    test_ref: ArtifactRef
    test_digest: Digest
    known_case_ids: tuple[str, ...]
    case_id_map: dict[str, str]
    artifact_digest: Digest


class StandaloneExecution(FrozenModel):
    workspace_ref: ArtifactRef
    authorization_ref: ArtifactRef
    record_ref: ArtifactRef
    run: RunRecord


class StandaloneEvidence(FrozenModel):
    schema_version: Literal["evidence.v4"] = "evidence.v4"
    profile: Literal["standalone-literals-docker.v1"] = "standalone-literals-docker.v1"
    evidence_id: EvidenceId
    created_at: UtcDateTime
    capture_ref: ArtifactRef
    capture_digest: Digest
    binding_digest: Digest
    contract_id: str
    contract_digest: Digest
    buggy: StandaloneExecution
    fixed: StandaloneExecution
    failing_case_ids: tuple[str, ...]
    reproduced: bool
    rejection_reasons: tuple[str, ...]
    artifact_digest: Digest


GuardId = Annotated[
    str, StringConstraints(pattern=r"^grd_[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$", strict=True)
]


class StandaloneCompilation(FrozenModel):
    schema_version: Literal["standalone-compilation.v1"] = "standalone-compilation.v1"
    guard_id: GuardId
    created_at: UtcDateTime
    output_ref: ArtifactRef
    source_evidence_ref: ArtifactRef
    source_evidence_digest: Digest
    review_reason: ReviewReason
    implementation_digests: dict[str, Digest]
    artifact_digest: Digest


class StandaloneGuardAuthorization(FrozenModel):
    schema_version: Literal["docker-execution-authorization.v5"] = (
        "docker-execution-authorization.v5"
    )
    backend: Literal["docker"] = "docker"
    purpose: Literal["minimal_guard_self_check", "standalone_registry_replay"]
    role: RunRole
    provenance_digest: Digest
    evidence_digest: Digest
    binding_digest: Digest
    target_revision: str
    assertion_head: str
    image_digest: Digest
    runner_review_digest: Digest
    policy_digest: Digest
    implementation_digests: dict[str, Digest]
    request_digest: Digest
    input_pins: tuple[ExecutionInputPin, ...]
    input_origins: dict[ArtifactRef, ArtifactRef]
    import_root: Literal[".", "src"]
    test_ref: ArtifactRef
    test_digest: Digest
    known_case_ids: tuple[str, ...]
    case_id_map: dict[str, str]
    scope_digest: Digest | None = None
    registry_entry_digest: Digest | None = None
    registry_event_tip_digest: Digest | None = None
    inspection_digest: Digest | None = None
    artifact_digest: Digest


class StandaloneScope(FrozenModel):
    schema_version: Literal["standalone-snapshot-scope.v1"] = "standalone-snapshot-scope.v1"
    guard_id: GuardId
    source_evidence_digest: Digest
    binding_digest: Digest
    target_module: str
    target_symbol: str
    import_root: Literal[".", "src"]
    contract_ref: ArtifactRef
    contract_digest: Digest
    # Each role has an exact path -> content digest map; never a Cartesian mix.
    snapshots: dict[str, dict[ArtifactRef, Digest]]
    artifact_digest: Digest


class StandaloneGuard(FrozenModel):
    schema_version: Literal["guard.v3"] = "guard.v3"
    profile: Literal["standalone-literals-docker.v1"] = "standalone-literals-docker.v1"
    guard_id: GuardId
    state: Literal["candidate"] = "candidate"
    created_at: UtcDateTime
    compilation_ref: ArtifactRef
    compilation_digest: Digest
    source_evidence_ref: ArtifactRef
    source_evidence_digest: Digest
    contract_id: str
    contract_digest: Digest
    case_ids: tuple[str, ...]
    generator_version: Literal["standalone-guard-test.v1"] = "standalone-guard-test.v1"
    test_ref: ArtifactRef
    test_digest: Digest
    scope_ref: ArtifactRef
    scope_digest: Digest
    buggy_check: StandaloneExecution
    fixed_check: StandaloneExecution
    artifact_digest: Digest
