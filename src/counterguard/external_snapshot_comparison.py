"""Independent external target/oracle review, with unchanged closed Docker transport."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.external_snapshot import ExternalSnapshotSession
from counterguard.external_snapshot_models import (
    ExternalComparisonAdmission,
    ExternalComparisonAuthorization,
    ExternalComparisonPlan,
    ExternalComparisonReplay,
    ExternalComparisonReview,
    ExternalSnapshotGuard,
    ExternalSnapshotMap,
    ExternalSnapshotReview,
    ExternalSnapshotTarget,
    ExternalSnapshotWitness,
)
from counterguard.project_config import reject_links
from counterguard.runners.docker import DockerPolicyV1
from counterguard.snapshot_admission import read_value, require, seal
from counterguard.snapshot_comparison import SnapshotComparisonSession, _decide_comparison
from counterguard.snapshot_comparison_data import (
    ComparisonFacts,
    _create_comparison_map,
    _inspect_snapshot_target,
    validate_own_witness,
)
from counterguard.snapshot_models import ZERO, SnapshotBinding
from counterguard.snapshot_repository import SNAPSHOT_BUDGET, read_snapshot


def inspect_external_snapshot_target(
    repo,
    revision,
    *,
    repository_url,
    target_id,
    entry,
    license_ref,
    interface_kind,
    interface_basis_ref,
    output=None,
    budget=SNAPSHOT_BUDGET,
):
    return _inspect_snapshot_target(
        repo,
        revision,
        target_id=target_id,
        entry=entry,
        license_ref=license_ref,
        interface_kind=interface_kind,
        interface_basis_ref=interface_basis_ref,
        output=output,
        budget=budget,
        target_model=ExternalSnapshotTarget,
        repository_url=repository_url,
    )


def create_external_snapshot_map(guard, contract, target):
    require(
        type(guard) is ExternalSnapshotGuard and type(target) is ExternalSnapshotTarget,
        "external_snapshot_map_requires_external_subjects",
    )
    return _create_comparison_map(guard, contract, target, ExternalSnapshotMap)


def load_external_comparison_facts(source, target_repo, plan):
    require(
        type(source) is ExternalSnapshotSession and type(plan) is ExternalComparisonPlan,
        "external_snapshot_source_and_plan_types_required",
    )
    workspace = source.workspace
    reject_links(target_repo)
    require(
        Path(target_repo).resolve() != source.repo, "comparison_target_must_be_separate_repository"
    )
    guard = source.verify_guard(
        workspace / plan.guard_ref, evidence_path=workspace / plan.evidence_ref
    )
    binding = read_value(source.binding_path, SnapshotBinding)
    review = read_value(
        source.review_path, ExternalSnapshotReview, expected_digest=source.trusted_digest
    )
    require(
        guard.binding_digest == binding.artifact_digest
        and guard.review_digest == review.artifact_digest,
        "comparison_source_changed_during_load",
    )
    target = read_value(workspace / plan.target_ref, ExternalSnapshotTarget)
    rebuilt, files = inspect_external_snapshot_target(
        target_repo,
        target.manifest.commit,
        repository_url=target.repository_url,
        target_id=target.target_id,
        entry=target.entry,
        license_ref=target.license_ref,
        interface_kind=target.interface_kind,
        interface_basis_ref=target.interface_basis_ref,
        budget=target.manifest.budget,
    )
    require(target == rebuilt, "comparison_target_not_reconstructable")
    mapping = read_value(workspace / plan.map_ref, ExternalSnapshotMap)
    require(
        mapping == create_external_snapshot_map(guard, binding.contract, target),
        "comparison_map_changed_or_dropped_source_case",
    )
    cases = tuple(c for c in binding.contract.cases if c.case_id in guard.case_ids)
    witness = None
    if plan.witness_ref is not None:
        witness = read_value(workspace / plan.witness_ref, ExternalSnapshotWitness)
        validate_own_witness(witness, target, mapping, cases, files)
    manifest, head = read_snapshot(source.repo, binding.head_commit, budget=binding.budget)
    require(manifest == binding.trees["head"], "comparison_source_head_changed")
    return ComparisonFacts(
        guard, binding, review, target, mapping, witness, cases, files, head[binding.contract_ref]
    )


def issue_external_comparison_review(
    source,
    target_repo,
    plan,
    *,
    output,
    reason,
    source_interface,
    source_interface_basis_ref,
    action="approve",
):
    require(type(plan) is ExternalComparisonPlan, "external_snapshot_plan_type_required")
    plan = ExternalComparisonPlan.model_validate_json(canonical_json_bytes(plan))
    require(plan.artifact_digest == digest_json_artifact(plan), "comparison_plan_digest_mismatch")
    facts = load_external_comparison_facts(source, target_repo, plan)
    require(reason.strip(), "comparison_review_reason_required")
    require(
        source_interface_basis_ref in facts.binding.package_refs["fixed"],
        "comparison_source_interface_basis_missing",
    )
    require(
        plan.timeout_seconds <= facts.source_review.timeout_seconds,
        "comparison_timeout_exceeds_source_budget",
    )
    result = seal(
        ExternalComparisonReview(
            action=action,
            created_at=datetime.now(UTC),
            reason=reason,
            source_review_digest=source.trusted_digest,
            source_guard_digest=facts.guard.artifact_digest,
            source_binding_digest=facts.binding.artifact_digest,
            target_digest=facts.target.artifact_digest,
            map_digest=facts.mapping.artifact_digest,
            witness_digest=facts.witness.artifact_digest if facts.witness else None,
            source_interface=source_interface,
            source_interface_basis_ref=source_interface_basis_ref,
            runner=facts.source_review.runner,
            policy_digest=digest_json_artifact(DockerPolicyV1()),
            timeout_seconds=plan.timeout_seconds,
            implementation_digests=inspection_implementation_digests(),
            artifact_digest=ZERO,
        )
    )
    write_immutable(Path(output), canonical_json_bytes(result))
    return result


@dataclass(frozen=True)
class ExternalSnapshotComparisonSession(SnapshotComparisonSession):
    _PLAN = ExternalComparisonPlan
    _REVIEW = ExternalComparisonReview
    _AUTHORIZATION = ExternalComparisonAuthorization
    _RESULT = ExternalComparisonReplay

    def __post_init__(self):
        require(
            type(self.source) is ExternalSnapshotSession, "external_snapshot_source_type_required"
        )
        super().__post_init__()

    def _facts(self, plan):
        return load_external_comparison_facts(self.source, self.target_repo, plan)

    def _decision(self, plan, facts, review):
        return _decide_comparison(plan, facts, review, ExternalComparisonAdmission)
