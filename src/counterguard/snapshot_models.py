"""Research-only snapshot types. None are production Scope/Registry artifacts."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.contract_draft_models import DraftCase, DraftMatchCase
from counterguard.models import Digest, FrozenModel, RunRecord, UtcDateTime
from counterguard.project_config import Module, RepositoryPath, Symbol
from counterguard.runner_catalog import RunnerReview
from counterguard.runners.docker import ExecutionInputPin
from counterguard.snapshot_repository import SnapshotBudget, SnapshotManifest
from counterguard.standalone_contracts import CommitId, ContractId
from counterguard.standalone_models import CaptureTimeout, EvidenceId, GuardId, ReviewReason

PROFILE = "source-only-python-snapshot.v1"
ZERO = "sha256:" + "0" * 64


class SnapshotOrigin(FrozenModel):
    test_ref: RepositoryPath
    test_function: Symbol
    test_object_id: CommitId
    test_digest: Digest
    extractor_version: Literal["snapshot-test-projection.v1"] = "snapshot-test-projection.v1"
    projection_digest: Digest


class SnapshotContract(FrozenModel):
    schema_version: Literal["research-snapshot-contract.v1"] = "research-snapshot-contract.v1"
    profile: Literal["source-only-python-snapshot.v1"] = PROFILE
    contract_id: ContractId
    buggy_commit: CommitId
    fixed_commit: CommitId
    target_module: Module
    target_symbol: Symbol
    source_ref: RepositoryPath
    import_root: Literal[".", "src"]
    test_origin: SnapshotOrigin
    cases: Annotated[tuple[DraftMatchCase | DraftCase, ...], Field(min_length=1, max_length=256)]
    authority: Literal["repository_declaration_not_execution_authorization"] = (
        "repository_declaration_not_execution_authorization"
    )

    @model_validator(mode="after")
    def coherent(self):
        if self.buggy_commit == self.fixed_commit:
            raise ValueError("snapshot_fix_requires_different_commits")
        prefix = "" if self.import_root == "." else "src/"
        stem = prefix + self.target_module.replace(".", "/")
        if self.source_ref not in {stem + ".py", stem + "/__init__.py"}:
            raise ValueError("snapshot_entry_mapping_mismatch")
        if not self.test_origin.test_function.startswith("test_"):
            raise ValueError("snapshot_requires_test_function")
        ids = tuple(case.case_id for case in self.cases)
        if len(set(ids)) != len(ids):
            raise ValueError("snapshot_duplicate_cases")
        # This version preserves source assertion/parameter order, never lexical ID order.
        order = tuple((c.assertion_index, c.parameter_index) for c in self.cases)
        if order != tuple(sorted(set(order))):
            raise ValueError("snapshot_cases_must_preserve_source_order")
        count = 0
        for case in self.cases:
            if len(case.positional_args) + len(case.keyword_args) > 32:
                raise ValueError("snapshot_argument_budget_exceeded")
            pending = [
                (v, 0)
                for v in (
                    *case.positional_args,
                    *(x.literal for x in case.keyword_args),
                    *((case.expected,) if case.expected is not None else ()),
                )
            ]
            while pending:
                value, depth = pending.pop()
                count += 1
                if depth > 8 or count > 10000:
                    raise ValueError("snapshot_literal_budget_exceeded")
                pending.extend((v, depth + 1) for v in value.items)
                pending.extend((v, depth + 1) for pair in value.entries for v in pair)
        return self


class SnapshotBinding(FrozenModel):
    schema_version: Literal["research-snapshot-binding.v1"] = "research-snapshot-binding.v1"
    profile: Literal["source-only-python-snapshot.v1"] = PROFILE
    status: Literal["independent_review_required"] = "independent_review_required"
    head_commit: CommitId
    contract_ref: RepositoryPath
    contract_digest: Digest
    contract: SnapshotContract
    trees: dict[Literal["buggy", "fixed", "head"], SnapshotManifest]
    package_refs: dict[Literal["buggy", "fixed", "head"], tuple[RepositoryPath, ...]]
    tool_additions: tuple[RepositoryPath, ...]
    upstream_refs: tuple[RepositoryPath, ...]
    budget: SnapshotBudget
    execution_allowed: Literal[False] = False
    semantic_review: Literal["not_performed"] = "not_performed"
    implementation_digests: dict[str, Digest]
    artifact_digest: Digest


class SnapshotReview(FrozenModel):
    schema_version: Literal["research-snapshot-review.v1"] = "research-snapshot-review.v1"
    profile: Literal["source-only-python-snapshot.v1"] = PROFILE
    purpose: Literal["tool_owned_fixture"] = "tool_owned_fixture"
    authority: Literal["trusted_local_operator_not_authenticated_identity"] = (
        "trusted_local_operator_not_authenticated_identity"
    )
    review_kind: Literal["execution", "semantics"]
    created_at: UtcDateTime
    reason: ReviewReason
    binding_digest: Digest
    runner: RunnerReview
    budget: SnapshotBudget
    timeout_seconds: CaptureTimeout
    policy_digest: Digest
    implementation_digests: dict[str, Digest]
    artifact_digest: Digest


class SnapshotAuthorization(FrozenModel):
    schema_version: Literal["research-snapshot-authorization.v1"] = (
        "research-snapshot-authorization.v1"
    )
    profile: Literal["source-only-python-snapshot.v1"] = PROFILE
    purpose: Literal["fixture_capture", "fixture_guard_check", "fixture_replay"]
    backend: Literal["docker"] = "docker"
    review_digest: Digest
    binding_digest: Digest
    target_manifest_digest: Digest
    implementation_digests: dict[str, Digest]
    image_digest: Digest
    policy_digest: Digest
    request_digest: Digest
    input_pins: tuple[ExecutionInputPin, ...]
    import_root: Literal[".", "src"]
    test_ref: RepositoryPath
    test_digest: Digest
    artifact_digest: Digest


class SnapshotExecution(FrozenModel):
    workspace_ref: RepositoryPath
    authorization_ref: RepositoryPath
    record_ref: RepositoryPath
    run: RunRecord


class SnapshotEvidence(FrozenModel):
    schema_version: Literal["research-snapshot-evidence.v1"] = "research-snapshot-evidence.v1"
    profile: Literal["source-only-python-snapshot.v1"] = PROFILE
    evidence_id: EvidenceId
    created_at: UtcDateTime
    binding_digest: Digest
    review_digest: Digest
    contract_digest: Digest
    buggy: SnapshotExecution
    fixed: SnapshotExecution
    failing_case_ids: tuple[str, ...]
    reproduced: bool
    rejection_reasons: tuple[str, ...]
    artifact_digest: Digest


class SnapshotGuard(FrozenModel):
    schema_version: Literal["research-snapshot-guard.v1"] = "research-snapshot-guard.v1"
    profile: Literal["source-only-python-snapshot.v1"] = PROFILE
    state: Literal["fixture_candidate_not_schedulable"] = "fixture_candidate_not_schedulable"
    guard_id: GuardId
    created_at: UtcDateTime
    evidence_digest: Digest
    binding_digest: Digest
    review_digest: Digest
    case_ids: tuple[str, ...]
    test_digest: Digest
    buggy_check: SnapshotExecution
    fixed_check: SnapshotExecution
    artifact_digest: Digest


class SnapshotReplay(FrozenModel):
    schema_version: Literal["research-snapshot-replay.v1"] = "research-snapshot-replay.v1"
    profile: Literal["source-only-python-snapshot.v1"] = PROFILE
    purpose: Literal["tool_owned_fixture"] = "tool_owned_fixture"
    decision: Literal["exact_reviewed_fixture_snapshot"] = "exact_reviewed_fixture_snapshot"
    guard_digest: Digest
    evidence_digest: Digest
    review_digest: Digest
    binding_digest: Digest
    source_role: Literal["buggy", "fixed"]
    target_manifest_digest: Digest
    execution: SnapshotExecution
    artifact_digest: Digest
