"""New repository provenance shapes; legacy Evidence/Guard bytes remain unchanged."""

from typing import Literal

from counterguard.models import (
    ArtifactRef,
    Digest,
    FrozenModel,
    NonEmptyText,
    RunRecord,
    UtcDateTime,
)
from counterguard.repository_contracts import RepositoryCase


class RepositoryEvidence(FrozenModel):
    schema_version: Literal["evidence.v3"] = "evidence.v3"
    evidence_id: NonEmptyText
    created_at: UtcDateTime
    manifest_ref: ArtifactRef
    manifest_digest: Digest
    contract_id: NonEmptyText
    contract_ref: ArtifactRef
    contract_digest: Digest
    test_ref: ArtifactRef
    test_digest: Digest
    assertion_head: NonEmptyText
    buggy_commit: NonEmptyText
    fixed_commit: NonEmptyText
    buggy_workspace_ref: ArtifactRef
    fixed_workspace_ref: ArtifactRef
    buggy_target_digest: Digest
    fixed_target_digest: Digest
    buggy_run: RunRecord
    fixed_run: RunRecord
    buggy_authorization_ref: ArtifactRef
    fixed_authorization_ref: ArtifactRef
    failing_case_ids: tuple[NonEmptyText, ...]
    reproduced: bool
    rejection_reasons: tuple[NonEmptyText, ...]
    artifact_digest: Digest


class RepositoryGuard(FrozenModel):
    schema_version: Literal["guard.v2"] = "guard.v2"
    generator_version: Literal["guard-test.v3"] = "guard-test.v3"
    guard_id: NonEmptyText
    created_at: UtcDateTime
    source_evidence_id: NonEmptyText
    source_evidence_ref: ArtifactRef
    source_evidence_digest: Digest
    contract_id: NonEmptyText
    contract_digest: Digest
    source_buggy_digest: Digest
    source_fixed_digest: Digest
    cases: tuple[RepositoryCase, ...]
    test_ref: ArtifactRef
    test_digest: Digest
    validation_workspace_ref: ArtifactRef
    validation_run: RunRecord
    validation_authorization_ref: ArtifactRef
    state: Literal["candidate"] = "candidate"
    artifact_digest: Digest
