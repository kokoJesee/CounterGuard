"""Current Registry/Scope authorization for a minimal standalone Docker replay."""

from pathlib import Path
from uuid import uuid4

from counterguard.admission import assess_minimal_python
from counterguard.artifacts import write_immutable
from counterguard.bootstrap_binding import _runtime_assessment
from counterguard.change_analysis import inspect_repository
from counterguard.digests import canonical_json_bytes, digest_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import RunRole
from counterguard.registry import Registry, StandaloneRegistryEntry
from counterguard.repository import read_committed_files
from counterguard.runner_catalog import resolve_runner
from counterguard.standalone_capture import _model, _require
from counterguard.standalone_guard import (
    GuardDockerExecutor,
    authorize_guard_inputs,
    guard_request,
    render_minimal_test,
)
from counterguard.standalone_models import StandaloneScope
from counterguard.standalone_test import CONTRACT_REF, TEST_REF


class StandaloneScopeUnknown(ValueError):
    """Valid provenance does not establish applicability for this target snapshot."""


def _admission(request, guard_id, expected_mapping=None):
    verified = Registry(request.registry).resolve_for_verification(guard_id)
    if not isinstance(verified.entry, StandaloneRegistryEntry):
        raise ArtifactIntegrityError("standalone_registry_provenance_required")
    workspace = Path(verified.entry.source_workspace).resolve(strict=True)
    repo = Path(verified.entry.source_repository).resolve(strict=True)
    if repo != request.repo.resolve(strict=True):
        raise StandaloneScopeUnknown("standalone_repository_identity_outside_scope")
    plan, evidence, capture, binding, contract = verified.source_facts
    review = resolve_runner(runner_id=None, image_digest=request.image_digest)
    if review != capture.runner:
        raise StandaloneScopeUnknown("standalone_runner_outside_scope")
    inspection = inspect_repository(request.repo, request.base, request.head, request.config)
    from counterguard.project_config import load_project_config

    config, _ = load_project_config(request.config)
    candidates = [
        item
        for item in config.targets
        if item.guard_id == guard_id and (expected_mapping is None or item == expected_mapping)
    ]
    if len(candidates) != 1:
        raise StandaloneScopeUnknown("standalone_target_mapping_not_unique")
    mapping = candidates[0]
    refs = set(contract.runtime_refs) | {binding["contract_ref"]}
    if (
        mapping.module != contract.target_module
        or mapping.symbol != contract.target_symbol
        or mapping.source_ref != contract.source_ref
        or mapping.contract_ref != binding["contract_ref"]
        or mapping.import_root != contract.import_root
        or set(mapping.input_refs()) != refs
    ):
        raise StandaloneScopeUnknown("standalone_mapping_outside_scope")
    if inspection.status != "ready":
        raise StandaloneScopeUnknown("standalone_inspection_not_ready")
    revision, files, pins = read_committed_files(repo, inspection.head_commit)
    _require(revision == inspection.head_commit, "standalone_replay_head_changed")
    current_pins = {pin.path: pin for pin in pins}
    _require(
        all(
            current_pins.get(pin.path) == pin for pin in inspection.files if pin.revision == "head"
        ),
        "standalone_replay_inspection_changed",
    )
    if (
        files.get(binding["contract_ref"]) is None
        or digest_bytes(files[binding["contract_ref"]]) != evidence.contract_digest
    ):
        raise StandaloneScopeUnknown("standalone_contract_outside_scope")
    assessment = _runtime_assessment(files, contract)
    if assessment["status"] != "review_required":
        raise StandaloneScopeUnknown("standalone_runtime_requires_review")
    python_findings = {
        "declared_python_version_excludes_runner",
        "python_version_constraint_requires_review",
        "project_metadata_requires_review",
    }
    if any(
        item["code"] in python_findings
        for item in assess_minimal_python(files, import_root=contract.import_root)["findings"]
    ):
        raise StandaloneScopeUnknown("standalone_python_outside_scope")
    scope = _model(workspace, verified.guard.scope_ref, StandaloneScope)
    actual = {pin["path"]: pin["content_digest"] for pin in assessment["files"]}
    if actual not in scope.snapshots.values():
        raise StandaloneScopeUnknown("standalone_source_snapshot_unknown")
    return (
        verified,
        workspace,
        plan,
        evidence,
        capture,
        binding,
        contract,
        inspection,
        mapping,
        revision,
        files,
        pins,
        scope,
        actual,
    )


def authorize_standalone_replay(request, guard_id, mapping, run_request):
    (
        verified,
        workspace,
        _,
        evidence,
        capture,
        binding,
        contract,
        inspection,
        actual_mapping,
        revision,
        _,
        pins,
        scope,
        actual,
    ) = _admission(request, guard_id, mapping)
    output = (
        request.output
        if request.output.is_absolute()
        else request.cwd.resolve(strict=True) / request.output
    )
    runtime = output / "work" / actual_mapping.target_id
    _require(run_request.role is RunRole.REPLAY, "standalone_replay_role_required")
    return authorize_guard_inputs(
        run_request,
        workspace=workspace,
        runtime=runtime,
        contract=contract,
        binding=binding,
        revision=revision,
        source_pins={pin.path: pin.model_dump(mode="json") for pin in pins},
        source_refs=sorted(actual),
        case_ids=verified.guard.case_ids,
        evidence=evidence,
        capture=capture,
        purpose="standalone_registry_replay",
        provenance_digest=verified.guard.artifact_digest,
        scope_digest=scope.artifact_digest,
        registry_entry_digest=verified.entry.artifact_digest,
        registry_event_tip_digest=verified.event_tip_digest,
        inspection_digest=inspection.artifact_digest,
    )


def prepare_standalone_replay(request, output, mapping, expected_inspection):
    (
        verified,
        _,
        _,
        evidence,
        capture,
        binding,
        contract,
        inspection,
        _,
        _,
        files,
        pins,
        scope,
        actual,
    ) = _admission(request, mapping.guard_id, mapping)
    _require(inspection == expected_inspection, "standalone_inspection_changed_before_replay")
    runtime = output / "work" / mapping.target_id
    for ref in sorted(actual):
        write_immutable(runtime / ref, files[ref])
    write_immutable(runtime / CONTRACT_REF, files[binding["contract_ref"]])
    write_immutable(runtime / TEST_REF, render_minimal_test(contract, verified.guard.case_ids))
    source_pin = next(pin for pin in pins if pin.path == contract.source_ref)
    run_request = guard_request(
        runtime,
        contract,
        evidence,
        capture,
        source_pin.model_dump(mode="json"),
        RunRole.REPLAY,
        "run_" + uuid4().hex,
    )

    def authorize(actual):
        return authorize_standalone_replay(request, mapping.guard_id, mapping, actual)

    auth = authorize(run_request)
    write_immutable(runtime / "authorization.json", canonical_json_bytes(auth))
    return scope.artifact_digest, run_request, GuardDockerExecutor(auth, authorize, capture)
