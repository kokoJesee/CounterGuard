"""Reviewed validators replay in a fresh runtime; historical capture authorization is unchanged."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspect_repository, inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError, GuardReplayIntegrityError
from counterguard.execution import PytestRunRequest, _execute_with_adapter, verify_run_record
from counterguard.models import ArtifactRef, Digest, FrozenModel, RunRole, TargetRef
from counterguard.pilot_inputs import ZERO, load_inputs, resolve_ref
from counterguard.registry import Registry
from counterguard.repository_contracts import CONTRACT_REF, SOURCE_REF, render_repository_test
from counterguard.repository_guard import verify_pilot_scope
from counterguard.repository_models import RepositoryEvidence, RepositoryGuard
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import (
    DockerPolicyV1,
    ExecutionInputPin,
    _AdmittedDockerProcess,
    _docker_executable,
    _file_ref,
    _require_image_identity,
)
from counterguard.runners.repository import _request_digest


class UnsupportedRepositoryScope(ValueError):
    """A valid source chain is not an authorization for a different project/head/profile."""


class ReviewedReplayAuthorization(FrozenModel):
    schema_version: Literal["docker-execution-authorization.v3"] = (
        "docker-execution-authorization.v3"
    )
    backend: Literal["docker"] = "docker"
    import_root: Literal["src"] = "src"
    image_digest: Digest
    runner_review_digest: Digest
    policy_digest: Digest
    manifest_digest: Digest
    inspection_digest: Digest
    guard_digest: Digest
    evidence_digest: Digest
    scope_digest: Digest
    registry_entry_digest: Digest
    registry_event_tip_digest: Digest
    head_commit: str
    implementation_digests: dict[str, Digest]
    request_digest: Digest
    input_pins: tuple[ExecutionInputPin, ...]
    test_ref: ArtifactRef
    test_digest: Digest
    artifact_digest: Digest


def _admission(request, guard_id):
    registry = Registry(request.registry)
    verified = registry.resolve_for_verification(guard_id)
    if not isinstance(verified.guard, RepositoryGuard) or not isinstance(
        verified.evidence, RepositoryEvidence
    ):
        raise UnsupportedRepositoryScope("Not a reviewed repository Guard")
    source_workspace = Path(verified.entry.source_workspace).resolve(strict=True)
    facts = load_inputs(source_workspace / verified.evidence.manifest_ref, source_workspace)
    manifest = facts["manifest"]
    inspection = inspect_repository(request.repo, request.base, request.head, request.config)
    review = resolve_runner(runner_id=None, image_digest=request.image_digest)
    if (
        request.repo.resolve(strict=True)
        != (source_workspace / manifest["repository_ref"]).resolve(strict=True)
        or inspection != facts["inspection"]
        or review.profile != "validators-src-pytest9.v1"
        or review.image_digest != manifest["image_id"]
        or review.lock_digest != manifest["runner_lock_digest"]
    ):
        raise UnsupportedRepositoryScope(
            "Repository, commits, configuration or runner profile is outside reviewed scope"
        )
    scope = verify_pilot_scope(source_workspace / manifest["scope_ref"], facts, verified.guard)
    return (
        verified,
        facts,
        scope,
        inspection,
        review,
        {"events": [{"artifact_digest": verified.event_tip_digest}]},
    )


def authorize_reviewed_replay(request, guard_id, run_request):
    verified, facts, scope, inspection, review, item = _admission(request, guard_id)
    guard, contract = verified.guard, facts["contract"]
    runtime = run_request.cwd.resolve(strict=True)
    output = request.output if request.output.is_absolute() else request.cwd / request.output
    expected_runtime = (output / "work" / facts["config"].targets[0].target_id).resolve(strict=True)
    if runtime != expected_runtime:
        raise ArtifactIntegrityError(
            "Repository replay runtime is outside the new report namespace"
        )
    case_ids = tuple(case.case_id for case in guard.cases)
    if (
        run_request.role is not RunRole.REPLAY
        or run_request.target
        != TargetRef(
            module=contract.target_module, symbol=contract.target_symbol, source_ref=SOURCE_REF
        )
        or run_request.target_digest != guard.source_fixed_digest
        or run_request.contract_id != guard.contract_id
        or run_request.contract_digest != guard.contract_digest
        or run_request.known_case_ids != case_ids
        or not 0 < run_request.timeout_seconds <= DockerPolicyV1().max_test_timeout_seconds
        or run_request.artifact_root.resolve() != runtime / "a"
        or _file_ref(run_request.contract_path, runtime, "contract") != CONTRACT_REF
    ):
        raise ArtifactIntegrityError("Repository replay request differs from its verified Guard")
    pins = {pin.path: pin for pin in facts["pins"]["h"]}
    selected = tuple(sorted((*facts["runtime_refs"], CONTRACT_REF)))
    input_pins = []
    for ref in selected:
        if digest_bytes(resolve_ref(runtime, ref).read_bytes()) != pins[ref].content_digest:
            raise ArtifactIntegrityError("Materialized replay input differs from assertion head")
        input_pins.append(
            ExecutionInputPin(
                path=ref, object_id=pins[ref].object_id, content_digest=pins[ref].content_digest
            )
        )
    test_ref = _file_ref(run_request.test_path, runtime, "test")
    expected_test = render_repository_test(contract, case_ids)
    if (
        test_ref != "_cg/test_guard.py"
        or resolve_ref(runtime, test_ref).read_bytes() != expected_test
    ):
        raise ArtifactIntegrityError("Repository replay assertions differ from minimal Guard cases")
    value = ReviewedReplayAuthorization(
        image_digest=review.image_digest,
        runner_review_digest=review.artifact_digest,
        policy_digest=digest_json_artifact(DockerPolicyV1()),
        manifest_digest=facts["manifest"]["artifact_digest"],
        inspection_digest=inspection.artifact_digest,
        guard_digest=guard.artifact_digest,
        evidence_digest=verified.evidence.artifact_digest,
        scope_digest=scope.artifact_digest,
        registry_entry_digest=verified.entry.artifact_digest,
        registry_event_tip_digest=item["events"][-1]["artifact_digest"],
        head_commit=inspection.head_commit,
        implementation_digests=inspection_implementation_digests(),
        request_digest=_request_digest(run_request),
        input_pins=tuple(input_pins),
        test_ref=test_ref,
        test_digest=digest_bytes(expected_test),
        artifact_digest=ZERO,
    )
    return value.model_copy(update={"artifact_digest": digest_json_artifact(value)})


@dataclass(frozen=True)
class ReviewedRepositoryExecutor:
    authorization: ReviewedReplayAuthorization
    verification_request: object
    guard_id: str
    policy: DockerPolicyV1 = DockerPolicyV1()

    def _verify(self, request):
        rebuilt = authorize_reviewed_replay(self.verification_request, self.guard_id, request)
        if rebuilt != self.authorization:
            raise ArtifactIntegrityError("Reviewed repository replay authorization is stale")

    def execute(self, request):
        self._verify(request)
        executable = _docker_executable()
        _require_image_identity(executable, self.authorization.image_digest, self.policy)
        run = _execute_with_adapter(request, _AdmittedDockerProcess(self, executable))
        try:
            self._verify(request)
            write_immutable(request.cwd / "run.json", canonical_json_bytes(run))
            verify_run_record(run, cwd=request.cwd, known_case_ids=request.known_case_ids)
        except (ArtifactIntegrityError, OSError, ValueError) as error:
            raise GuardReplayIntegrityError(
                "Repository replay changed after execution", run
            ) from error
        return run


def prepare_repository_replay(request, output, mapping, expected_inspection):
    verified, facts, scope, inspection, _, _ = _admission(request, mapping.guard_id)
    if inspection != expected_inspection or mapping != facts["config"].targets[0]:
        raise UnsupportedRepositoryScope(
            "Target mapping differs from the reviewed repository profile"
        )
    runtime = output / "work" / mapping.target_id
    for ref in sorted((*facts["runtime_refs"], CONTRACT_REF)):
        write_immutable(runtime / ref, facts["trees"]["h"][ref])
    test = runtime / "_cg/test_guard.py"
    case_ids = tuple(case.case_id for case in verified.guard.cases)
    write_immutable(test, render_repository_test(facts["contract"], case_ids))
    run_request = PytestRunRequest(
        role=RunRole.REPLAY,
        contract_id=verified.guard.contract_id,
        contract_digest=verified.guard.contract_digest,
        target=TargetRef(
            module=facts["contract"].target_module, symbol=mapping.symbol, source_ref=SOURCE_REF
        ),
        target_digest=verified.guard.source_fixed_digest,
        test_path=test,
        known_case_ids=case_ids,
        cwd=runtime,
        artifact_root=runtime / "a",
        contract_path=runtime / CONTRACT_REF,
    )
    authorization = authorize_reviewed_replay(request, mapping.guard_id, run_request)
    write_immutable(runtime / "authorization.json", canonical_json_bytes(authorization))
    return (
        scope.artifact_digest,
        run_request,
        ReviewedRepositoryExecutor(authorization, request, mapping.guard_id),
    )
