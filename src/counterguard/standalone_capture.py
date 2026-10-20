"""Reviewed generic B/F capture; target Python runs exclusively in pinned Docker."""

import base64
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import TypeAdapter

from counterguard.admission import assess_minimal_python
from counterguard.artifacts import write_immutable
from counterguard.bootstrap_binding import _new_output, verify_binding
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError, GuardReplayIntegrityError
from counterguard.execution import PytestRunRequest, _execute_with_adapter, verify_run_record
from counterguard.models import CaseOutcome, RunOutcome, RunRecord, RunRole, TargetRef
from counterguard.project_config import reject_links, repository_path
from counterguard.repository import RepositoryProblem, read_committed_files
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import (
    _CONTAINER_PREFIX,
    DockerPolicyV1,
    ExecutionInputPin,
    _AdmittedDockerProcess,
    _docker_executable,
    _require_image_identity,
)
from counterguard.standalone_contracts import (
    StandaloneContractV4,
    read_standalone_contract,
    strict_json,
)
from counterguard.standalone_models import (
    CaptureTimeout,
    EvidenceId,
    ReviewReason,
    StandaloneAuthorization,
    StandaloneCapture,
    StandaloneCaptureV2,
    StandaloneEvidence,
    StandaloneExecution,
    StandaloneGuard,
    StandaloneGuardV4,
)
from counterguard.standalone_test import (
    CONTRACT_REF,
    CONTROL,
    TEST_REF,
    render_standalone_test,
    runtime_case_id,
)

ZERO = "sha256:" + "0" * 64
ROLES = {RunRole.BUGGY: "buggy", RunRole.FIXED: "fixed"}
DIRECTORIES = {RunRole.BUGGY: "b", RunRole.FIXED: "f"}


class CaptureNotReady(ArtifactIntegrityError):
    """A genuine unsupported/unknown input, not corrupted provenance."""


def _require(value, code):
    if not value:
        raise ArtifactIntegrityError(code)


def _seal(model):
    return model.model_copy(update={"artifact_digest": digest_json_artifact(model)})


def _file(workspace: Path, ref: str, limit=4 * 1024 * 1024) -> bytes:
    repository_path(ref)
    path = workspace / ref
    reject_links(path)
    _require(
        path.resolve().is_relative_to(workspace.resolve()), "capture_reference_escapes_workspace"
    )
    _require(path.is_file() and path.stat().st_nlink == 1, "capture_reference_is_not_regular")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    _require(len(data) <= limit, "capture_file_byte_budget_exceeded")
    return data


def _ref(path: Path, workspace: Path) -> str:
    path = path if path.is_absolute() else workspace / path
    reject_links(path)
    resolved = path.resolve(strict=True)
    _require(resolved.is_relative_to(workspace), "capture_reference_escapes_workspace")
    return repository_path(resolved.relative_to(workspace).as_posix())


def _model(workspace, ref, model):
    raw = _file(workspace, ref)
    value = strict_json(raw, limit=4 * 1024 * 1024)
    _require(
        value.get("artifact_digest") == digest_json_artifact(value),
        "capture_artifact_digest_mismatch",
    )
    if model is StandaloneCapture and value.get("schema_version") == "standalone-capture.v2":
        model = StandaloneCaptureV2
    if model is StandaloneGuard and value.get("schema_version") == "guard.v4":
        model = StandaloneGuardV4
    return model.model_validate_json(raw)


def _binding(repo, path):
    value = verify_binding(repo, path)
    if value["capture_input_status"] != "review_required":
        raise CaptureNotReady("capture_inputs_require_resolution")
    contract = read_standalone_contract(canonical_json_bytes(value["contract"]))
    for ref in contract.runtime_refs:
        relative = ref.removeprefix("src/") if contract.import_root == "src" else ref
        if relative.split("/")[0] in {CONTROL, "sitecustomize.py", "usercustomize.py"}:
            raise CaptureNotReady("capture_reserved_or_startup_input")
    return value, contract


