"""Promote declarative candidates only after trusted, bidirectional execution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import ValidationError, model_validator

from evidenceguard.artifacts import write_immutable
from evidenceguard.digests import (
    canonical_json_bytes,
    digest_bytes,
    digest_file,
    digest_json_artifact,
)
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.evidence import (
    CaptureRequest,
    _load_contract,
    capture_evidence,
    parse_target_ref,
    verify_evidence,
)
from evidenceguard.execution import _classify_completed_run
from evidenceguard.independent_verifier import (
    EMPTY_DIGEST,
    AgentContext,
    CandidateRecord,
    VerificationRequest,
    assess_candidate,
    propose_candidate,
    render_candidate,
)
from evidenceguard.model_client import MAX_RESPONSE_BYTES, RecordedModelClient
from evidenceguard.models import ArtifactRef, Digest, FrozenModel, TargetRef, UtcDateTime
from evidenceguard.path_limits import require_publication, require_run_directory


class GateResult(FrozenModel):
    schema_version: Literal["verification-gate.v1"] = "verification-gate.v1"
    request_id: str
    created_at: UtcDateTime
    agent_source: Literal["recorded"] = "recorded"
    request_ref: ArtifactRef
    request_digest: Digest
    candidate_ref: ArtifactRef
    candidate_digest: Digest
    fixed_target: TargetRef
    fixed_target_digest: Digest
    status: Literal["verified", "rejected"]
    reason_code: Literal["candidate_rejected", "not_reproduced"] | None
    rejection_reasons: tuple[str, ...]
    test_ref: ArtifactRef | None
    test_digest: Digest | None
    diagnostic_evidence_ref: ArtifactRef | None
    diagnostic_evidence_digest: Digest | None
    evidence_ref: ArtifactRef | None
    evidence_digest: Digest | None
    artifact_digest: Digest

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        for ref, digest in (
            (self.test_ref, self.test_digest),
            (self.diagnostic_evidence_ref, self.diagnostic_evidence_digest),
            (self.evidence_ref, self.evidence_digest),
        ):
            if (ref is None) != (digest is None):
                raise ValueError("Reference and digest must be present together")
        if self.status == "verified":
            if (
                self.reason_code is not None
                or self.rejection_reasons
                or any(
                    value is None
                    for value in (
                        self.test_ref,
                        self.diagnostic_evidence_ref,
                        self.evidence_ref,
                    )
                )
            ):
                raise ValueError("Verified Gate requires bidirectional Evidence")
        elif (
            self.reason_code is None or not self.rejection_reasons or self.evidence_ref is not None
        ):
            raise ValueError("Rejected Gate cannot publish trusted Evidence")
        return self


def _path(path: str | Path, cwd: Path) -> Path:
    result = (cwd / path).resolve()
    if not result.is_relative_to(cwd):
        raise ValueError("Verification path must resolve below cwd")
    return result


def _ref(path: Path, cwd: Path) -> str:
    return path.relative_to(cwd).as_posix()


def _request(path: Path) -> VerificationRequest:
    try:
        return VerificationRequest.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise ValueError("Verification request schema is invalid") from error


def _context(request: VerificationRequest, cwd: Path) -> AgentContext:
    contract = _path(request.contract_ref, cwd)
    manifest = _load_contract(contract)
    target, target_digest = parse_target_ref(request.buggy_target, cwd=cwd, validate_symbol=True)
    if target.symbol != manifest.target_symbol:
        raise ValueError("Candidate target does not match the authoritative contract symbol")
    return AgentContext(
        contract_ref=request.contract_ref,
        contract_digest=digest_file(contract),
        contract_json=contract.read_text(encoding="utf-8"),
        buggy_target=target,
        buggy_target_digest=target_digest,
        buggy_source_code=_path(target.source_ref, cwd).read_text(encoding="utf-8"),
    )


def _layout(root: Path, request: VerificationRequest) -> tuple[Path, Path, str]:
    stem = request.request_id.removeprefix("req_")
    directory = root / "candidates" / f"cnd_{stem}"
    evidence_id = f"evd_{stem}"
    evidence_path = root / "evidence" / evidence_id / "evidence.json"
    return directory, evidence_path, evidence_id


def _preflight(directory: Path, evidence_path: Path, evidence_id: str) -> None:
    for name in ("candidate.json", "gate.json", "test_candidate.py"):
        require_publication(directory / name)
    require_publication(evidence_path)
    require_publication(directory / "runtime/evidence" / evidence_id / "evidence.json")
    require_run_directory(directory / "runtime/runs" / ("run_" + "0" * 32))


def capture_candidate(
    request_path: str | Path,
    *,
    cwd: str | Path,
    workspace: str | Path,
    agent_source: str = "recorded",
) -> GateResult:
    """Completion marker is gate.json; identical completed requests are read-only."""
    cwd = Path(cwd).resolve(strict=True)
    request_path = _path(request_path, cwd)
    request_digest = digest_file(request_path)
    request = _request(request_path)
    if agent_source != "recorded":
        raise ValueError("D10 supports agent-source=recorded only")
    root = _path(workspace, cwd)
    directory, public_evidence, evidence_id = _layout(root, request)
    if (directory / "gate.json").exists():
        result = verify_gate(directory / "gate.json", cwd=cwd)
        if result.request_ref != _ref(request_path, cwd):
            raise ArtifactIntegrityError("Request ID already belongs to another request file")
        return result
    _preflight(directory, public_evidence, evidence_id)
    if directory.exists() and any(directory.iterdir()):
        raise ArtifactIntegrityError("Incomplete candidate exists; use a new request ID")
    context = _context(request, cwd)
    fixed, fixed_digest = parse_target_ref(request.fixed_target, cwd=cwd, validate_symbol=True)
    if fixed.symbol != context.buggy_target.symbol:
        raise ValueError("Fixed target must implement the same contract symbol")
    response_path = _path(request.response_ref, cwd)
    # Response files are bounded; fingerprints below always describe complete bytes.
    if response_path.stat().st_size > MAX_RESPONSE_BYTES:
        raise ValueError("Recorded response exceeds the 64 KiB input limit")
    response_digest = digest_file(response_path)
    record = propose_candidate(
        RecordedModelClient(response_path),
        context,
        candidate_id=directory.name,
        request_ref=_ref(request_path, cwd),
        request_digest=request_digest,
        response_ref=request.response_ref,
    )
    if response_digest != record.response_digest:
        raise ArtifactIntegrityError("Recorded response changed during candidate generation")
    candidate_path = directory / "candidate.json"
    write_immutable(candidate_path, canonical_json_bytes(record) + b"\n")
    test_path = directory / "test_candidate.py"
    diagnostic_path = directory / "runtime/evidence" / evidence_id / "evidence.json"
    evidence = None
    test_digest = None
    if record.candidate is not None:
        test_bytes = render_candidate(record.candidate, context)
        test_digest = digest_bytes(test_bytes)
        write_immutable(test_path, test_bytes)
        evidence = capture_evidence(
            CaptureRequest(
                evidence_id=evidence_id,
                contract_path=Path(request.contract_ref),
                test_path=test_path,
                buggy_target=request.buggy_target,
                fixed_target=request.fixed_target,
                cwd=cwd,
                artifact_root=directory / "runtime",
                timeout_seconds=request.timeout_seconds,
            )
        )
        evidence = verify_evidence(diagnostic_path, cwd=cwd)
    # Check all pins after execution before promoting any candidate.
    if (
        digest_file(request_path) != request_digest
        or _request(request_path) != request
        or digest_file(response_path) != response_digest
        or _context(request, cwd) != context
        or digest_file(_path(fixed.source_ref, cwd)) != fixed_digest
        or (test_digest is not None and digest_file(test_path) != test_digest)
    ):
        raise ArtifactIntegrityError("Verification inputs changed during the Gate")
    verified = evidence is not None and evidence.reproduced
    if verified:
        write_immutable(public_evidence, diagnostic_path.read_bytes())
    draft = GateResult(
        request_id=request.request_id,
        created_at=datetime.now(UTC),
        request_ref=_ref(request_path, cwd),
        request_digest=request_digest,
        candidate_ref=_ref(candidate_path, cwd),
        candidate_digest=record.artifact_digest,
        fixed_target=fixed,
        fixed_target_digest=fixed_digest,
        status="verified" if verified else "rejected",
        reason_code=None
        if verified
        else "candidate_rejected"
        if evidence is None
        else "not_reproduced",
        rejection_reasons=()
        if verified
        else evidence.rejection_reasons
        if evidence is not None
        else (record.reason_code,),
        test_ref=_ref(test_path, cwd) if test_digest is not None else None,
        test_digest=test_digest,
        diagnostic_evidence_ref=_ref(diagnostic_path, cwd) if evidence is not None else None,
        diagnostic_evidence_digest=evidence.artifact_digest if evidence is not None else None,
        evidence_ref=_ref(public_evidence, cwd) if verified else None,
        evidence_digest=evidence.artifact_digest if verified else None,
        artifact_digest=EMPTY_DIGEST,
    )
    result = draft.model_copy(update={"artifact_digest": digest_json_artifact(draft)})
    write_immutable(directory / "gate.json", canonical_json_bytes(result) + b"\n")
    return verify_gate(directory / "gate.json", cwd=cwd)


def _load(path: Path, model):
    try:
        record = model.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as error:
        raise ArtifactIntegrityError("Gate artifact is unreadable or invalid") from error
    if digest_json_artifact(record) != record.artifact_digest:
        raise ArtifactIntegrityError("Gate artifact self digest mismatch")
    return record


def verify_gate(path: str | Path, *, cwd: str | Path) -> GateResult:
    cwd = Path(cwd).resolve(strict=True)
    gate_path = _path(path, cwd)
    result = _load(gate_path, GateResult)
    request_path = _path(result.request_ref, cwd)
    if digest_file(request_path) != result.request_digest:
        raise ArtifactIntegrityError("Gate request digest mismatch")
    request = _request(request_path)
    root = gate_path.parent.parent.parent
    directory, public_evidence, evidence_id = _layout(root, request)
    if gate_path != directory / "gate.json" or result.request_id != request.request_id:
        raise ArtifactIntegrityError("Gate identity/location mismatch")
    context = _context(request, cwd)
    record = _load(_path(result.candidate_ref, cwd), CandidateRecord)
    if (
        result.candidate_ref != _ref(directory / "candidate.json", cwd)
        or record.candidate_id != directory.name
        or record.artifact_digest != result.candidate_digest
        or record.request_ref != result.request_ref
        or record.request_digest != result.request_digest
        or record.context_digest != digest_bytes(canonical_json_bytes(context))
        or record.response_ref != request.response_ref
    ):
        raise ArtifactIntegrityError("Gate candidate provenance mismatch")
    response_path = _path(request.response_ref, cwd)
    if response_path.stat().st_size > MAX_RESPONSE_BYTES:
        raise ArtifactIntegrityError("Gate response exceeds the input limit")
    raw = response_path.read_bytes()
    if digest_bytes(raw) != record.response_digest or len(raw) != record.response_size:
        raise ArtifactIntegrityError("Gate response digest mismatch")
    candidate, reason = assess_candidate(raw, context)
    if candidate != record.candidate or reason != record.reason_code:
        raise ArtifactIntegrityError("Gate candidate admission mismatch")
    fixed, fixed_digest = parse_target_ref(request.fixed_target, cwd=cwd, validate_symbol=True)
    if fixed != result.fixed_target or fixed_digest != result.fixed_target_digest:
        raise ArtifactIntegrityError("Gate fixed target digest mismatch")
    if candidate is None:
        if (
            result.status != "rejected"
            or result.reason_code != "candidate_rejected"
            or result.test_ref is not None
            or result.diagnostic_evidence_ref is not None
            or result.rejection_reasons != (record.reason_code,)
        ):
            raise ArtifactIntegrityError("Invalid candidate must never reach execution")
        return result
    test_path = directory / "test_candidate.py"
    expected_test = render_candidate(candidate, context)
    if (
        result.test_ref != _ref(test_path, cwd)
        or digest_bytes(expected_test) != result.test_digest
        or test_path.read_bytes() != expected_test
    ):
        raise ArtifactIntegrityError("Gate generated test/oracle mismatch")
    diagnostic_path = directory / "runtime/evidence" / evidence_id / "evidence.json"
    if result.diagnostic_evidence_ref != _ref(diagnostic_path, cwd):
        raise ArtifactIntegrityError("Gate diagnostic Evidence location mismatch")
    evidence = verify_evidence(diagnostic_path, cwd=cwd)
    for run in (evidence.buggy_run, evidence.fixed_run):
        if run.pytest_exit_code is not None:
            outcome, cases, _ = _classify_completed_run(
                run.pytest_exit_code,
                _path(run.junit_ref, cwd),
                candidate.case_ids,
            )
            if outcome != run.outcome or cases != run.case_results:
                raise ArtifactIntegrityError("Gate raw JUnit contradicts the claimed execution")
    if (
        evidence.artifact_digest != result.diagnostic_evidence_digest
        or evidence.contract_ref != request.contract_ref
        or evidence.contract_digest != context.contract_digest
        or evidence.test_ref != result.test_ref
        or evidence.test_digest != result.test_digest
        or evidence.buggy_target != context.buggy_target
        or evidence.buggy_target_digest != context.buggy_target_digest
        or evidence.fixed_target != fixed
        or evidence.fixed_target_digest != fixed_digest
        or evidence.buggy_run.timeout_seconds != request.timeout_seconds
        or evidence.fixed_run.timeout_seconds != request.timeout_seconds
    ):
        raise ArtifactIntegrityError("Gate bidirectional Evidence binding mismatch")
    if evidence.reproduced != (result.status == "verified"):
        raise ArtifactIntegrityError("Gate status contradicts trusted execution")
    if result.rejection_reasons != evidence.rejection_reasons:
        raise ArtifactIntegrityError("Gate rejection reasons contradict trusted execution")
    if evidence.reproduced:
        if (
            result.evidence_ref != _ref(public_evidence, cwd)
            or result.evidence_digest != evidence.artifact_digest
            or public_evidence.read_bytes() != diagnostic_path.read_bytes()
        ):
            raise ArtifactIntegrityError("Gate public Evidence promotion mismatch")
        verify_evidence(public_evidence, cwd=cwd)
    elif result.reason_code != "not_reproduced":
        raise ArtifactIntegrityError("Gate rejection reason mismatch")
    return result


def gate_exit_code(result: GateResult, *, cwd: Path) -> int:
    if result.status == "verified":
        return 0
    if result.diagnostic_evidence_ref is None:
        return 2
    from evidenceguard.evidence import evidence_exit_code

    return evidence_exit_code(verify_evidence(result.diagnostic_evidence_ref, cwd=cwd))
