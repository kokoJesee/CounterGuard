"""Capture, persist, load, and verify bidirectional bug evidence."""

from __future__ import annotations

import ast
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import ValidationError

from evidenceguard.artifacts import write_immutable
from evidenceguard.contracts import convert_contract_value, resolve_exception
from evidenceguard.digests import (
    canonical_json_bytes,
    digest_file,
    digest_json_artifact,
)
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.execution import (
    DEFAULT_TIMEOUT_SECONDS,
    PytestRunRequest,
    run_pytest,
    verify_run_record,
)
from evidenceguard.models import (
    CaseOutcome,
    Digest,
    Evidence,
    EvidenceLink,
    RunOutcome,
    RunRecord,
    RunRole,
    TargetRef,
)

_CASE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")
_POSITIONAL_CASE_ID_PATTERN = re.compile(r"^(?:case|test)-?\d+$")
_EVIDENCE_ID_PATTERN = re.compile(r"^evd_[A-Za-z0-9][A-Za-z0-9_-]*$")
_CONTRACT_REQUIRED_FIELDS = frozenset(
    {
        "contract_id",
        "contract_family",
        "contract_version",
        "interface_kind",
        "target_symbol",
        "symbol_signature",
        "argument_types",
        "return_type",
        "cases",
    }
)
_CONTRACT_OPTIONAL_FIELDS = frozenset({"rounding", "lexical_policy"})
_CONTRACT_TYPES = frozenset({"boolean", "decimal", "integer", "optional_string"})
_PLACEHOLDER_DIGEST = "sha256:" + "0" * 64


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    """Inputs for one trusted, bidirectional evidence capture."""

    evidence_id: str
    contract_path: Path
    test_path: Path
    buggy_target: str
    fixed_target: str
    cwd: Path
    artifact_root: Path
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    tool_version: str | None = None
    supersedes_path: Path | None = None
    recapture_reason: str | None = None


@dataclass(frozen=True, slots=True)
class _ContractManifest:
    contract_id: str
    target_symbol: str
    case_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _CaptureInputs:
    cwd: Path
    artifact_root: Path
    evidence_path: Path
    contract_ref: str
    contract_digest: Digest
    contract: _ContractManifest
    test_path: Path
    test_ref: str
    test_digest: Digest
    buggy_target: TargetRef
    buggy_target_digest: Digest
    fixed_target: TargetRef
    fixed_target_digest: Digest
    tool_version: str
    supersedes: EvidenceLink | None
    capture_revision: int
    recapture_reason: str | None


def capture_evidence(request: CaptureRequest) -> Evidence:
    """Run a contract against buggy and fixed targets and persist the Evidence.

    Repeating the same request returns the already verified artifact without
    rerunning pytest. Reusing an evidence ID for different immutable inputs is
    rejected before any new run starts.
    """

    prepared = _prepare_capture(request)
    if prepared.evidence_path.exists():
        existing = verify_evidence(prepared.evidence_path, cwd=prepared.cwd)
        _require_same_capture_inputs(
            existing, request.evidence_id, prepared, request.timeout_seconds
        )
        return existing

    buggy_run = _run_target(
        prepared,
        role=RunRole.BUGGY,
        target=prepared.buggy_target,
        target_digest=prepared.buggy_target_digest,
        timeout_seconds=request.timeout_seconds,
    )
    fixed_run = _run_target(
        prepared,
        role=RunRole.FIXED,
        target=prepared.fixed_target,
        target_digest=prepared.fixed_target_digest,
        timeout_seconds=request.timeout_seconds,
    )
    _require_unchanged_inputs(prepared)
    failing_case_ids = _fixed_buggy_failures(buggy_run, fixed_run)
    rejection_reasons = _rejection_reasons(buggy_run, fixed_run, failing_case_ids)
    reproduced = not rejection_reasons

    draft = Evidence(
        evidence_id=request.evidence_id,
        created_at=datetime.now(UTC),
        contract_id=prepared.contract.contract_id,
        contract_ref=prepared.contract_ref,
        contract_digest=prepared.contract_digest,
        test_ref=prepared.test_ref,
        test_digest=prepared.test_digest,
        buggy_target=prepared.buggy_target,
        fixed_target=prepared.fixed_target,
        buggy_target_digest=prepared.buggy_target_digest,
        fixed_target_digest=prepared.fixed_target_digest,
        buggy_run=buggy_run,
        fixed_run=fixed_run,
        failing_case_ids=failing_case_ids,
        reproduced=reproduced,
        rejection_reasons=rejection_reasons,
        tool_version=prepared.tool_version,
        artifact_digest=_PLACEHOLDER_DIGEST,
        capture_revision=prepared.capture_revision,
        supersedes=prepared.supersedes,
        recapture_reason=prepared.recapture_reason,
    )
    evidence = Evidence.model_validate(
        {
            **draft.model_dump(),
            "artifact_digest": digest_json_artifact(draft),
        }
    )
    _publish_evidence(prepared.evidence_path, evidence)
    return evidence