def _tree(repo, binding, role):
    revision = binding["trees"][role]["commit"]
    actual, files, pins = read_committed_files(repo, revision)
    _require(
        actual == revision
        and [pin.model_dump(mode="json") for pin in sorted(pins, key=lambda item: item.path)]
        == binding["trees"][role]["files"],
        "capture_git_tree_differs_from_binding",
    )
    # The independent generated test does not use upstream pytest configuration.
    # Target Python compatibility is still mandatory, using the existing closed
    # 3.13.16 constraint checker rather than guessing from successful AST parsing.
    contract = binding["contract"]
    assessment = assess_minimal_python(files, import_root=contract["import_root"])
    python_findings = {
        "declared_python_version_excludes_runner",
        "python_version_constraint_requires_review",
        "project_metadata_requires_review",
    }
    if any(item["code"] in python_findings for item in assessment["findings"]):
        raise CaptureNotReady("capture_python_compatibility_requires_resolution")
    return files


def _context(repo, workspace, capture_ref):
    plan = _model(workspace, capture_ref, StandaloneCapture)
    _require(capture_ref == plan.output_ref + "/capture.json", "capture_plan_layout_mismatch")
    _require(
        plan.implementation_digests == inspection_implementation_digests(),
        "capture_implementation_is_stale",
    )
    _require(
        plan.policy_digest == digest_json_artifact(DockerPolicyV1()), "capture_policy_mismatch"
    )
    _require(bool(plan.review_reason.strip()), "capture_review_reason_required")
    runner = resolve_runner(runner_id=plan.runner.runner_id, image_digest=None)
    _require(
        runner == plan.runner and runner.profile == "root-pytest8.v1",
        "capture_runner_profile_mismatch",
    )
    binding, contract = _binding(repo, workspace / plan.binding_ref)
    _require(binding["artifact_digest"] == plan.binding_digest, "capture_binding_mismatch")
    _require(
        isinstance(plan, StandaloneCaptureV2) == isinstance(contract, StandaloneContractV4),
        "capture_generator_contract_version_mismatch",
    )
    return plan, binding, contract


def _request_digest(request):
    return digest_json_artifact(
        {
            "role": request.role.value,
            "contract_id": request.contract_id,
            "contract_digest": request.contract_digest,
            "target": request.target.model_dump(),
            "target_digest": request.target_digest,
            "test_path": str(request.test_path),
            "contract_path": str(request.contract_path),
            "cwd": str(request.cwd),
            "artifact_root": str(request.artifact_root),
            "known_case_ids": request.known_case_ids,
            "timeout_seconds": request.timeout_seconds,
            "run_id": request.run_id,
        }
    )


def authorize_standalone(
    repo: Path, workspace: Path, capture_ref: str, request: PytestRunRequest
) -> StandaloneAuthorization:
    """Rebuild all authority and request/input bindings for every execution."""
    return _authorize_loaded_inputs(
        repo, workspace, request, _context(repo, workspace, capture_ref)
    )


