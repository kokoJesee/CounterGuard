"""Independent fixture-only comparison types; old snapshot/production readers reject them."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.contract_draft_models import DraftCase, DraftMatchCase
from counterguard.models import Digest, FrozenModel, RunRecord, UtcDateTime
from counterguard.project_config import Identifier, Module, RepositoryPath, Symbol
from counterguard.runner_catalog import RunnerReview
from counterguard.runners.docker import ExecutionInputPin
from counterguard.snapshot_repository import SnapshotManifest
from counterguard.standalone_contracts import CommitId
from counterguard.standalone_models import CaptureTimeout, ReviewReason
from counterguard.study_models import Method

Interface = Literal["value_return", "stdout_write"]
Lane = Literal["guard", "own_contract"]
CaseId = Annotated[str, Field(pattern=r"^case_[a-f0-9]{24}$", strict=True)]


class SnapshotTargetEntry(FrozenModel):
    target_module: Module
    target_symbol: Symbol
    source_ref: RepositoryPath
    import_root: Literal[".", "src"]

    @model_validator(mode="after")
    def coherent(self):
        prefix = "" if self.import_root == "." else "src/"
        stem = prefix + self.target_module.replace(".", "/")
        if self.source_ref not in {stem + ".py", stem + "/__init__.py"}:
            raise ValueError("snapshot_target_entry_mapping_mismatch")
        return self


class SnapshotComparisonTarget(FrozenModel):
    schema_version: Literal["snapshot-comparison-target.v1"] = "snapshot-comparison-target.v1"
    profile: Literal["source-only-python-snapshot.v1"] = "source-only-python-snapshot.v1"
    target_id: Identifier
    repository_identity_digest: Digest
    entry: SnapshotTargetEntry
    manifest: SnapshotManifest
    package_refs: Annotated[tuple[RepositoryPath, ...], Field(min_length=1, max_length=2048)]
    license_ref: RepositoryPath
    license_digest: Digest
    interface_kind: Interface
    interface_basis_ref: RepositoryPath
    execution_allowed: Literal[False] = False
    implementation_digests: dict[str, Digest]
    artifact_digest: Digest


class SnapshotMappedCase(FrozenModel):
    case_id: CaseId
    source_case_digest: Digest


class SnapshotComparisonMap(FrozenModel):
    schema_version: Literal["snapshot-comparison-map.v1"] = "snapshot-comparison-map.v1"
    mapping: Literal["identity_call_all_minimal_cases"] = "identity_call_all_minimal_cases"
    guard_digest: Digest
    target_digest: Digest
    cases: Annotated[tuple[SnapshotMappedCase, ...], Field(min_length=1, max_length=256)]
    artifact_digest: Digest


class SnapshotOwnWitness(FrozenModel):
    schema_version: Literal["snapshot-comparison-own-witness.v1"] = (
        "snapshot-comparison-own-witness.v1"
    )
    target_digest: Digest
    map_digest: Digest
    basis_refs: Annotated[tuple[RepositoryPath, ...], Field(min_length=1, max_length=16)]
    cases: Annotated[tuple[DraftMatchCase | DraftCase, ...], Field(min_length=1, max_length=256)]
    role: Literal["target_own_observation_not_source_oracle_or_label"] = (
        "target_own_observation_not_source_oracle_or_label"
    )
    artifact_digest: Digest

    @model_validator(mode="after")
    def finite_witness(self):
        if self.basis_refs != tuple(sorted(set(self.basis_refs))):
            raise ValueError("snapshot_witness_basis_must_be_unique_sorted")
        if any(
            c.expected is not None and c.expected.kind in {"dict", "list", "tuple"}
            for c in self.cases
        ):
            raise ValueError("snapshot_own_expected_scalar_required")
        return self


class SnapshotComparisonReview(FrozenModel):
    schema_version: Literal["snapshot-comparison-review.v1"] = "snapshot-comparison-review.v1"
    purpose: Literal["tool_owned_snapshot_comparison_only"] = "tool_owned_snapshot_comparison_only"
    authority: Literal["trusted_local_operator_not_authenticated_identity"] = (
        "trusted_local_operator_not_authenticated_identity"
    )
    action: Literal["approve", "withdraw"] = "approve"
    created_at: UtcDateTime
    reason: ReviewReason
    source_review_digest: Digest
    source_guard_digest: Digest
    source_binding_digest: Digest
    target_digest: Digest
    map_digest: Digest
    witness_digest: Digest | None
    source_interface: Interface
    source_interface_basis_ref: RepositoryPath
    runner: RunnerReview
    policy_digest: Digest
    timeout_seconds: CaptureTimeout
    implementation_digests: dict[str, Digest]
    artifact_digest: Digest


class SnapshotComparisonPlan(FrozenModel):
    schema_version: Literal["snapshot-comparison-plan.v1"] = "snapshot-comparison-plan.v1"
    purpose: Literal["tool_owned_snapshot_comparison_only"] = "tool_owned_snapshot_comparison_only"
    evidence_ref: RepositoryPath
    guard_ref: RepositoryPath
    target_ref: RepositoryPath
    map_ref: RepositoryPath
    review_ref: RepositoryPath
    witness_ref: RepositoryPath | None = None
    method: Method
    lane: Lane = "guard"
    timeout_seconds: CaptureTimeout = 10.0
    artifact_digest: Digest


class SnapshotComparisonAdmission(FrozenModel):
    schema_version: Literal["snapshot-comparison-admission.v1"] = "snapshot-comparison-admission.v1"
    plan_digest: Digest
    guard_digest: Digest
    target_digest: Digest
    map_digest: Digest
    review_digest: Digest
    witness_digest: Digest | None
    method: Method
    lane: Lane
    decision: Literal["applicable", "inapplicable", "unknown"]
    reason_code: Identifier
    artifact_digest: Digest


class SnapshotComparisonAuthorization(FrozenModel):
    schema_version: Literal["snapshot-comparison-authorization.v1"] = (
        "snapshot-comparison-authorization.v1"
    )
    purpose: Literal["tool_owned_snapshot_comparison_only"] = "tool_owned_snapshot_comparison_only"
    backend: Literal["docker"] = "docker"
    source_head: CommitId
    target_revision: CommitId
    source_review_digest: Digest
    comparison_review_digest: Digest
    source_binding_digest: Digest
    source_guard_digest: Digest
    target_digest: Digest
    target_manifest_digest: Digest
    map_digest: Digest
    witness_digest: Digest | None
    plan_digest: Digest
    admission_digest: Digest
    image_digest: Digest
    policy_digest: Digest
    implementation_digests: dict[str, Digest]
    request_digest: Digest
    input_pins: tuple[ExecutionInputPin, ...]
    import_root: Literal[".", "src"]
    test_ref: RepositoryPath
    test_digest: Digest
    artifact_digest: Digest


class SnapshotComparisonReplay(FrozenModel):
    schema_version: Literal["snapshot-comparison-replay.v1"] = "snapshot-comparison-replay.v1"
    purpose: Literal["tool_owned_snapshot_comparison_only"] = "tool_owned_snapshot_comparison_only"
    created_at: UtcDateTime
    plan_ref: RepositoryPath
    plan_digest: Digest
    source_review_digest: Digest
    comparison_review_digest: Digest
    admission: SnapshotComparisonAdmission
    integrity: Literal["current", "stale"]
    outcome: Literal[
        "passed",
        "test_failed",
        "infrastructure_error",
        "integrity_error",
        "skipped_unknown",
        "skipped_inapplicable",
    ]
    reason_code: Identifier
    workspace_ref: RepositoryPath | None
    authorization_ref: RepositoryPath | None
    record_ref: RepositoryPath | None
    run: RunRecord | None
    artifact_digest: Digest
