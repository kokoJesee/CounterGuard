"""Historical capture admission v2; existing replay authorization v1 is unchanged."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from evidenceguard.digests import digest_bytes, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError, GuardReplayIntegrityError
from evidenceguard.execution import PytestRunRequest, _execute_with_adapter
from evidenceguard.models import ArtifactRef, Digest, FrozenModel, RunRecord, RunRole, TargetRef
from evidenceguard.pilot_inputs import ZERO, load_inputs, repository_path, resolve_ref
from evidenceguard.repository_contracts import (
    CONTRACT_REF,
    EVIDENCE_ID,
    SOURCE_REF,
    render_repository_test,
)
from evidenceguard.runners.docker import (
    DockerPolicyV1,
    ExecutionInputPin,
    _AdmittedDockerProcess,
    _directory_ref,
    _docker_executable,
    _file_ref,
    _require_image_identity,
)


class RepositoryAuthorization(FrozenModel):
    schema_version: Literal["docker-execution-authorization.v2"] = (
        "docker-execution-authorization.v2"
    )
    backend: Literal["docker"] = "docker"
    phase: Literal["capture", "compile", "replay"]
    role: RunRole
    assertion_head: str
    target_revision: str
    manifest_digest: Digest
    inspection_digest: Digest
    implementation_digests: dict[str, Digest]
    request_digest: Digest
    workspace_ref: ArtifactRef
    input_pins: tuple[ExecutionInputPin, ...]
    image_digest: Digest
    policy_digest: Digest
    import_root: Literal["src"] = "src"
    test_ref: ArtifactRef
    test_digest: Digest
    known_case_ids: tuple[str, ...]
    artifact_root_ref: ArtifactRef
    artifact_digest: Digest


def _request_digest(request: PytestRunRequest) -> str:
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


def authorize_repository_execution(
    manifest_path: Path,
    workspace: Path,
    request: PytestRunRequest,
    *,
    phase: Literal["capture", "compile", "replay"],
) -> RepositoryAuthorization:
    """Reconstruct every pin before allowing a request; YAML has no enable switch."""
    facts = load_inputs(manifest_path, workspace)
    manifest, contract = facts["manifest"], facts["contract"]
    if phase == "capture":
        if request.role not in {RunRole.BUGGY, RunRole.FIXED}:
            raise ArtifactIntegrityError("Capture requires buggy/fixed roles")
        key = "b" if request.role is RunRole.BUGGY else "f"
        case_ids = tuple(case.case_id for case in contract.cases)
    else:
        if phase not in {"compile", "replay"} or request.role is not RunRole.REPLAY:
            raise ArtifactIntegrityError("Head self-check/replay requires replay role")
        from evidenceguard.repository_guard import verify_repository_evidence

        evidence_ref = manifest["output_root_ref"] + f"/evidence/{EVIDENCE_ID}/evidence.json"
        evidence = verify_repository_evidence(workspace / evidence_ref, cwd=workspace)
        if not evidence.reproduced:
            raise ArtifactIntegrityError("Cannot compile unreproduced Evidence")
        key, case_ids = "h", evidence.failing_case_ids
        if phase == "replay":
            from evidenceguard.registry import Registry
            from evidenceguard.repository_guard import verify_pilot_scope

            entry = Registry(workspace / manifest["registry_root_ref"]).resolve_for_execution(
                facts["config"].targets[0].guard_id
            )
            verify_pilot_scope(workspace / manifest["scope_ref"], facts, entry.guard)
    runtime = workspace / repository_path(manifest["workspace_root_ref"]) / key
    if request.cwd.resolve(strict=True) != runtime.resolve(strict=True):
        raise ArtifactIntegrityError("Execution workspace/role mismatch")
    reject_request = (
        request.target
        != TargetRef(
            module=contract.target_module, symbol=contract.target_symbol, source_ref=SOURCE_REF
        )
        or request.target_digest != digest_bytes(facts["trees"][key][SOURCE_REF])
        or request.contract_digest != manifest["contract_digest"]
        or request.contract_id != contract.contract_id
        or request.known_case_ids != case_ids
        or not 0 < request.timeout_seconds <= DockerPolicyV1().max_test_timeout_seconds
    )
    if reject_request:
        raise ArtifactIntegrityError("Request exceeds reviewed contract/target/case binding")
    contract_ref = _file_ref(request.contract_path, runtime, "contract")
    test_ref = _file_ref(request.test_path, runtime, "test")
    if (
        contract_ref != CONTRACT_REF
        or (runtime / contract_ref).read_bytes() != facts["trees"]["h"][CONTRACT_REF]
    ):
        raise ArtifactIntegrityError("Execution contract must be exact assertion-head bytes")
    if (runtime / test_ref).read_bytes() != render_repository_test(contract, case_ids):
        raise ArtifactIntegrityError("Test must be canonical generated assertions for exact cases")
    source_pins = {pin.path: pin for pin in facts["pins"][key]}
    head_pins = {pin.path: pin for pin in facts["pins"]["h"]}
    pins = []
    for ref in sorted((*facts["runtime_refs"], CONTRACT_REF)):
        pin = head_pins[ref] if ref == CONTRACT_REF else source_pins[ref]
        if digest_bytes(resolve_ref(runtime, ref).read_bytes()) != pin.content_digest:
            raise ArtifactIntegrityError("Materialized input differs from committed origin")
        pins.append(
            ExecutionInputPin(path=ref, object_id=pin.object_id, content_digest=pin.content_digest)
        )
    payload = dict(
        phase=phase,
        role=request.role,
        assertion_head=manifest["head_sha"],
        target_revision={
            "b": manifest["base_sha"],
            "f": manifest["fixed_sha"],
            "h": manifest["head_sha"],
        }[key],
        manifest_digest=manifest["artifact_digest"],
        inspection_digest=facts["inspection"].artifact_digest,
        implementation_digests=facts["implementation_digests"],
        request_digest=_request_digest(request),
        workspace_ref=runtime.relative_to(workspace).as_posix(),
        input_pins=tuple(pins),
        image_digest=manifest["image_id"],
        policy_digest=digest_json_artifact(DockerPolicyV1()),
        test_ref=test_ref,
        test_digest=digest_bytes((runtime / test_ref).read_bytes()),
        known_case_ids=case_ids,
        artifact_root_ref=_directory_ref(request.artifact_root, runtime, "artifact root"),
    )
    authorization = RepositoryAuthorization(**payload, artifact_digest=ZERO)
    return authorization.model_copy(update={"artifact_digest": digest_json_artifact(authorization)})


@dataclass(frozen=True)
class RepositoryDockerExecutor:
    authorization: RepositoryAuthorization
    manifest_path: Path
    workspace: Path
    policy: DockerPolicyV1 = DockerPolicyV1()

    def verify(self, request: PytestRunRequest) -> None:
        rebuilt = authorize_repository_execution(
            self.manifest_path, self.workspace, request, phase=self.authorization.phase
        )
        if rebuilt != self.authorization:
            raise ArtifactIntegrityError("Repository authorization is stale or request changed")

    def execute(self, request: PytestRunRequest) -> RunRecord:
        self.verify(request)
        executable = _docker_executable()
        _require_image_identity(executable, self.authorization.image_digest, self.policy)
        record = _execute_with_adapter(request, _AdmittedDockerProcess(self, executable))
        try:
            self.verify(request)
        except (ArtifactIntegrityError, OSError, ValueError) as error:
            raise GuardReplayIntegrityError(
                "Repository inputs changed during Docker execution", record
            ) from error
        return record