def _authorize_loaded_inputs(repo, workspace, request, context):
    """Reuse verified facts within this call only; each execution gate reloads them."""
    plan, binding, contract = context
    _require(request.role in ROLES, "capture_requires_buggy_or_fixed_role")
    role = ROLES[request.role]
    runtime = workspace / plan.output_ref / DIRECTORIES[request.role]
    _require(
        request.cwd.resolve(strict=True) == runtime.resolve(strict=True),
        "capture_role_workspace_mismatch",
    )
    _require(request.run_id is not None, "capture_run_identity_required")
    expected_ids = tuple(runtime_case_id(case.case_id) for case in contract.cases)
    _require(
        request.target
        == TargetRef(
            module=contract.target_module,
            symbol=contract.target_symbol,
            source_ref=contract.source_ref,
        )
        and request.contract_id == contract.contract_id
        and request.contract_digest == binding["contract_digest"]
        and request.known_case_ids == expected_ids
        and request.timeout_seconds == plan.timeout_seconds
        and request.test_path == runtime / TEST_REF
        and request.contract_path == runtime / CONTRACT_REF
        and request.artifact_root == runtime / "r",
        "capture_request_exceeds_reviewed_binding",
    )
    source_pins = {pin["path"]: pin for pin in binding["trees"][role]["files"]}
    head_pins = {pin["path"]: pin for pin in binding["trees"]["head"]["files"]}
    _require(
        request.target_digest == source_pins[contract.source_ref]["content_digest"],
        "capture_target_digest_mismatch",
    )
    refs = [item["path"] for item in binding["runtime_assessments"][role]["files"]]
    origins = {ref: ref for ref in refs} | {CONTRACT_REF: binding["contract_ref"]}
    pins = []
    for ref, origin in sorted(origins.items()):
        pin = head_pins[origin] if ref == CONTRACT_REF else source_pins[origin]
        _require(
            digest_bytes(_file(runtime, ref, 1024 * 1024)) == pin["content_digest"],
            "capture_materialized_input_mismatch",
        )
        pins.append(
            ExecutionInputPin(
                path=ref, object_id=pin["object_id"], content_digest=pin["content_digest"]
            )
        )
    test = render_standalone_test(contract)
    _require(_file(runtime, TEST_REF, 1024 * 1024) == test, "capture_test_is_not_canonical")
    _tree(repo, binding, role)  # Recheck declared target Python constraints too.
    return _seal(
        StandaloneAuthorization(
            role=request.role,
            capture_digest=plan.artifact_digest,
            binding_digest=plan.binding_digest,
            target_revision=binding["trees"][role]["commit"],
            assertion_head=binding["head_commit"],
            runner_review_digest=plan.runner.artifact_digest,
            image_digest=plan.runner.image_digest,
            policy_digest=plan.policy_digest,
            implementation_digests=plan.implementation_digests,
            request_digest=_request_digest(request),
            input_pins=tuple(pins),
            input_origins=origins,
            import_root=contract.import_root,
            test_ref=TEST_REF,
            test_digest=digest_bytes(test),
            known_case_ids=expected_ids,
            case_id_map={case.case_id: runtime_case_id(case.case_id) for case in contract.cases},
            artifact_digest=ZERO,
        )
    )


@dataclass(frozen=True)
class StandaloneDockerExecutor:
    authorization: StandaloneAuthorization
    repo: Path
    workspace: Path
    capture_ref: str
    policy: DockerPolicyV1 = DockerPolicyV1()

    def verify(self, request):
        _require(self.policy == DockerPolicyV1(), "capture_executor_policy_mismatch")
        _require(
            authorize_standalone(self.repo, self.workspace, self.capture_ref, request)
            == self.authorization,
            "capture_authorization_is_stale",
        )

    def execute(self, request):
        self.verify(request)
        executable = _docker_executable()
        _require_image_identity(executable, self.authorization.image_digest, self.policy)
        record = _execute_with_adapter(request, _AdmittedDockerProcess(self, executable))
        # Save the actual record before the post-run integrity gate can reject.
        write_immutable(request.artifact_root / "record.json", canonical_json_bytes(record))
        try:
            self.verify(request)
        except (ArtifactIntegrityError, OSError, ValueError, RepositoryProblem) as error:
            raise GuardReplayIntegrityError(
                "capture_inputs_changed_after_execution", record
            ) from error
        return record


def _request(plan, binding, contract, workspace, role, *, run_id):
    runtime = workspace / plan.output_ref / DIRECTORIES[role]
    source = next(
        pin for pin in binding["trees"][ROLES[role]]["files"] if pin["path"] == contract.source_ref
    )
    return PytestRunRequest(
        role=role,
        contract_id=contract.contract_id,
        contract_digest=binding["contract_digest"],
        target=TargetRef(
            module=contract.target_module,
            symbol=contract.target_symbol,
            source_ref=contract.source_ref,
        ),
        target_digest=source["content_digest"],
        test_path=runtime / TEST_REF,
        contract_path=runtime / CONTRACT_REF,
        known_case_ids=tuple(runtime_case_id(case.case_id) for case in contract.cases),
        cwd=runtime,
        artifact_root=runtime / "r",
        run_id=run_id,
        timeout_seconds=plan.timeout_seconds,
    )


