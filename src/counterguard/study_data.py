"""Independently rebuild research facts; no imports of repository Python."""

import sys
from datetime import UTC, datetime

from counterguard.admission import assess_minimal_python
from counterguard.artifacts import write_immutable
from counterguard.bootstrap_binding import assess_runtime_source
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.project_config import reject_links
from counterguard.repository import read_committed_files
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import DockerPolicyV1, ExecutionInputPin
from counterguard.standalone_capture import ZERO, _model, _require, _seal
from counterguard.standalone_guard import verify_standalone_guard_chain
from counterguard.study_models import (
    StudyCallMap,
    StudyReview,
    StudySource,
    StudyTarget,
    StudyWitness,
)


class StudyNotReady(ValueError):
    """Finite reason for a genuine unsupported input, never an approval override."""


def repository_identity(repo):
    reject_links(repo)
    return digest_bytes(str(repo.resolve(strict=True)).encode())


def persist(path, model):
    raw = canonical_json_bytes(model)
    _require(len(raw) <= 4 * 1024 * 1024, "study_publication_byte_budget_exceeded")
    write_immutable(path, raw)
    return model


def inspect_source(repo, workspace, guard_ref, *, source_id):
    guard, facts = verify_standalone_guard_chain(repo, workspace / guard_ref, cwd=workspace)
    _, evidence, _, binding, _ = facts
    source = _seal(
        StudySource(
            source_id=source_id,
            repository_identity_digest=repository_identity(repo),
            guard_ref=guard_ref,
            guard_digest=guard.artifact_digest,
            evidence_digest=evidence.artifact_digest,
            binding_digest=binding["artifact_digest"],
            buggy_commit=binding["trees"]["buggy"]["commit"],
            fixed_commit=binding["trees"]["fixed"]["commit"],
            assertion_head=binding["head_commit"],
            contract_ref=binding["contract_ref"],
            contract_digest=evidence.contract_digest,
            case_ids=guard.case_ids,
            artifact_digest=ZERO,
        )
    )
    return source, guard, facts


def inspect_target(repo, revision, *, target_id, module, symbol, import_root, profile, license_ref):
    # Validate names/versions before using them to derive paths or inspect Git.
    from pydantic import TypeAdapter

    from counterguard.project_config import Module, Symbol
    from counterguard.standalone_contracts import CommitId

    TypeAdapter(CommitId).validate_python(revision)
    TypeAdapter(Module).validate_python(module)
    TypeAdapter(Symbol).validate_python(symbol)
    if profile not in {"direct", "static-reexport-v2"} or import_root not in {".", "src"}:
        raise StudyNotReady("study_target_profile_unsupported")
    actual, files, pins = read_committed_files(repo, revision)
    _require(actual == revision, "study_target_revision_changed")
    prefix = "" if import_root == "." else "src/"
    module_path = prefix + module.replace(".", "/")
    source_ref = module_path + ("/__init__.py" if profile == "static-reexport-v2" else ".py")
    assessment = assess_runtime_source(
        files,
        module=module,
        symbol=symbol,
        source_ref=source_ref,
        import_root=import_root,
        closure_algorithm="module-import-closure.v2",
        export_algorithm="static-root-reexport.v2" if profile == "static-reexport-v2" else None,
    )
    if assessment["status"] != "review_required":
        raise StudyNotReady("study_target_runtime_unresolved")
    python_findings = {
        "declared_python_version_excludes_runner",
        "python_version_constraint_requires_review",
        "project_metadata_requires_review",
    }
    if any(
        item["code"] in python_findings
        for item in assess_minimal_python(files, import_root=import_root)["findings"]
    ):
        raise StudyNotReady("study_target_python_unresolved")
    selected = {p["path"] for p in assessment["files"]}
    reserved = set(sys.stdlib_module_names) | {
        "cg_control",
        "pytest",
        "sitecustomize",
        "usercustomize",
    }
    for ref in selected:
        relative = ref.removeprefix(prefix) if prefix else ref
        if relative.split("/")[0].removesuffix(".py") in reserved:
            raise StudyNotReady("study_target_reserved_input")
    _require(
        license_ref in files and bool(files[license_ref].strip()), "study_target_license_missing"
    )
    tree = tuple(
        ExecutionInputPin(path=p.path, object_id=p.object_id, content_digest=p.content_digest)
        for p in sorted(pins, key=lambda p: p.path)
    )
    target = _seal(
        StudyTarget(
            target_id=target_id,
            repository_identity_digest=repository_identity(repo),
            revision=actual,
            module=module,
            symbol=symbol,
            import_root=import_root,
            profile=profile,
            source_ref=source_ref,
            license_ref=license_ref,
            tree_pins=tree,
            closure_pins=tuple(p for p in tree if p.path in selected),
            assessment_digest=digest_json_artifact(assessment),
            artifact_digest=ZERO,
        )
    )
    return target, files