def load_evidence(path: str | Path) -> Evidence:
    """Load an Evidence JSON document and verify its self digest."""

    evidence_path = Path(path)
    try:
        raw = evidence_path.read_bytes()
    except OSError as error:
        raise ArtifactIntegrityError(f"cannot read Evidence artifact: {evidence_path}") from error
    try:
        # JSON validation preserves strict field checking while decoding the
        # JSON representations of datetime, Enum, and tuple values.
        evidence = Evidence.model_validate_json(raw)
    except ValidationError as error:
        raise ArtifactIntegrityError(
            f"Evidence schema validation failed: {evidence_path}"
        ) from error

    actual_digest = digest_json_artifact(evidence)
    if actual_digest != evidence.artifact_digest:
        raise ArtifactIntegrityError(
            "Evidence artifact digest mismatch: "
            f"expected {evidence.artifact_digest}, got {actual_digest}"
        )
    return evidence


def verify_evidence(path: str | Path, *, cwd: str | Path) -> Evidence:
    """Verify an Evidence artifact and every file digest it references."""

    workspace = Path(cwd).resolve(strict=True)
    if not workspace.is_dir():
        raise ArtifactIntegrityError("Evidence workspace must be a directory")
    evidence_path = _verified_workspace_file(Path(path), workspace, "evidence artifact")
    evidence = load_evidence(evidence_path)
    _verify_lineage(evidence, workspace)

    if evidence_path.name != "evidence.json" or evidence_path.parent.name != evidence.evidence_id:
        raise ArtifactIntegrityError(
            "Evidence artifact must be stored at <artifact-root>/evidence/"
            f"{evidence.evidence_id}/evidence.json"
        )
    if evidence_path.parent.parent.name != "evidence":
        raise ArtifactIntegrityError("Evidence artifact parent directory must be named 'evidence'")

    references: tuple[tuple[str, str, Digest], ...] = (
        ("contract", evidence.contract_ref, evidence.contract_digest),
        ("test", evidence.test_ref, evidence.test_digest),
        (
            "buggy target",
            evidence.buggy_target.source_ref,
            evidence.buggy_target_digest,
        ),
        (
            "fixed target",
            evidence.fixed_target.source_ref,
            evidence.fixed_target_digest,
        ),
        ("buggy stdout", evidence.buggy_run.stdout_ref, evidence.buggy_run.stdout_digest),
        ("buggy stderr", evidence.buggy_run.stderr_ref, evidence.buggy_run.stderr_digest),
        ("buggy JUnit", evidence.buggy_run.junit_ref, evidence.buggy_run.junit_digest),
        ("fixed stdout", evidence.fixed_run.stdout_ref, evidence.fixed_run.stdout_digest),
        ("fixed stderr", evidence.fixed_run.stderr_ref, evidence.fixed_run.stderr_digest),
        ("fixed JUnit", evidence.fixed_run.junit_ref, evidence.fixed_run.junit_digest),
    )
    for label, artifact_ref, expected_digest in references:
        referenced_path = _verified_workspace_file(workspace / artifact_ref, workspace, label)
        actual_digest = digest_file(referenced_path)
        if actual_digest != expected_digest:
            raise ArtifactIntegrityError(
                f"{label} digest mismatch for {artifact_ref}: "
                f"expected {expected_digest}, got {actual_digest}"
            )

    contract = _load_contract(workspace / evidence.contract_ref)
    if contract.contract_id != evidence.contract_id:
        raise ArtifactIntegrityError("Evidence contract identity contradicts its source")
    for target, expected in (
        (evidence.buggy_target, evidence.buggy_target_digest),
        (evidence.fixed_target, evidence.fixed_target_digest),
    ):
        try:
            actual_target, actual_digest = parse_target_ref(
                f"{target.module}:{target.symbol}", cwd=workspace, validate_symbol=True
            )
        except (OSError, ValueError) as error:
            raise ArtifactIntegrityError("Evidence target binding is unavailable") from error
        if (
            actual_target != target
            or actual_digest != expected
            or target.symbol != contract.target_symbol
        ):
            raise ArtifactIntegrityError("Evidence target identity contradicts its source")
    for run in (evidence.buggy_run, evidence.fixed_run):
        verify_run_record(run, cwd=workspace, known_case_ids=contract.case_ids)
    return evidence