def _reproduction(buggy, fixed, contract):
    expected_ids = tuple(runtime_case_id(case.case_id) for case in contract.cases)
    reasons = []
    if buggy.outcome is not RunOutcome.TEST_FAILED or buggy.pytest_exit_code != 1:
        reasons.append("buggy_did_not_produce_real_test_failure")
    if fixed.outcome is not RunOutcome.PASSED or fixed.pytest_exit_code != 0:
        reasons.append("fixed_did_not_pass")
    for role, run in (("buggy", buggy), ("fixed", fixed)):
        if tuple(case.case_id for case in run.case_results) != expected_ids:
            reasons.append(role + "_case_set_mismatch")
    failed_runtime = {
        case.case_id for case in buggy.case_results if case.outcome is CaseOutcome.FAILED
    }
    failed = tuple(
        case.case_id for case in contract.cases if runtime_case_id(case.case_id) in failed_runtime
    )
    if not failed:
        reasons.append("no_failed_cases")
    return failed, tuple(reasons)


def capture_standalone(
    repo: Path,
    binding_path: Path,
    *,
    runner_id: str,
    evidence_id: str,
    review_reason: str,
    output: Path,
    timeout=10.0,
    cwd: Path | None = None,
):
    workspace = (cwd or Path.cwd()).resolve(strict=True)
    output = _new_output(repo, output, workspace)
    TypeAdapter(EvidenceId).validate_python(evidence_id)
    TypeAdapter(ReviewReason).validate_python(review_reason)
    timeout = TypeAdapter(CaptureTimeout).validate_python(timeout)
    if not review_reason.strip():
        raise ValueError("Capture review reason must not be blank")
    completed = []
    try:
        binding_ref = _ref(binding_path, workspace)
        binding, contract = _binding(repo, workspace / binding_ref)
        runner = resolve_runner(runner_id=runner_id, image_digest=None)
        if runner.profile != "root-pytest8.v1":
            raise CaptureNotReady("capture_runner_profile_not_supported")
        trees = {role: _tree(repo, binding, role) for role in ("buggy", "fixed", "head")}
        plan = _seal(
            (
                StandaloneCaptureV2
                if isinstance(contract, StandaloneContractV4)
                else StandaloneCapture
            )(
                evidence_id=evidence_id,
                created_at=datetime.now(UTC),
                output_ref=output.relative_to(workspace).as_posix(),
                binding_ref=binding_ref,
                binding_digest=binding["artifact_digest"],
                runner=runner,
                review_reason=review_reason,
                timeout_seconds=timeout,
                implementation_digests=inspection_implementation_digests(),
                policy_digest=digest_json_artifact(DockerPolicyV1()),
                artifact_digest=ZERO,
            )
        )
        capture_ref = plan.output_ref + "/capture.json"
        write_immutable(workspace / capture_ref, canonical_json_bytes(plan))
        test = render_standalone_test(contract)
        results = []
        for role in (RunRole.BUGGY, RunRole.FIXED):
            key = ROLES[role]
            runtime = output / DIRECTORIES[role]
            for pin in binding["runtime_assessments"][key]["files"]:
                write_immutable(runtime / pin["path"], trees[key][pin["path"]])
            write_immutable(runtime / CONTRACT_REF, trees["head"][binding["contract_ref"]])
            write_immutable(runtime / TEST_REF, test)
            request = _request(
                plan, binding, contract, workspace, role, run_id="run_" + uuid4().hex
            )
            authorization = authorize_standalone(repo, workspace, capture_ref, request)
            auth_ref = plan.output_ref + "/auth/" + key + ".json"
            write_immutable(workspace / auth_ref, canonical_json_bytes(authorization))
            run = StandaloneDockerExecutor(authorization, repo, workspace, capture_ref).execute(
                request
            )
            record_ref = (request.artifact_root / "record.json").relative_to(workspace).as_posix()
            completed.append(record_ref)
            results.append(
                StandaloneExecution(
                    workspace_ref=runtime.relative_to(workspace).as_posix(),
                    authorization_ref=auth_ref,
                    record_ref=record_ref,
                    run=run,
                )
            )
        failed, reasons = _reproduction(results[0].run, results[1].run, contract)
        evidence = _seal(
            StandaloneEvidence(
                evidence_id=evidence_id,
                created_at=datetime.now(UTC),
                capture_ref=capture_ref,
                capture_digest=plan.artifact_digest,
                binding_digest=plan.binding_digest,
                contract_id=contract.contract_id,
                contract_digest=binding["contract_digest"],
                buggy=results[0],
                fixed=results[1],
                failing_case_ids=failed,
                reproduced=not reasons,
                rejection_reasons=reasons,
                artifact_digest=ZERO,
            )
        )
        # Publish the success/result marker only after independent reconstruction
        # of both runs. Late changes to B while F runs must not leave a success
        # Evidence file behind alongside a failure marker.
        _verify_evidence_value(repo, workspace, plan.output_ref + "/evidence.json", evidence)
        raw = canonical_json_bytes(evidence)
        _require(len(raw) <= 4 * 1024 * 1024, "capture_publication_byte_budget_exceeded")
        write_immutable(output / "evidence.json", raw)
        return evidence.model_dump(mode="json")
    except (ArtifactIntegrityError, RepositoryProblem, OSError) as error:
        if isinstance(error, GuardReplayIntegrityError):
            completed.append(
                (output / DIRECTORIES[error.run.role] / "r/record.json")
                .relative_to(workspace)
                .as_posix()
            )
        value = {
            "schema_version": "standalone-capture-failure.v1",
            "evidence_id": evidence_id,
            "created_at": datetime.now(UTC).isoformat(),
            "reproduced": False,
            "exit_code": 3
            if isinstance(error, OSError)
            else 4
            if isinstance(error, CaptureNotReady)
            or isinstance(error, RepositoryProblem)
            and not error.rejected
            else 5,
            "reason_code": "docker_or_io_unavailable"
            if isinstance(error, OSError)
            else error.code
            if isinstance(error, RepositoryProblem)
            else str(error),
            "completed_record_refs": completed,
            "implementation_digests": inspection_implementation_digests(),
        }
        value["artifact_digest"] = digest_json_artifact(value)
        write_immutable(output / "capture-failure.json", canonical_json_bytes(value))
        return value


