"""Digest-bound admission and a fail-closed Docker pytest backend."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import subprocess
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from counterguard.change_analysis import (
    InspectionReport,
    verify_inspection_report,
)
from counterguard.digests import (
    canonical_json_bytes,
    digest_bytes,
    digest_file,
    digest_json_artifact,
)
from counterguard.errors import ArtifactIntegrityError, GuardReplayIntegrityError
from counterguard.execution import PytestRunRequest
from counterguard.models import (
    ArtifactRef,
    Digest,
    FrozenModel,
    NonEmptyText,
    RunOutcome,
    RunRecord,
    RunRole,
    TargetRef,
)
from counterguard.project_config import (
    Identifier,
    RepositoryPath,
    load_project_config,
)
from counterguard.runners.base import PreparedRun, RawExecution

_OBJECT_ID = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$", strict=True)]
_CONTAINER_PREFIX = "counterguard-w3b-"


class DockerPolicyV1(FrozenModel):
    """Closed W3-B isolation profile; callers cannot weaken individual controls."""

    schema_version: Literal["docker-policy.v1"] = "docker-policy.v1"
    network_mode: Literal["none"] = "none"
    workspace_mode: Literal["read_only"] = "read_only"
    root_filesystem: Literal["read_only"] = "read_only"
    run_as: Literal["65532:65532"] = "65532:65532"
    cap_drop: Literal["ALL"] = "ALL"
    no_new_privileges: Literal[True] = True
    ipc_mode: Literal["none"] = "none"
    pids_limit: Literal[64] = 64
    memory_bytes: Literal[268435456] = 268435456
    memory_swap_bytes: Literal[268435456] = 268435456
    cpus: Literal[1.0] = 1.0
    tmpfs_size_bytes: Literal[67108864] = 67108864
    stdout_limit_bytes: Literal[1048576] = 1048576
    stderr_limit_bytes: Literal[1048576] = 1048576
    junit_limit_bytes: Literal[4194304] = 4194304
    transport_stdout_limit_bytes: Literal[8388608] = 8388608
    transport_stderr_limit_bytes: Literal[65536] = 65536
    startup_grace_seconds: Literal[5.0] = 5.0
    cleanup_timeout_seconds: Literal[5.0] = 5.0
    max_test_timeout_seconds: Literal[30.0] = 30.0


class ExecutionInputPin(FrozenModel):
    path: RepositoryPath
    object_id: _OBJECT_ID
    content_digest: Digest


class DockerExecutionAuthorization(FrozenModel):
    """Audit record produced by the trusted admission gate, never by target code."""

    schema_version: Literal["docker-execution-authorization.v1"] = (
        "docker-execution-authorization.v1"
    )
    backend: Literal["docker"] = "docker"
    inspection_digest: Digest
    config_digest: Digest
    project_id: Identifier
    head_commit: _OBJECT_ID
    target_id: Identifier
    guard_id: NonEmptyText
    input_pins: Annotated[tuple[ExecutionInputPin, ...], Field(min_length=2)]
    image_digest: Digest
    policy_digest: Digest
    role: Literal[RunRole.REPLAY] = RunRole.REPLAY
    contract_id: NonEmptyText
    contract_digest: Digest
    contract_ref: ArtifactRef
    target: TargetRef
    target_digest: Digest
    test_ref: ArtifactRef
    test_digest: Digest
    known_case_ids: Annotated[tuple[NonEmptyText, ...], Field(min_length=1)]
    timeout_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    artifact_root_ref: ArtifactRef
    requested_run_id: str | None
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent_bindings(self) -> Self:
        paths = [pin.path for pin in self.input_pins]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("Execution input pins must be unique and sorted")
        if self.target.source_ref not in paths or self.contract_ref not in paths:
            raise ValueError("Execution authorization must pin source and contract inputs")
        if len(self.known_case_ids) != len(set(self.known_case_ids)):
            raise ValueError("Execution authorization case IDs must be unique")
        if self.policy_digest != digest_json_artifact(DockerPolicyV1()):
            raise ValueError("Execution authorization does not use the closed W3-B policy")
        return self


def authorize_docker_execution(
    report: InspectionReport,
    *,
    config_path: str | Path,
    target_id: str,
    request: PytestRunRequest,
    image_digest: Digest,
    policy: DockerPolicyV1 | None = None,
    require_current_implementation: bool = True,
) -> DockerExecutionAuthorization:
    """Admit one exact replay request after independently rebuilding all bindings."""
    verify_inspection_report(
        report, require_current_implementation=require_current_implementation
    )
    if report.status != "ready" or report.reason_codes or report.unmapped_paths:
        raise ValueError("Docker execution requires a ready inspection without uncertainty")
    if report.head_commit is None:
        raise ValueError("Docker execution requires an exact head commit")
    if request.role is not RunRole.REPLAY:
        raise ValueError("W3-B authorizes replay requests only")

    config, config_digest = load_project_config(config_path)
    if config.schema_version != "project-config.v1":
        raise ValueError("W3-B v1 requires its original project-config.v1 profile")
    if config_digest != report.config_digest or config.project_id != report.project_id:
        raise ValueError("Project configuration does not match the inspection report")
    mappings = [item for item in config.targets if item.target_id == target_id]
    impacts = [item for item in report.targets if item.target_id == target_id]
    if len(mappings) != 1 or len(impacts) != 1:
        raise ValueError("Execution target is not uniquely present in config and inspection")
    mapping, impact = mappings[0], impacts[0]
    if impact.impact != "affected" or impact.reason_codes:
        raise ValueError("Docker execution requires an affected target without uncertainty")
    if (
        impact.guard_id != mapping.guard_id
        or impact.source_ref != mapping.source_ref
        or impact.symbol != mapping.symbol
    ):
        raise ValueError("Inspection target does not match the project mapping")
    if (
        request.target.source_ref != mapping.source_ref
        or mapping.module is None
        or request.target.module != mapping.module
        or request.target.symbol != mapping.symbol
    ):
        raise ValueError("Docker replay requires an explicit matching module and target mapping")

    workspace = request.cwd.resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("Replay workspace must be a directory")
    contract_ref = _file_ref(request.contract_path, workspace, "contract_path")
    test_ref = _file_ref(request.test_path, workspace, "test_path")
    artifact_root_ref = _directory_ref(request.artifact_root, workspace, "artifact_root")
    if contract_ref != mapping.contract_ref or not test_ref.endswith(".py"):
        raise ValueError("Replay contract or test path does not match the admitted inputs")

    relevant_head_pins = [
        pin
        for pin in report.files
        if pin.revision == "head" and pin.path in mapping.input_refs()
    ]
    head_pins = {
        pin.path: pin
        for pin in relevant_head_pins
    }
    if (
        len(relevant_head_pins) != len(head_pins)
        or set(head_pins) != set(mapping.input_refs())
    ):
        raise ValueError("Inspection report does not pin every declared head input")
    input_pins = []
    for ref in sorted(mapping.input_refs()):
        path = _resolve_workspace_file(workspace, ref)
        pin = head_pins[ref]
        if digest_file(path) != pin.content_digest:
            raise ValueError("Materialized workspace differs from the inspected head commit")
        input_pins.append(
            ExecutionInputPin(
                path=ref,
                object_id=pin.object_id,
                content_digest=pin.content_digest,
            )
        )
    source_pin = head_pins[mapping.source_ref]
    contract_pin = head_pins[mapping.contract_ref]
    if (
        request.target_digest != source_pin.content_digest
        or request.contract_digest != contract_pin.content_digest
    ):
        raise ValueError("Replay request digests differ from inspected source or contract")

    effective_policy = policy or DockerPolicyV1()
    if request.timeout_seconds > effective_policy.max_test_timeout_seconds:
        raise ValueError("Docker replay timeout exceeds the closed W3-B policy")
    authorization = DockerExecutionAuthorization(
        inspection_digest=report.artifact_digest,
        config_digest=config_digest,
        project_id=config.project_id,
        head_commit=report.head_commit,
        target_id=mapping.target_id,
        guard_id=mapping.guard_id,
        input_pins=tuple(input_pins),
        image_digest=image_digest,
        policy_digest=digest_json_artifact(effective_policy),
        role=request.role,
        contract_id=request.contract_id,
        contract_digest=request.contract_digest,
        contract_ref=contract_ref,
        target=request.target,
        target_digest=request.target_digest,
        test_ref=test_ref,
        test_digest=digest_file(_resolve_workspace_file(workspace, test_ref)),
        known_case_ids=request.known_case_ids,
        timeout_seconds=request.timeout_seconds,
        artifact_root_ref=artifact_root_ref,
        requested_run_id=request.run_id,
        artifact_digest="sha256:" + "0" * 64,
    )
    return authorization.model_copy(
        update={"artifact_digest": digest_json_artifact(authorization)}
    )


def verify_docker_authorization(
    authorization: DockerExecutionAuthorization,
    *,
    report: InspectionReport,
    config_path: str | Path,
    request: PytestRunRequest,
    policy: DockerPolicyV1 | None = None,
    require_current_implementation: bool = True,
) -> DockerExecutionAuthorization:
    """Rebuild admission from trusted inputs; a recomputed self-digest is insufficient."""
    if digest_json_artifact(authorization) != authorization.artifact_digest:
        raise ValueError("Docker execution authorization digest mismatch")
    try:
        expected = authorize_docker_execution(
            report,
            config_path=config_path,
            target_id=authorization.target_id,
            request=request,
            image_digest=authorization.image_digest,
            policy=policy,
            require_current_implementation=require_current_implementation,
        )
    except (OSError, ValueError) as error:
        raise ValueError("Docker authorization no longer matches request or workspace") from error
    if expected != authorization:
        raise ValueError("Docker authorization no longer matches request or workspace")
    return authorization


@dataclass(frozen=True, slots=True)
class DockerExecutor:
    """Run one admitted request under the fixed W3-B Docker isolation profile."""

    authorization: DockerExecutionAuthorization
    inspection_report: InspectionReport
    config_path: Path
    policy: DockerPolicyV1 = DockerPolicyV1()
    docker_executable: str | None = None
    require_current_implementation: bool = True

    def execute(self, request: PytestRunRequest) -> RunRecord:
        verify_docker_authorization(
            self.authorization,
            report=self.inspection_report,
            config_path=self.config_path,
            request=request,
            policy=self.policy,
            require_current_implementation=self.require_current_implementation,
        )
        executable = self.docker_executable or _docker_executable()
        _require_image_identity(executable, self.authorization.image_digest, self.policy)
        from counterguard.execution import _execute_with_adapter

        adapter = _AdmittedDockerProcess(self, executable)
        record = _execute_with_adapter(request, adapter)
        try:
            verify_docker_authorization(
                self.authorization,
                report=self.inspection_report,
                config_path=self.config_path,
                request=request,
                policy=self.policy,
                require_current_implementation=self.require_current_implementation,
            )
        except (ArtifactIntegrityError, OSError, ValueError) as error:
            raise GuardReplayIntegrityError(
                "Docker replay inputs changed during execution", record
            ) from error
        return record


@dataclass(frozen=True, slots=True)
class _AdmittedDockerProcess:
    executor: DockerExecutor
    executable: str

    def execute_process(
        self, request: PytestRunRequest, prepared: PreparedRun
    ) -> RawExecution:
        policy = self.executor.policy
        sandbox = _materialize_sandbox_inputs(
            prepared.cwd,
            prepared.run_dir / "sandbox-input",
            self.executor.authorization,
        )
        if any(character in str(sandbox) for character in (",", "\n", "\r")):
            raise ValueError("Docker workspace path contains unsupported mount characters")
        manifest = {
            "schema_version": "docker-runner-request.v1",
            "test_ref": prepared.test_ref,
            "contract_ref": prepared.contract_ref,
            "target_module": request.target.module,
            "target_symbol": request.target.symbol,
            "timeout_seconds": request.timeout_seconds,
            "stdout_limit_bytes": policy.stdout_limit_bytes,
            "stderr_limit_bytes": policy.stderr_limit_bytes,
            "junit_limit_bytes": policy.junit_limit_bytes,
        }
        if hasattr(self.executor.authorization, "import_root"):
            manifest.update(
                schema_version="docker-runner-request.v2",
                import_root=self.executor.authorization.import_root,
            )
        encoded_manifest = base64.urlsafe_b64encode(canonical_json_bytes(manifest)).decode("ascii")
        container_name = _CONTAINER_PREFIX + uuid.uuid4().hex
        mount = f"type=bind,src={sandbox},dst=/workspace,readonly"
        argv = (
            self.executable,
            "run",
            "--rm",
            "--name",
            container_name,
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
            mount,
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,"
            f"size={policy.tmpfs_size_bytes},uid=65532,gid=65532,mode=700",
            "--workdir=/workspace",
            self.executor.authorization.image_digest,
            encoded_manifest,
        )
        display_argv = tuple(
            "type=bind,src=<workspace>,dst=/workspace,readonly" if item == mount else item
            for item in argv
        )
        result = _run_bounded(
            argv,
            cwd=prepared.cwd,
            timeout=request.timeout_seconds + policy.startup_grace_seconds,
            stdout_limit=policy.transport_stdout_limit_bytes,
            stderr_limit=policy.transport_stderr_limit_bytes,
        )
        if result.timed_out or result.overflowed:
            _remove_container(self.executable, container_name, policy.cleanup_timeout_seconds)
            detail = "docker runner exceeded its host deadline"
            if result.overflowed:
                detail = "docker runner exceeded its transport output limit"
            return _transport_failure(
                display_argv,
                detail,
                timeout=result.timed_out,
            )
        if result.returncode != 0:
            _remove_container(self.executable, container_name, policy.cleanup_timeout_seconds)
            return _transport_failure(display_argv, "docker runner process failed")
        try:
            envelope = _decode_envelope(result.stdout, policy)
        except ValueError as error:
            return _transport_failure(display_argv, f"invalid docker runner envelope: {error}")

        error_code = envelope["error_code"]
        terminal = None
        detail = None
        exit_code = envelope["pytest_exit_code"]
        if envelope["timed_out"]:
            terminal = RunOutcome.TIMEOUT
            exit_code = None
            detail = f"pytest exceeded timeout of {request.timeout_seconds:g} seconds"
        elif error_code is not None:
            terminal = RunOutcome.PROCESS_ERROR
            exit_code = 120
            detail = str(error_code)
        return RawExecution(
            argv=display_argv,
            stdout=envelope["stdout"],
            stderr=envelope["stderr"],
            junit=envelope["junit"],
            junit_produced=envelope["junit_produced"],
            pytest_exit_code=exit_code,
            python_version=envelope["python_version"],
            pytest_version=envelope["pytest_version"],
            terminal_outcome=terminal,
            error_detail=detail,
        )


@dataclass(frozen=True, slots=True)
class _BoundedProcessResult:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    overflowed: bool


def _run_bounded(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    timeout: float,
    stdout_limit: int,
    stderr_limit: int,
) -> _BoundedProcessResult:
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except OSError:
        return _BoundedProcessResult(None, b"", b"", False, False)

    def consume(stream, index: int, maximum: int) -> None:
        while chunk := stream.read(8192):
            available = maximum - len(buffers[index])
            if available <= 0 or len(chunk) > available:
                if available > 0:
                    buffers[index].extend(chunk[:available])
                overflow.set()
                process.kill()
                return
            buffers[index].extend(chunk)

    threads = [
        threading.Thread(target=consume, args=(process.stdout, 0, stdout_limit), daemon=True),
        threading.Thread(target=consume, args=(process.stderr, 1, stderr_limit), daemon=True),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait(timeout=5)
    finally:
        for thread in threads:
            thread.join(timeout=1)
    return _BoundedProcessResult(
        process.returncode,
        bytes(buffers[0]),
        bytes(buffers[1]),
        timed_out,
        overflow.is_set(),
    )


def _decode_envelope(data: bytes, policy: DockerPolicyV1) -> dict[str, object]:
    if len(data) > policy.transport_stdout_limit_bytes:
        raise ValueError("transport output exceeds policy")
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("response is not one JSON document") from error
    expected_keys = {
        "schema_version",
        "pytest_exit_code",
        "timed_out",
        "error_code",
        "junit_produced",
        "stdout_b64",
        "stderr_b64",
        "junit_b64",
        "python_version",
        "pytest_version",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("response fields differ from docker-runner-response.v1")
    if payload["schema_version"] != "docker-runner-response.v1":
        raise ValueError("response schema is unsupported")
    if type(payload["timed_out"]) is not bool or type(payload["junit_produced"]) is not bool:
        raise ValueError("response boolean fields are invalid")
    exit_code = payload["pytest_exit_code"]
    if exit_code is not None and type(exit_code) is not int:
        raise ValueError("pytest exit code is invalid")
    error_code = payload["error_code"]
    if error_code is not None and (
        not isinstance(error_code, str) or len(error_code) > 128
    ):
        raise ValueError("runner error code is invalid")
    versions = (payload["python_version"], payload["pytest_version"])
    if any(not isinstance(value, str) or not value or len(value) > 128 for value in versions):
        raise ValueError("runner versions are invalid")

    decoded = {}
    for key, limit in (
        ("stdout", policy.stdout_limit_bytes),
        ("stderr", policy.stderr_limit_bytes),
        ("junit", policy.junit_limit_bytes),
    ):
        encoded = payload[key + "_b64"]
        if not isinstance(encoded, str):
            raise ValueError(f"{key} payload is invalid")
        try:
            value = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError(f"{key} payload is not canonical base64") from error
        if len(value) > limit:
            raise ValueError(f"{key} payload exceeds policy")
        decoded[key] = value
    return {
        **payload,
        **decoded,
    }


def _transport_failure(
    argv: tuple[str, ...], detail: str, *, timeout: bool = False
) -> RawExecution:
    return RawExecution(
        argv=argv,
        stdout=b"",
        stderr=(detail + "\n").encode("utf-8"),
        junit=b"",
        junit_produced=False,
        pytest_exit_code=None,
        python_version="unavailable",
        pytest_version="unavailable",
        terminal_outcome=RunOutcome.TIMEOUT if timeout else RunOutcome.LAUNCH_ERROR,
        error_detail=detail,
    )


def _require_image_identity(executable: str, image_digest: Digest, policy: DockerPolicyV1) -> None:
    result = _run_bounded(
        (executable, "image", "inspect", "--format={{.Id}}", image_digest),
        cwd=Path.cwd(),
        timeout=policy.cleanup_timeout_seconds,
        stdout_limit=256,
        stderr_limit=policy.transport_stderr_limit_bytes,
    )
    identity = result.stdout.decode("ascii", errors="ignore").strip()
    if (
        result.returncode != 0
        or result.timed_out
        or result.overflowed
        or identity != image_digest
    ):
        raise OSError("Pinned Docker runner image is unavailable or has a different identity")


def _remove_container(executable: str, name: str, timeout: float) -> None:
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run(
            (executable, "rm", "-f", name),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            shell=False,
        )


def _docker_executable() -> str:
    name = "docker.exe" if os.name == "nt" else "docker"
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory or not Path(directory).is_absolute():
            continue
        candidate = Path(directory) / name
        if candidate.is_file():
            return str(candidate.resolve())
    raise OSError("Docker CLI is unavailable; unknown repository execution remains disabled")


def _resolve_workspace_file(workspace: Path, ref: str) -> Path:
    path = (workspace / ref).resolve(strict=True)
    if not path.is_relative_to(workspace) or not path.is_file():
        raise ValueError("Execution input must be a regular file below the workspace")
    return path


def _materialize_sandbox_inputs(
    workspace: Path,
    destination: Path,
    authorization: DockerExecutionAuthorization,
) -> Path:
    """Copy only admitted bytes; undeclared repository files never enter the mount."""
    expected = {pin.path: pin.content_digest for pin in authorization.input_pins}
    previous = expected.setdefault(authorization.test_ref, authorization.test_digest)
    if previous != authorization.test_digest:
        raise ValueError("Docker test path conflicts with an admitted repository input")
    destination.mkdir(parents=True, exist_ok=False)
    for ref, expected_digest in sorted(expected.items()):
        data = _resolve_workspace_file(workspace, ref).read_bytes()
        if digest_bytes(data) != expected_digest:
            raise ValueError("Docker input changed while materializing the isolated workspace")
        output = destination / ref
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
    return destination


def _file_ref(path: Path | None, workspace: Path, label: str) -> str:
    if path is None:
        raise ValueError(f"{label} is required for Docker execution")
    candidate = path if path.is_absolute() else workspace / path
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(workspace) or not resolved.is_file():
        raise ValueError(f"{label} must be a file below the workspace")
    return resolved.relative_to(workspace).as_posix()


def _directory_ref(path: Path, workspace: Path, label: str) -> str:
    candidate = path if path.is_absolute() else workspace / path
    resolved = candidate.resolve()
    if not resolved.is_relative_to(workspace) or resolved == workspace:
        raise ValueError(f"{label} must name a child directory below the workspace")
    return resolved.relative_to(workspace).as_posix()