def evidence_exit_code(evidence: Evidence) -> int:
    """Use the same admissibility decision for CLI verification and inventory."""
    domain_outcomes = {RunOutcome.PASSED, RunOutcome.TEST_FAILED}
    if any(run.outcome not in domain_outcomes for run in (evidence.buggy_run, evidence.fixed_run)):
        return 3
    return 0 if evidence.reproduced else 1


def inventory_evidence(*, cwd: str | Path, artifact_root: str | Path) -> dict:
    """Inspect every artifact through full verification; names never imply validity."""
    workspace = Path(cwd).resolve(strict=True)
    root = _workspace_path(Path(artifact_root), workspace, "artifact_root") / "evidence"
    rows = []
    verified = {}
    for directory in sorted(root.iterdir()) if root.is_dir() else ():
        if not directory.is_dir():
            continue
        path = directory / "evidence.json"
        row = {
            "evidence_id": directory.name,
            "path": path.relative_to(workspace).as_posix(),
            "status": "invalid",
            "verification_exit_code": 5,
            "usable": False,
            "eligible": False,
            "superseded_by": [],
            "reason": None,
        }
        try:
            evidence = verify_evidence(path, cwd=workspace)
        except (ArtifactIntegrityError, OSError, ValueError) as error:
            row["reason"] = str(error)
        else:
            code = evidence_exit_code(evidence)
            row.update(
                status="verified" if code == 0 else "diagnostic",
                verification_exit_code=code,
                usable=code == 0,
                eligible=code == 0,
                capture_revision=evidence.capture_revision
                if evidence.schema_version == "evidence.v2"
                else None,
                recapture_reason=evidence.recapture_reason,
            )
            if code == 0:
                verified[evidence.evidence_id] = evidence
        rows.append(row)
    successors: dict[str, list[str]] = {}
    for evidence in verified.values():
        if evidence.supersedes is not None:
            successors.setdefault(evidence.supersedes.evidence_id, []).append(evidence.evidence_id)
    for row in rows:
        row["superseded_by"] = sorted(successors.get(row["evidence_id"], []))
        row["eligible"] = row["usable"] and not row["superseded_by"]
    return {
        "schema_version": "evidence-inventory.v1",
        "entries": rows,
        "counts": {
            "total": len(rows),
            "verified": sum(row["usable"] for row in rows),
            "invalid": sum(row["status"] == "invalid" for row in rows),
            "diagnostic": sum(row["status"] == "diagnostic" for row in rows),
            "eligible": sum(row["eligible"] for row in rows),
        },
    }


def _verify_lineage(evidence: Evidence, workspace: Path) -> None:
    current = evidence
    visited = {current.evidence_id}
    while current.supersedes is not None:
        link = current.supersedes
        path = _verified_workspace_file(workspace / link.evidence_ref, workspace, "predecessor")
        # Historical input files may be stale; the immutable predecessor JSON
        # must still be intact. It is never admitted for new work by this check.
        prior = load_evidence(path)
        if (
            prior.evidence_id in visited
            or prior.evidence_id != link.evidence_id
            or prior.artifact_digest != link.artifact_digest
        ):
            raise ArtifactIntegrityError("Evidence predecessor identity/digest mismatch or cycle")
        if (
            prior.contract_id != current.contract_id
            or current.capture_revision != prior.capture_revision + 1
        ):
            raise ArtifactIntegrityError("Evidence predecessor contract/revision mismatch")
        visited.add(prior.evidence_id)
        current = prior