def _verify_run_envelope(run, request, plan, *, import_root=None):
    policy = DockerPolicyV1()
    if import_root is None:
        import_root = read_standalone_contract(_file(request.cwd, CONTRACT_REF)).import_root
    manifest = {
        "schema_version": "docker-runner-request.v2",
        "test_ref": TEST_REF,
        "contract_ref": CONTRACT_REF,
        "target_module": request.target.module,
        "target_symbol": request.target.symbol,
        "import_root": import_root,
        "timeout_seconds": request.timeout_seconds,
        "stdout_limit_bytes": policy.stdout_limit_bytes,
        "stderr_limit_bytes": policy.stderr_limit_bytes,
        "junit_limit_bytes": policy.junit_limit_bytes,
    }
    encoded = base64.urlsafe_b64encode(canonical_json_bytes(manifest)).decode("ascii")
    _require(
        len(run.argv) >= 5
        and re.fullmatch(re.escape(_CONTAINER_PREFIX) + r"[a-f0-9]{32}", run.argv[4]),
        "capture_container_identity_mismatch",
    )
    expected = (
        "run",
        "--rm",
        "--name",
        run.argv[4],
        "--pull=never",
        "--network=none",
        "--ipc=none",
        "--read-only",
        "--user=65532:65532",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        f"--pids-limit={policy.pids_limit}",
        f"--memory={policy.memory_bytes}",
        f"--memory-swap={policy.memory_swap_bytes}",
        f"--cpus={policy.cpus:g}",
        "--ulimit=nofile=256:256",
        "--stop-timeout=1",
        "--mount",
        "type=bind,src=<workspace>,dst=/workspace,readonly",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,nodev,size={policy.tmpfs_size_bytes},uid=65532,gid=65532,mode=700",
        "--workdir=/workspace",
        plan.runner.image_digest,
        encoded,
    )
    _require(
        run.argv[1:] == expected and Path(run.argv[0]).name.lower() in {"docker", "docker.exe"},
        "capture_run_does_not_use_closed_docker_argv",
    )
    log_root = "r/runs/" + run.run_id
    _require(
        (run.stdout_ref, run.stderr_ref, run.junit_ref)
        == (log_root + "/stdout.txt", log_root + "/stderr.txt", log_root + "/junit.xml"),
        "capture_run_log_layout_mismatch",
    )
    if run.outcome in {RunOutcome.PASSED, RunOutcome.TEST_FAILED}:
        _require(
            run.pytest_version == plan.runner.pytest_version and run.python_version == "3.13.16",
            "capture_runner_version_mismatch",
        )