def check_mapping(source, target, mapping, contract):
    _require(
        mapping.source_digest == source.artifact_digest
        and mapping.target_digest == target.artifact_digest
        and tuple(row.case_id for row in mapping.cases) == source.case_ids,
        "study_map_source_target_or_cases_changed",
    )
    cases = {c.case_id: c for c in contract.cases}
    result = []
    for row in mapping.cases:
        case = cases[row.case_id]
        _require(row.source_assertion_digest == case.assertion_digest, "study_map_oracle_changed")
        original = {k.name: k.literal for k in case.keyword_args}
        dropped = set(row.source_only_keywords)
        _require(
            set(row.keyword_renames).isdisjoint(dropped)
            and set(row.keyword_renames) | dropped == set(original),
            "study_map_keywords_missing_or_added",
        )
        for name in dropped:
            control = original[name]
            _require(
                control.kind == "boolean" and control.value is True,
                "study_source_control_not_literal_true",
            )
        from counterguard.contract_draft_models import DraftKeyword

        mapped = tuple(
            DraftKeyword(name=new, literal=original[old])
            for old, new in sorted(row.keyword_renames.items(), key=lambda p: p[1])
        )
        # Args and every oracle field come from verified source cases, never the map.
        result.append(case.model_copy(update={"keyword_args": mapped}))
    return tuple(result)


def make_call_map(source, target, contract, *, map_id, cases):
    model = _seal(
        StudyCallMap(
            map_id=map_id,
            source_digest=source.artifact_digest,
            target_digest=target.artifact_digest,
            cases=tuple(sorted(cases, key=lambda c: c.case_id)),
            artifact_digest=ZERO,
        )
    )
    check_mapping(source, target, model, contract)
    return model


def load_facts(source_repo, target_repo, workspace, plan):
    source = _model(workspace, plan.source_ref, StudySource)
    rebuilt, guard, facts = inspect_source(
        source_repo, workspace, source.guard_ref, source_id=source.source_id
    )
    _require(rebuilt == source, "study_source_not_rebuilt")
    target = _model(workspace, plan.target_ref, StudyTarget)
    rebuilt_target, files = inspect_target(
        target_repo,
        target.revision,
        target_id=target.target_id,
        module=target.module,
        symbol=target.symbol,
        import_root=target.import_root,
        profile=target.profile,
        license_ref=target.license_ref,
    )
    _require(rebuilt_target == target, "study_target_not_rebuilt")
    mapping = _model(workspace, plan.map_ref, StudyCallMap)
    mapped = check_mapping(source, target, mapping, facts[-1])
    witness = None
    if plan.witness_ref is not None:
        witness = _model(workspace, plan.witness_ref, StudyWitness)
        _require(
            witness.target_digest == target.artifact_digest
            and witness.map_digest == mapping.artifact_digest
            and set(c.case_id for c in witness.cases) <= set(source.case_ids)
            and all(ref in files for ref in witness.basis_refs),
            "study_witness_not_bound_to_target_map",
        )
    return source, target, mapping, witness, guard, facts, files, mapped


def load_review(workspace, ref, anchor):
    review = _model(workspace, ref, StudyReview)
    _require(review.artifact_digest == anchor, "study_review_anchor_mismatch")
    current, seen = review, {ref}
    for _ in range(32):
        if current.previous_review_ref is None:
            return review
        _require(current.previous_review_ref not in seen, "study_review_chain_cycle")
        seen.add(current.previous_review_ref)
        previous = _model(workspace, current.previous_review_ref, StudyReview)
        _require(
            previous.artifact_digest == current.previous_review_digest,
            "study_review_predecessor_changed",
        )
        _require(previous.created_at <= current.created_at, "study_review_time_regressed")
        current = previous
    raise StudyNotReady("study_review_chain_budget_exceeded")


def issue_review(
    source_repo,
    target_repo,
    workspace,
    plan,
    *,
    output_ref,
    review_id,
    operator,
    reason,
    source_interface,
    target_interface,
    runner_id="root-pytest8",
    previous_ref=None,
    previous_anchor=None,
    action="approve",
):
    """Trusted local approval action. Retain the returned digest outside mutable plan input."""
    source, target, mapping, witness, _, facts, _, _ = load_facts(
        source_repo, target_repo, workspace, plan
    )
    runner = resolve_runner(runner_id=runner_id, image_digest=None)
    _require(runner == facts[2].runner, "study_source_runner_mismatch")
    previous = None
    if previous_ref is not None:
        previous = load_review(workspace, previous_ref, previous_anchor)
    else:
        _require(previous_anchor is None, "study_review_predecessor_incomplete")
    review = _seal(
        StudyReview(
            review_id=review_id,
            created_at=datetime.now(UTC),
            operator=operator,
            reason=reason,
            action=action,
            source_digest=source.artifact_digest,
            target_digest=target.artifact_digest,
            map_digest=mapping.artifact_digest,
            witness_digest=witness.artifact_digest if witness else None,
            source_interface=source_interface,
            target_interface=target_interface,
            runner=runner,
            policy_digest=digest_json_artifact(DockerPolicyV1()),
            implementation_digests=inspection_implementation_digests(),
            previous_review_ref=previous_ref,
            previous_review_digest=previous.artifact_digest if previous else None,
            artifact_digest=ZERO,
        )
    )
    # Validate the output reference even though it has not been created yet.
    from pydantic import TypeAdapter

    from counterguard.models import ArtifactRef

    TypeAdapter(ArtifactRef).validate_python(output_ref)
    reject_links(workspace / output_ref)
    persist(workspace / output_ref, review)
    return review