def parse_target_ref(
    spec: str, *, cwd: str | Path, validate_symbol: bool = True
) -> tuple[TargetRef, Digest]:
    """Resolve ``module:symbol`` to a repository-relative source and digest."""

    if spec.count(":") != 1:
        raise ValueError("target must use the form module:symbol")
    module, symbol = spec.split(":", maxsplit=1)
    if not module or not symbol:
        raise ValueError("target must use the form module:symbol")

    workspace = Path(cwd).resolve(strict=True)
    # Let TargetRef enforce the public module/symbol syntax before touching disk.
    provisional = TargetRef(module=module, symbol=symbol, source_ref="placeholder.py")
    relative_module = Path(*module.split("."))
    candidates: list[Path] = []
    for import_root in (workspace, workspace / "src"):
        for candidate in (
            import_root / relative_module.with_suffix(".py"),
            import_root / relative_module / "__init__.py",
        ):
            if candidate.is_file():
                candidates.append(candidate.resolve(strict=True))
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        raise ValueError(f"target module source was not found below the workspace: {module}")
    if len(candidates) > 1:
        refs = ", ".join(path.relative_to(workspace).as_posix() for path in candidates)
        raise ValueError(f"target module resolves ambiguously below the workspace: {refs}")

    source_path = _verified_workspace_file(candidates[0], workspace, "target source")
    if validate_symbol:
        _require_symbol_in_source(source_path, symbol)
    target = TargetRef(
        module=provisional.module,
        symbol=provisional.symbol,
        source_ref=source_path.relative_to(workspace).as_posix(),
    )
    return target, digest_file(source_path)


def _prepare_capture(request: CaptureRequest) -> _CaptureInputs:
    if not _EVIDENCE_ID_PATTERN.fullmatch(request.evidence_id):
        raise ValueError("evidence_id must start with 'evd_' and contain safe characters")
    if re.search(r"_d\d+$", request.evidence_id):
        raise ValueError(
            "Calendar-suffixed Evidence IDs are legacy only; use a semantic _vN revision"
        )
    cwd = Path(request.cwd).resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError("cwd must be a directory")
    if not math.isfinite(request.timeout_seconds) or request.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a positive finite number")

    contract_path = _verified_workspace_file(request.contract_path, cwd, "contract")
    test_path = _verified_workspace_file(request.test_path, cwd, "contract test")
    contract = _load_contract(contract_path)
    buggy_target, buggy_digest = parse_target_ref(request.buggy_target, cwd=cwd)
    fixed_target, fixed_digest = parse_target_ref(request.fixed_target, cwd=cwd)
    if buggy_target.symbol != contract.target_symbol:
        raise ValueError("buggy target symbol does not match contract target_symbol")
    if fixed_target.symbol != contract.target_symbol:
        raise ValueError("fixed target symbol does not match contract target_symbol")

    predecessor = None
    revision = 1
    if request.supersedes_path is not None:
        if not request.recapture_reason or not request.recapture_reason.strip():
            raise ValueError("A recapture requires an explicit reason")
        predecessor_path = _verified_workspace_file(request.supersedes_path, cwd, "predecessor")
        prior = load_evidence(predecessor_path)
        _verify_lineage(prior, cwd)
        if prior.evidence_id == request.evidence_id or prior.contract_id != contract.contract_id:
            raise ValueError("Cannot supersede the same Evidence ID or a different contract")
        revision = prior.capture_revision + 1
        predecessor = EvidenceLink(
            evidence_id=prior.evidence_id,
            evidence_ref=predecessor_path.relative_to(cwd).as_posix(),
            artifact_digest=prior.artifact_digest,
        )
    elif request.recapture_reason is not None:
        raise ValueError("recapture_reason requires a supersedes path")
    version_suffix = re.search(r"_v([1-9]\d*)$", request.evidence_id)
    if version_suffix and int(version_suffix.group(1)) != revision:
        raise ValueError("Evidence ID version suffix must match its derived capture revision")

    artifact_root = _workspace_path(request.artifact_root, cwd, "artifact_root")
    evidence_path = artifact_root / "evidence" / request.evidence_id / "evidence.json"
    tool_version = request.tool_version or _package_version()
    if not tool_version:
        raise ValueError("tool_version must not be empty")

    return _CaptureInputs(
        cwd=cwd,
        artifact_root=artifact_root,
        evidence_path=evidence_path,
        contract_ref=contract_path.relative_to(cwd).as_posix(),
        contract_digest=digest_file(contract_path),
        contract=contract,
        test_path=test_path,
        test_ref=test_path.relative_to(cwd).as_posix(),
        test_digest=digest_file(test_path),
        buggy_target=buggy_target,
        buggy_target_digest=buggy_digest,
        fixed_target=fixed_target,
        fixed_target_digest=fixed_digest,
        tool_version=tool_version,
        supersedes=predecessor,
        capture_revision=revision,
        recapture_reason=request.recapture_reason,
    )


