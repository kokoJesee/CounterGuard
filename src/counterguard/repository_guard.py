"""Docker-only capture, minimal compilation and independent repository verification."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from counterguard.artifacts import write_immutable
from counterguard.digests import (
    canonical_json_bytes,
    digest_bytes,
    digest_file,
    digest_json_artifact,
)
from counterguard.errors import ArtifactIntegrityError, GuardSelfCheckError, InvalidEvidenceError
from counterguard.execution import PytestRunRequest, verify_run_record
from counterguard.models import CaseOutcome, RunOutcome, RunRole, TargetRef
from counterguard.pilot_inputs import ZERO, closure_digest, load_inputs, read_fact, resolve_ref
from counterguard.repository_contracts import (
    CONTRACT_REF,
    EVIDENCE_ID,
    GUARD_ID,
    SOURCE_REF,
    ExplicitPilotScope,
    render_repository_test,
)
from counterguard.repository_models import RepositoryEvidence, RepositoryGuard
from counterguard.runners.repository import (
    RepositoryAuthorization,
    RepositoryDockerExecutor,
    authorize_repository_execution,
)


def _seal(model):
    return model.model_copy(update={"artifact_digest": digest_json_artifact(model)})


def _model(path: Path, model, workspace: Path):
    path = resolve_ref(workspace, path.relative_to(workspace).as_posix())
    value = model.model_validate_json(canonical_json_bytes(read_fact(path)))
    if path.name != ("guard.json" if model is RepositoryGuard else "evidence.json"):
        raise ArtifactIntegrityError("Artifact filename mismatch")
    identity = value.guard_id if model is RepositoryGuard else value.evidence_id
    kind = "guards" if model is RepositoryGuard else "evidence"
    if path.parent.name != identity or path.parent.parent.name != kind:
        raise ArtifactIntegrityError("Artifact identity/directory mismatch")
    return value


def _verify_record(run, authorization_ref, manifest_path, workspace, expected_phase):
    auth = RepositoryAuthorization.model_validate_json(
        canonical_json_bytes(read_fact(resolve_ref(workspace, authorization_ref)))
    )
    if auth.phase != expected_phase:
        raise ArtifactIntegrityError("Historical authorization purpose mismatch")
    runtime = workspace / auth.workspace_ref
    request = PytestRunRequest(
        role=run.role,
        contract_id=run.contract_id,
        contract_digest=run.contract_digest,
        target=run.target,
        target_digest=run.target_digest,
        test_path=runtime / auth.test_ref,
        known_case_ids=auth.known_case_ids,
        cwd=runtime,
        artifact_root=runtime / auth.artifact_root_ref,
        timeout_seconds=run.timeout_seconds,
        run_id=run.run_id,
        contract_path=runtime / CONTRACT_REF,
    )
    rebuilt = authorize_repository_execution(
        manifest_path, workspace, request, phase=expected_phase
    )
    # RunRecord paths are portable and relative to the separately authorized snapshot.
    # The shared runner deliberately records cwd=".", never the host's process cwd.
    if rebuilt != auth or run.cwd != ".":
        raise ArtifactIntegrityError("Run contradicts its independently rebuilt authorization")
    verify_run_record(run, cwd=runtime, known_case_ids=auth.known_case_ids)
    return auth


def reproduction(buggy, fixed, case_ids):
    failed = tuple(
        case.case_id for case in buggy.case_results if case.outcome is CaseOutcome.FAILED
    )
    reasons = []
    if buggy.outcome is not RunOutcome.TEST_FAILED or buggy.pytest_exit_code != 1:
        reasons.append("buggy_did_not_produce_real_test_failure")
    if fixed.outcome is not RunOutcome.PASSED or fixed.pytest_exit_code != 0:
        reasons.append("fixed_did_not_pass")
    for name, run in (("buggy", buggy), ("fixed", fixed)):
        if tuple(case.case_id for case in run.case_results) != case_ids:
            reasons.append(name + "_case_set_mismatch")
    if not failed:
        reasons.append("no_failed_cases")
    return failed, tuple(reasons)


def verify_repository_evidence(path: str | Path, *, cwd: str | Path) -> RepositoryEvidence:
    workspace = Path(cwd).resolve(strict=True)
    evidence = _model(Path(path), RepositoryEvidence, workspace)
    manifest_path = resolve_ref(workspace, evidence.manifest_ref)
    facts = load_inputs(manifest_path, workspace)
    manifest, contract = facts["manifest"], facts["contract"]
    if (
        evidence.evidence_id != EVIDENCE_ID
        or evidence.manifest_digest != manifest["artifact_digest"]
        or evidence.assertion_head != manifest["head_sha"]
        or evidence.buggy_commit != manifest["base_sha"]
        or evidence.fixed_commit != manifest["fixed_sha"]
        or evidence.contract_ref != manifest["contract_ref"]
        or evidence.contract_digest != manifest["contract_digest"]
        or evidence.contract_id != contract.contract_id
        or evidence.buggy_workspace_ref != manifest["workspace_root_ref"] + "/b"
        or evidence.fixed_workspace_ref != manifest["workspace_root_ref"] + "/f"
        or evidence.buggy_target_digest != digest_bytes(facts["trees"]["b"][SOURCE_REF])
        or evidence.fixed_target_digest != digest_bytes(facts["trees"]["f"][SOURCE_REF])
    ):
        raise ArtifactIntegrityError("Evidence provenance differs from committed inputs")
    test = resolve_ref(workspace, evidence.test_ref).read_bytes()
    if digest_bytes(test) != evidence.test_digest or test != render_repository_test(contract):
        raise ArtifactIntegrityError("Capture test does not preserve the upstream oracle")
    for run, ref, role, target_digest in (
        (
            evidence.buggy_run,
            evidence.buggy_authorization_ref,
            RunRole.BUGGY,
            evidence.buggy_target_digest,
        ),
        (
            evidence.fixed_run,
            evidence.fixed_authorization_ref,
            RunRole.FIXED,
            evidence.fixed_target_digest,
        ),
    ):
        if run.role is not role or run.target_digest != target_digest:
            raise ArtifactIntegrityError("Evidence run role/target mismatch")
        _verify_record(run, ref, manifest_path, workspace, "capture")
    failed, reasons = reproduction(
        evidence.buggy_run, evidence.fixed_run, tuple(c.case_id for c in contract.cases)
    )
    if (
        evidence.failing_case_ids != failed
        or evidence.rejection_reasons != reasons
        or evidence.reproduced != (not reasons)
    ):
        raise ArtifactIntegrityError("Evidence reproduction claims contradict raw runs")
    return evidence


def verify_repository_guard(path: str | Path, *, cwd: str | Path) -> RepositoryGuard:
    workspace = Path(cwd).resolve(strict=True)
    guard = _model(Path(path), RepositoryGuard, workspace)
    evidence = verify_repository_evidence(workspace / guard.source_evidence_ref, cwd=workspace)
    facts = load_inputs(workspace / evidence.manifest_ref, workspace)
    manifest, contract = facts["manifest"], facts["contract"]
    cases = tuple(case for case in contract.cases if case.case_id in evidence.failing_case_ids)
    if (
        not evidence.reproduced
        or not cases
        or guard.guard_id != GUARD_ID
        or guard.source_evidence_id != evidence.evidence_id
        or guard.source_evidence_digest != evidence.artifact_digest
        or guard.contract_id != evidence.contract_id
        or guard.contract_digest != evidence.contract_digest
        or guard.source_buggy_digest != evidence.buggy_target_digest
        or guard.source_fixed_digest != evidence.fixed_target_digest
        or guard.cases != cases
        or guard.validation_workspace_ref != manifest["workspace_root_ref"] + "/h"
        or guard.validation_run.outcome is not RunOutcome.PASSED
        or guard.validation_run.target_digest != evidence.fixed_target_digest
        or guard.validation_run.role is not RunRole.REPLAY
    ):
        raise ArtifactIntegrityError("Guard differs from minimal verified Evidence")
    test_path = resolve_ref(workspace, guard.test_ref)
    if test_path != Path(path).parent / "test_guard.py":
        raise ArtifactIntegrityError("Guard test must belong to the Guard directory")
    expected = render_repository_test(contract, evidence.failing_case_ids)
    if test_path.read_bytes() != expected or digest_file(test_path) != guard.test_digest:
        raise ArtifactIntegrityError("Guard generated assertions changed")
    auth = _verify_record(
        guard.validation_run,
        guard.validation_authorization_ref,
        workspace / evidence.manifest_ref,
        workspace,
        "compile",
    )
    if auth.known_case_ids != evidence.failing_case_ids:
        raise ArtifactIntegrityError("Self-check did not execute exactly the minimal failure set")
    return guard


def verify_pilot_scope(path: Path, facts: dict, guard: RepositoryGuard) -> ExplicitPilotScope:
    scope = ExplicitPilotScope.model_validate(read_fact(path))
    manifest = facts["manifest"]
    if (
        scope.manifest_digest != manifest["artifact_digest"]
        or scope.guard_digest != guard.artifact_digest
        or scope.contract_digest != manifest["contract_digest"]
        or scope.head_commit != manifest["head_sha"]
        or scope.source_digest != digest_bytes(facts["trees"]["h"][SOURCE_REF])
        or scope.runtime_closure_digest
        != closure_digest(facts["trees"]["h"], facts["runtime_refs"])
    ):
        raise ArtifactIntegrityError("Explicit scope does not match this exact audited snapshot")
    return scope


def execute_admitted(request, facts, manifest_path, workspace, *, phase):
    authorization = authorize_repository_execution(manifest_path, workspace, request, phase=phase)
    root = workspace / facts["manifest"]["output_root_ref"]
    ref = (root / "authorizations" / f"{request.run_id}.json").relative_to(workspace).as_posix()
    write_immutable(workspace / ref, canonical_json_bytes(authorization))
    record = RepositoryDockerExecutor(authorization, manifest_path, workspace).execute(request)
    return record, ref


def make_request(facts, workspace, key, role, case_ids, *, test_ref):
    manifest, contract = facts["manifest"], facts["contract"]
    runtime = workspace / manifest["workspace_root_ref"] / key
    return PytestRunRequest(
        role=role,
        contract_id=contract.contract_id,
        contract_digest=manifest["contract_digest"],
        target=TargetRef(
            module=contract.target_module, symbol=contract.target_symbol, source_ref=SOURCE_REF
        ),
        target_digest=digest_bytes(facts["trees"][key][SOURCE_REF]),
        test_path=runtime / test_ref,
        contract_path=runtime / CONTRACT_REF,
        known_case_ids=case_ids,
        cwd=runtime,
        artifact_root=runtime / "a",
        run_id="run_" + uuid4().hex,
    )


def build_repository_guard(manifest_path: Path, workspace: Path) -> RepositoryGuard:
    facts = load_inputs(manifest_path, workspace)
    manifest, contract = facts["manifest"], facts["contract"]
    root = workspace / manifest["output_root_ref"]
    full_test = root / "generated" / "capture.py"
    write_immutable(full_test, render_repository_test(contract))
    for key in ("b", "f", "h"):
        runtime = workspace / manifest["workspace_root_ref"] / key
        if runtime.exists():
            raise ArtifactIntegrityError("Snapshot workspace exists; use a new version directory")
        for ref in facts["runtime_refs"]:
            write_immutable(runtime / ref, facts["trees"][key][ref])
        write_immutable(runtime / CONTRACT_REF, facts["trees"]["h"][CONTRACT_REF])
        write_immutable(runtime / "t/capture.py", full_test.read_bytes())
    ids = tuple(case.case_id for case in contract.cases)
    buggy, buggy_auth = execute_admitted(
        make_request(facts, workspace, "b", RunRole.BUGGY, ids, test_ref="t/capture.py"),
        facts,
        manifest_path,
        workspace,
        phase="capture",
    )
    fixed, fixed_auth = execute_admitted(
        make_request(facts, workspace, "f", RunRole.FIXED, ids, test_ref="t/capture.py"),
        facts,
        manifest_path,
        workspace,
        phase="capture",
    )
    failed, reasons = reproduction(buggy, fixed, ids)
    evidence = _seal(
        RepositoryEvidence(
            evidence_id=EVIDENCE_ID,
            created_at=datetime.now(UTC),
            manifest_ref=manifest_path.relative_to(workspace).as_posix(),
            manifest_digest=manifest["artifact_digest"],
            contract_id=contract.contract_id,
            contract_ref=manifest["contract_ref"],
            contract_digest=manifest["contract_digest"],
            test_ref=full_test.relative_to(workspace).as_posix(),
            test_digest=digest_file(full_test),
            assertion_head=manifest["head_sha"],
            buggy_commit=manifest["base_sha"],
            fixed_commit=manifest["fixed_sha"],
            buggy_workspace_ref=manifest["workspace_root_ref"] + "/b",
            fixed_workspace_ref=manifest["workspace_root_ref"] + "/f",
            buggy_target_digest=buggy.target_digest,
            fixed_target_digest=fixed.target_digest,
            buggy_run=buggy,
            fixed_run=fixed,
            buggy_authorization_ref=buggy_auth,
            fixed_authorization_ref=fixed_auth,
            failing_case_ids=failed,
            reproduced=not reasons,
            rejection_reasons=reasons,
            artifact_digest=ZERO,
        )
    )
    evidence_path = root / f"evidence/{EVIDENCE_ID}/evidence.json"
    write_immutable(evidence_path, canonical_json_bytes(evidence))
    verify_repository_evidence(evidence_path, cwd=workspace)
    if reasons:
        raise InvalidEvidenceError("Docker capture failed: " + ", ".join(reasons))
    guard_dir = root / "guards" / GUARD_ID
    test = render_repository_test(contract, failed)
    write_immutable(guard_dir / "test_guard.py", test)
    write_immutable(workspace / manifest["workspace_root_ref"] / "h/t/guard.py", test)
    validation, validation_auth = execute_admitted(
        make_request(facts, workspace, "h", RunRole.REPLAY, failed, test_ref="t/guard.py"),
        facts,
        manifest_path,
        workspace,
        phase="compile",
    )
    if validation.outcome is not RunOutcome.PASSED:
        raise GuardSelfCheckError(validation)
    guard = _seal(
        RepositoryGuard(
            guard_id=GUARD_ID,
            created_at=datetime.now(UTC),
            source_evidence_id=EVIDENCE_ID,
            source_evidence_ref=evidence_path.relative_to(workspace).as_posix(),
            source_evidence_digest=evidence.artifact_digest,
            contract_id=evidence.contract_id,
            contract_digest=evidence.contract_digest,
            source_buggy_digest=evidence.buggy_target_digest,
            source_fixed_digest=evidence.fixed_target_digest,
            cases=tuple(c for c in contract.cases if c.case_id in failed),
            test_ref=(guard_dir / "test_guard.py").relative_to(workspace).as_posix(),
            test_digest=digest_bytes(test),
            validation_workspace_ref=manifest["workspace_root_ref"] + "/h",
            validation_run=validation,
            validation_authorization_ref=validation_auth,
            artifact_digest=ZERO,
        )
    )
    write_immutable(guard_dir / "guard.json", canonical_json_bytes(guard))
    guard = verify_repository_guard(guard_dir / "guard.json", cwd=workspace)
    scope = _seal(
        ExplicitPilotScope(
            manifest_digest=manifest["artifact_digest"],
            guard_digest=guard.artifact_digest,
            contract_digest=manifest["contract_digest"],
            source_digest=digest_bytes(facts["trees"]["h"][SOURCE_REF]),
            runtime_closure_digest=closure_digest(facts["trees"]["h"], facts["runtime_refs"]),
            head_commit=manifest["head_sha"],
            artifact_digest=ZERO,
        )
    )
    write_immutable(workspace / manifest["scope_ref"], canonical_json_bytes(scope))
    from counterguard.registry import Registry

    Registry(workspace / manifest["registry_root_ref"]).add(guard_dir / "guard.json", cwd=workspace)
    return guard