def verify_standalone_evidence(repo: Path, path: Path, *, cwd: Path | None = None):
    workspace = (cwd or Path.cwd()).resolve(strict=True)
    evidence_ref = _ref(path, workspace)
    return _load_verified_evidence(repo, workspace, evidence_ref)[0]


def _load_verified_evidence(repo, workspace, evidence_ref):
    evidence = _model(workspace, evidence_ref, StandaloneEvidence)
    context = _context(repo, workspace, evidence.capture_ref)
    return _verify_evidence_value(repo, workspace, evidence_ref, evidence, context=context), context


def _verify_evidence_value(repo, workspace, evidence_ref, evidence, *, context=None):
    context = context or _context(repo, workspace, evidence.capture_ref)
    plan, binding, contract = context
    _require(
        evidence_ref == plan.output_ref + "/evidence.json"
        and evidence.capture_digest == plan.artifact_digest
        and evidence.evidence_id == plan.evidence_id
        and evidence.binding_digest == binding["artifact_digest"]
        and evidence.contract_id == contract.contract_id
        and evidence.contract_digest == binding["contract_digest"],
        "capture_evidence_provenance_mismatch",
    )
    for item, role in ((evidence.buggy, RunRole.BUGGY), (evidence.fixed, RunRole.FIXED)):
        runtime_ref = plan.output_ref + "/" + DIRECTORIES[role]
        _require(
            item.workspace_ref == runtime_ref
            and item.authorization_ref == plan.output_ref + "/auth/" + ROLES[role] + ".json"
            and item.record_ref == runtime_ref + "/r/record.json",
            "capture_evidence_layout_mismatch",
        )
        auth = _model(workspace, item.authorization_ref, StandaloneAuthorization)
        request = _request(plan, binding, contract, workspace, role, run_id=item.run.run_id)
        _require(
            auth == _authorize_loaded_inputs(repo, workspace, request, context),
            "capture_record_authorization_mismatch",
        )
        stored = RunRecord.model_validate_json(_file(workspace, item.record_ref))
        _require(
            item.run == stored
            and stored.role is role
            and stored.target == request.target
            and stored.target_digest == request.target_digest
            and stored.contract_id == contract.contract_id
            and stored.contract_digest == binding["contract_digest"]
            and stored.timeout_seconds == plan.timeout_seconds
            and stored.cwd == "."
            and stored.pytest_version in {plan.runner.pytest_version, "unavailable"},
            "capture_record_identity_mismatch",
        )
        _verify_run_envelope(stored, request, plan)
        for ref in (stored.stdout_ref, stored.stderr_ref, stored.junit_ref):
            _file(workspace / runtime_ref, ref)
        verify_run_record(stored, cwd=workspace / runtime_ref, known_case_ids=auth.known_case_ids)
    failed, reasons = _reproduction(evidence.buggy.run, evidence.fixed.run, contract)
    _require(
        evidence.failing_case_ids == failed
        and evidence.rejection_reasons == reasons
        and evidence.reproduced == (not reasons),
        "capture_reproduction_claims_mismatch",
    )
    return evidence


def standalone_capture_exit_code(value):
    if value["schema_version"] == "standalone-capture-failure.v1":
        return value["exit_code"]
    if value["reproduced"]:
        return 0
    domain = {RunOutcome.PASSED.value, RunOutcome.TEST_FAILED.value}
    return 1 if all(value[role]["run"]["outcome"] in domain for role in ("buggy", "fixed")) else 3
