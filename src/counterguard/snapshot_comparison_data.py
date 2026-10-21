"""Read-only comparison provenance; no candidate imports or host execution."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.project_config import reject_links
from counterguard.runners.docker import DockerPolicyV1
from counterguard.snapshot_admission import (
    FIXTURE_MARKER,
    FIXTURE_REF,
    _package,
    read_value,
    require,
    seal,
)
from counterguard.snapshot_comparison_models import (
    SnapshotComparisonMap,
    SnapshotComparisonPlan,
    SnapshotComparisonReview,
    SnapshotComparisonTarget,
    SnapshotMappedCase,
    SnapshotOwnWitness,
    SnapshotTargetEntry,
)
from counterguard.snapshot_models import ZERO, SnapshotBinding, SnapshotGuard, SnapshotReview
from counterguard.snapshot_repository import SNAPSHOT_BUDGET, read_snapshot
from counterguard.standalone_contracts import CommitId


def inspect_snapshot_target(
    repo,
    revision,
    *,
    target_id,
    entry,
    license_ref,
    interface_kind,
    interface_basis_ref,
    output=None,
    budget=SNAPSHOT_BUDGET,
):
    entry = SnapshotTargetEntry.model_validate_json(canonical_json_bytes(entry))
    TypeAdapter(CommitId).validate_python(revision)
    require(
        entry.target_module.split(".")[0].casefold()
        not in {
            "cg_control",
            "pytest",
            "sitecustomize",
            "usercustomize",
            "conftest",
        },
        "comparison_reserved_target_package",
    )
    manifest, files = read_snapshot(repo, revision, budget=budget)
    refs = _package(files, entry)
    require(license_ref in files and files[license_ref].strip(), "comparison_license_missing")
    require(
        interface_basis_ref in files and files[interface_basis_ref].strip(),
        "comparison_interface_basis_missing",
    )
    reject_links(repo)
    target = seal(
        SnapshotComparisonTarget(
            target_id=target_id,
            repository_identity_digest=digest_bytes(str(Path(repo).resolve()).encode()),
            entry=entry,
            manifest=manifest,
            package_refs=refs,
            license_ref=license_ref,
            license_digest=digest_bytes(files[license_ref]),
            interface_kind=interface_kind,
            interface_basis_ref=interface_basis_ref,
            implementation_digests=inspection_implementation_digests(),
            artifact_digest=ZERO,
        )
    )
    if output is not None:
        write_immutable(Path(output), canonical_json_bytes(target))
    return target, files


@dataclass(frozen=True)
class ComparisonFacts:
    guard: SnapshotGuard
    binding: SnapshotBinding
    source_review: SnapshotReview
    target: SnapshotComparisonTarget
    mapping: SnapshotComparisonMap
    witness: SnapshotOwnWitness | None
    cases: tuple
    target_files: dict[str, bytes]
    source_contract: bytes


def create_comparison_map(guard, contract, target):
    cases = tuple(c for c in contract.cases if c.case_id in guard.case_ids)
    require(
        tuple(c.case_id for c in cases) == guard.case_ids, "comparison_guard_case_order_mismatch"
    )
    return seal(
        SnapshotComparisonMap(
            guard_digest=guard.artifact_digest,
            target_digest=target.artifact_digest,
            cases=tuple(
                SnapshotMappedCase(case_id=c.case_id, source_case_digest=digest_json_artifact(c))
                for c in cases
            ),
            artifact_digest=ZERO,
        )
    )


def validate_comparison_map(guard, contract, target, mapping):
    require(
        mapping == create_comparison_map(guard, contract, target),
        "comparison_map_changed_or_dropped_source_case",
    )
    return tuple(c for c in contract.cases if c.case_id in guard.case_ids)


def validate_own_witness(witness, target, mapping, cases, files):
    require(
        witness.target_digest == target.artifact_digest
        and witness.map_digest == mapping.artifact_digest
        and tuple(c.case_id for c in witness.cases) == tuple(c.case_id for c in cases),
        "comparison_witness_subject_or_case_set_mismatch",
    )
    require(
        all(ref in files and files[ref].strip() for ref in witness.basis_refs),
        "comparison_witness_basis_missing",
    )
    for original, own in zip(cases, witness.cases, strict=True):
        fields = (
            "case_id",
            "assertion_digest",
            "source_line",
            "assertion_index",
            "parameter_index",
            "positional_args",
            "keyword_args",
        )
        require(
            all(getattr(original, field) == getattr(own, field) for field in fields),
            "comparison_witness_input_or_identity_changed",
        )


def load_comparison_facts(source, target_repo, plan):
    require(type(plan) is SnapshotComparisonPlan, "comparison_plan_type_required")
    workspace = source.workspace
    reject_links(target_repo)
    require(
        Path(target_repo).resolve() != source.repo, "comparison_target_must_be_separate_repository"
    )
    guard = source.verify_guard(
        workspace / plan.guard_ref, evidence_path=workspace / plan.evidence_ref
    )
    binding = read_value(source.binding_path, SnapshotBinding)
    review = read_value(source.review_path, SnapshotReview, expected_digest=source.trusted_digest)
    require(
        guard.binding_digest == binding.artifact_digest
        and guard.review_digest == review.artifact_digest,
        "comparison_source_changed_during_load",
    )
    target = read_value(workspace / plan.target_ref, SnapshotComparisonTarget)
    rebuilt, files = inspect_snapshot_target(
        target_repo,
        target.manifest.commit,
        target_id=target.target_id,
        entry=target.entry,
        license_ref=target.license_ref,
        interface_kind=target.interface_kind,
        interface_basis_ref=target.interface_basis_ref,
        budget=target.manifest.budget,
    )
    require(target == rebuilt, "comparison_target_not_reconstructable")
    require(
        files.get(FIXTURE_REF) == FIXTURE_MARKER, "comparison_only_tool_owned_fixtures_authorized"
    )
    mapping = read_value(workspace / plan.map_ref, SnapshotComparisonMap)
    cases = validate_comparison_map(guard, binding.contract, target, mapping)
    witness = None
    if plan.witness_ref is not None:
        witness = read_value(workspace / plan.witness_ref, SnapshotOwnWitness)
        validate_own_witness(witness, target, mapping, cases, files)
    manifest, head = read_snapshot(source.repo, binding.head_commit, budget=binding.budget)
    require(manifest == binding.trees["head"], "comparison_source_head_changed")
    return ComparisonFacts(
        guard, binding, review, target, mapping, witness, cases, files, head[binding.contract_ref]
    )


def issue_comparison_review(
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
    plan = SnapshotComparisonPlan.model_validate_json(canonical_json_bytes(plan))
    require(plan.artifact_digest == digest_json_artifact(plan), "comparison_plan_digest_mismatch")
    facts = load_comparison_facts(source, target_repo, plan)
    require(reason.strip(), "comparison_review_reason_required")
    require(
        source_interface_basis_ref in facts.binding.package_refs["fixed"],
        "comparison_source_interface_basis_missing",
    )
    require(
        plan.timeout_seconds <= facts.source_review.timeout_seconds,
        "comparison_timeout_exceeds_source_budget",
    )
    review = seal(
        SnapshotComparisonReview(
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
    write_immutable(Path(output), canonical_json_bytes(review))
    return review