def _load_contract(path: Path) -> _ContractManifest:
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"contract is not valid UTF-8 JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError("contract must be a JSON object")

    keys = set(payload)
    missing = _CONTRACT_REQUIRED_FIELDS - keys
    extra = keys - _CONTRACT_REQUIRED_FIELDS - _CONTRACT_OPTIONAL_FIELDS
    if missing:
        raise ValueError(f"contract is missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"contract has unknown fields: {', '.join(sorted(extra))}")

    for field in (
        "contract_id",
        "contract_family",
        "contract_version",
        "interface_kind",
        "target_symbol",
        "symbol_signature",
    ):
        if not isinstance(payload[field], str) or not payload[field]:
            raise ValueError(f"contract {field} must be a non-empty string")
    for field in _CONTRACT_OPTIONAL_FIELDS & keys:
        if not isinstance(payload[field], str) or not payload[field]:
            raise ValueError(f"contract {field} must be a non-empty string")

    argument_types = payload["argument_types"]
    if not isinstance(argument_types, dict) or not argument_types:
        raise ValueError("contract argument_types must be a non-empty object")
    if any(not isinstance(name, str) or not name for name in argument_types):
        raise ValueError("contract argument names must be non-empty strings")
    if any(
        not isinstance(value, str) or value not in _CONTRACT_TYPES
        for value in argument_types.values()
    ):
        raise ValueError("contract contains an unsupported argument type")
    if not isinstance(payload["return_type"], str) or payload["return_type"] not in _CONTRACT_TYPES:
        raise ValueError("contract contains an unsupported return type")

    cases = payload["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("contract cases must be a non-empty array")
    case_ids: list[str] = []
    argument_names = set(argument_types)
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"contract case {index} must be an object")
        if set(case) - {"case_id", "args", "expected", "raises"}:
            raise ValueError(f"contract case {index} contains unknown fields")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not _CASE_ID_PATTERN.fullmatch(case_id):
            raise ValueError(f"contract case {index} has an invalid stable case_id")
        if _POSITIONAL_CASE_ID_PATTERN.fullmatch(case_id):
            raise ValueError(f"contract case {case_id!r} uses an unstable positional ID")
        if case_id in case_ids:
            raise ValueError(f"contract contains duplicate case_id {case_id!r}")
        arguments = case.get("args")
        if not isinstance(arguments, dict) or set(arguments) != argument_names:
            raise ValueError(f"contract case {case_id!r} args do not match argument_types")
        if ("expected" in case) == ("raises" in case):
            raise ValueError(
                f"contract case {case_id!r} must declare exactly one of expected or raises"
            )
        if "raises" in case and (not isinstance(case["raises"], str) or not case["raises"]):
            raise ValueError(f"contract case {case_id!r} raises must be a non-empty string")
        if "raises" in case:
            resolve_exception(case["raises"])
        for name, value in arguments.items():
            _validate_contract_value(value, argument_types[name], f"{case_id}.{name}")
        if "expected" in case:
            _validate_contract_value(
                case["expected"], payload["return_type"], f"{case_id}.expected"
            )
        case_ids.append(case_id)

    return _ContractManifest(
        contract_id=payload["contract_id"],
        target_symbol=payload["target_symbol"],
        case_ids=tuple(case_ids),
    )


def _validate_contract_value(value: object, declared_type: str, label: str) -> None:
    try:
        convert_contract_value(value, declared_type)
    except ValueError as error:
        raise ValueError(f"contract value {label} does not match {declared_type}") from error


def _require_unchanged_inputs(prepared: _CaptureInputs) -> None:
    for label, ref, expected in (
        ("contract", prepared.contract_ref, prepared.contract_digest),
        ("test", prepared.test_ref, prepared.test_digest),
        ("buggy target", prepared.buggy_target.source_ref, prepared.buggy_target_digest),
        ("fixed target", prepared.fixed_target.source_ref, prepared.fixed_target_digest),
    ):
        if digest_file(prepared.cwd / ref) != expected:
            raise ArtifactIntegrityError(f"{label} changed during capture")


def _run_target(
    prepared: _CaptureInputs,
    *,
    role: RunRole,
    target: TargetRef,
    target_digest: Digest,
    timeout_seconds: float,
) -> RunRecord:
    return run_pytest(
        PytestRunRequest(
            role=role,
            contract_id=prepared.contract.contract_id,
            contract_digest=prepared.contract_digest,
            target=target,
            target_digest=target_digest,
            test_path=prepared.test_path,
            known_case_ids=prepared.contract.case_ids,
            cwd=prepared.cwd,
            artifact_root=prepared.artifact_root,
            timeout_seconds=timeout_seconds,
            contract_path=prepared.cwd / prepared.contract_ref,
        )
    )


def _fixed_buggy_failures(
    buggy_run: RunRecord,
    fixed_run: RunRecord,
) -> tuple[str, ...]:
    buggy_by_case = {result.case_id: result for result in buggy_run.case_results}
    fixed_by_case = {result.case_id: result for result in fixed_run.case_results}
    return tuple(
        sorted(
            case_id
            for case_id in buggy_by_case.keys() & fixed_by_case.keys()
            if buggy_by_case[case_id].outcome is CaseOutcome.FAILED
            and fixed_by_case[case_id].outcome is CaseOutcome.PASSED
        )
    )


def _rejection_reasons(
    buggy_run: RunRecord,
    fixed_run: RunRecord,
    failing_case_ids: tuple[str, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if buggy_run.outcome is not RunOutcome.TEST_FAILED:
        reasons.append(f"buggy-outcome:{buggy_run.outcome.value}")
    if fixed_run.outcome is not RunOutcome.PASSED:
        reasons.append(f"fixed-outcome:{fixed_run.outcome.value}")
    buggy_cases = {result.case_id for result in buggy_run.case_results}
    fixed_cases = {result.case_id for result in fixed_run.case_results}
    if buggy_cases != fixed_cases:
        reasons.append("case-set-mismatch")
    if not failing_case_ids:
        reasons.append("no-buggy-failure-fixed-by-candidate")
    return tuple(sorted(set(reasons)))


def _require_same_capture_inputs(
    evidence: Evidence,
    evidence_id: str,
    prepared: _CaptureInputs,
    timeout_seconds: float,
) -> None:
    actual = (
        evidence.evidence_id,
        evidence.contract_id,
        evidence.contract_ref,
        evidence.contract_digest,
        evidence.test_ref,
        evidence.test_digest,
        evidence.buggy_target,
        evidence.buggy_target_digest,
        evidence.fixed_target,
        evidence.fixed_target_digest,
        evidence.tool_version,
        evidence.buggy_run.timeout_seconds,
        evidence.fixed_run.timeout_seconds,
        evidence.supersedes,
        evidence.capture_revision,
        evidence.recapture_reason,
    )
    expected = (
        evidence_id,
        prepared.contract.contract_id,
        prepared.contract_ref,
        prepared.contract_digest,
        prepared.test_ref,
        prepared.test_digest,
        prepared.buggy_target,
        prepared.buggy_target_digest,
        prepared.fixed_target,
        prepared.fixed_target_digest,
        prepared.tool_version,
        timeout_seconds,
        timeout_seconds,
        prepared.supersedes,
        prepared.capture_revision,
        prepared.recapture_reason,
    )
    if actual != expected:
        raise ArtifactIntegrityError(
            f"Evidence ID {evidence_id!r} already exists with different immutable inputs"
        )


def _publish_evidence(path: Path, evidence: Evidence) -> None:
    write_immutable(path, canonical_json_bytes(evidence))


def _workspace_path(path: Path, cwd: Path, label: str) -> Path:
    candidate = path if path.is_absolute() else cwd / path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(cwd)
    except ValueError as error:
        raise ValueError(f"{label} must resolve below cwd") from error
    return resolved


def _verified_workspace_file(path: Path, cwd: Path, label: str) -> Path:
    try:
        resolved = _workspace_path(path, cwd, label).resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise ArtifactIntegrityError(f"{label} does not exist: {path}") from error
    if not resolved.is_file():
        raise ArtifactIntegrityError(f"{label} must be a file: {path}")
    return resolved


def _require_symbol_in_source(path: Path, symbol: str) -> None:
    try:
        module = ast.parse(path.read_bytes(), filename=str(path))
    except (OSError, SyntaxError) as error:
        raise ValueError(f"target source is not valid Python: {path}") from error

    body: list[ast.stmt] = module.body
    for part in symbol.split("."):
        matches = [
            statement
            for statement in body
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and statement.name == part
        ]
        if len(matches) != 1:
            raise ValueError(f"target symbol {symbol!r} was not found uniquely in {path}")
        body = matches[0].body


def _package_version() -> str:
    try:
        return version("evidenceguard")
    except PackageNotFoundError:
        return "0.1.0"


__all__ = [
    "CaptureRequest",
    "capture_evidence",
    "load_evidence",
    "parse_target_ref",
    "verify_evidence",
]
