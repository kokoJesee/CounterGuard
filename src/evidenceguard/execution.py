"""Controlled pytest execution and JUnit-to-contract result mapping."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import math
import os
import platform
import re
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from evidenceguard.digests import digest_file
from evidenceguard.errors import ArtifactIntegrityError, RunnerDependencyError
from evidenceguard.models import (
    CaseOutcome,
    CaseResult,
    Digest,
    RunOutcome,
    RunRecord,
    RunRole,
    TargetRef,
)
from evidenceguard.path_limits import require_run_directory

DEFAULT_TIMEOUT_SECONDS = 30.0

_RUN_ID_PATTERN = re.compile(r"run_[a-z0-9][a-z0-9_-]*\Z")
_CASE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
_CASE_ID_SUFFIX = re.compile(r"\[([^\[\]]+)]\Z")
_IMPORT_ERROR_TYPES = frozenset({"ImportError", "ModuleNotFoundError"})
_ENVIRONMENT_ALLOWLIST = frozenset(
    {
        "APPDATA",
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "VIRTUAL_ENV",
        "WINDIR",
    }
)
_EXIT_OUTCOMES = {
    2: RunOutcome.INTERRUPTED,
    3: RunOutcome.PYTEST_INTERNAL_ERROR,
    4: RunOutcome.PYTEST_USAGE_ERROR,
    5: RunOutcome.NO_TESTS_COLLECTED,
}


def verify_run_record(run: RunRecord, *, cwd: Path, known_case_ids: tuple[str, ...]) -> None:
    """Audit log bytes and reconstruct execution claims, without starting a process."""
    workspace = cwd.resolve(strict=True)
    if any(case.case_id not in known_case_ids for case in run.case_results):
        raise ArtifactIntegrityError("Recorded execution contains an unknown contract case")
    for ref, expected in (
        (run.stdout_ref, run.stdout_digest),
        (run.stderr_ref, run.stderr_digest),
        (run.junit_ref, run.junit_digest),
    ):
        path = (workspace / ref).resolve()
        if not path.is_relative_to(workspace):
            raise ArtifactIntegrityError("Execution log reference escapes its workspace")
        try:
            actual = digest_file(path)
        except OSError as error:
            raise ArtifactIntegrityError("Execution log is missing or unavailable") from error
        if actual != expected:
            raise ArtifactIntegrityError("Execution log digest mismatch")
    if run.pytest_exit_code is None:
        if run.case_results:
            raise ArtifactIntegrityError("Uncompleted execution cannot claim collected cases")
        return
    outcome, cases, _ = _classify_completed_run(
        run.pytest_exit_code, workspace / run.junit_ref, known_case_ids
    )
    if (outcome, cases) != (run.outcome, run.case_results):
        raise ArtifactIntegrityError("Recorded execution contradicts raw JUnit/case results")


@dataclass(frozen=True, slots=True)
class PytestRunRequest:
    """Everything the runner needs to produce one immutable ``RunRecord``.

    Both ``test_path`` and ``artifact_root`` must be below ``cwd``. The
    restriction keeps recorded references portable and prevents a capture from
    reaching outside its explicitly selected workspace.
    """

    role: RunRole
    contract_id: str
    contract_digest: Digest
    target: TargetRef
    target_digest: Digest
    test_path: Path
    known_case_ids: tuple[str, ...]
    cwd: Path
    artifact_root: Path
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    run_id: str | None = None
    contract_path: Path | None = None


@dataclass(frozen=True, slots=True)
class _PreparedRun:
    run_id: str
    cwd: Path
    test_ref: str
    run_dir: Path
    stdout_path: Path
    stderr_path: Path
    junit_path: Path
    stdout_ref: str
    stderr_ref: str
    junit_ref: str
    known_case_ids: tuple[str, ...]
    contract_ref: str | None


@dataclass(frozen=True, slots=True)
class _JunitResult:
    case_results: tuple[CaseResult, ...]
    problems: tuple[str, ...]


def run_pytest(request: PytestRunRequest) -> RunRecord:
    """Run one contract test with a controlled process and persist raw output.

    A pytest exit status of 1 becomes ``test_failed`` only when the JUnit file
    describes every expected case exactly once, includes at least one assertion
    failure, and contains no setup/collection error. All other ambiguous status-1
    runs become ``process_error``.
    """

    pytest_version = require_pytest()
    prepared = _prepare_run(request)
    argv = (
        sys.executable,
        "-m",
        "pytest",
        prepared.test_ref,
        "-c",
        _workspace_ref(prepared.run_dir / "pytest.ini", prepared.cwd, "pytest config"),
        "--noconftest",
        "-q",
        "--junitxml",
        prepared.junit_ref,
    )
    environment = _controlled_environment(request.target, prepared.contract_ref)
    started_at = datetime.now(UTC)
    started_monotonic = time.monotonic()
    pytest_exit_code: int | None
    case_results: tuple[CaseResult, ...] = ()
    error_detail: str | None = None

    try:
        completed = subprocess.run(
            argv,
            cwd=prepared.cwd,
            env=environment,
            capture_output=True,
            timeout=request.timeout_seconds,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        stdout = _output_bytes(error.stdout)
        stderr = _output_bytes(error.stderr)
        pytest_exit_code = None
        outcome = RunOutcome.TIMEOUT
        error_detail = f"pytest exceeded timeout of {request.timeout_seconds:g} seconds"
    except OSError as error:
        stdout = b""
        stderr = f"could not launch pytest: {type(error).__name__}: {error}".encode(
            "utf-8", errors="replace"
        )
        error_detail = f"could not launch pytest: {type(error).__name__}"
        pytest_exit_code = None
        outcome = RunOutcome.LAUNCH_ERROR
    else:
        stdout = _output_bytes(completed.stdout)
        stderr = _output_bytes(completed.stderr)
        pytest_exit_code = completed.returncode
        outcome, case_results, error_detail = _classify_completed_run(
            pytest_exit_code,
            prepared.junit_path,
            prepared.known_case_ids,
        )

    duration_ms = max(0, round((time.monotonic() - started_monotonic) * 1000))
    prepared.stdout_path.write_bytes(stdout)
    prepared.stderr_path.write_bytes(stderr)
    if not prepared.junit_path.exists():
        # RunRecord references are intentionally non-optional. An empty file is
        # explicit raw evidence that pytest produced no JUnit report.
        prepared.junit_path.write_bytes(b"")

    return RunRecord(
        run_id=prepared.run_id,
        role=request.role,
        contract_id=request.contract_id,
        contract_digest=request.contract_digest,
        target=request.target,
        target_digest=request.target_digest,
        argv=argv,
        cwd=".",
        started_at=started_at,
        duration_ms=duration_ms,
        timeout_seconds=request.timeout_seconds,
        pytest_exit_code=pytest_exit_code,
        outcome=outcome,
        case_results=case_results,
        stdout_ref=prepared.stdout_ref,
        stdout_digest=digest_file(prepared.stdout_path),
        stderr_ref=prepared.stderr_ref,
        stderr_digest=digest_file(prepared.stderr_path),
        junit_ref=prepared.junit_ref,
        junit_digest=digest_file(prepared.junit_path),
        python_version=platform.python_version(),
        pytest_version=pytest_version,
        error_detail=error_detail,
    )


def _prepare_run(request: PytestRunRequest) -> _PreparedRun:
    cwd = request.cwd.resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError("cwd must be a directory")
    if not math.isfinite(request.timeout_seconds) or request.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a positive finite number")

    test_path = request.test_path
    if not test_path.is_absolute():
        test_path = cwd / test_path
    test_path = test_path.resolve(strict=True)
    if not test_path.is_file():
        raise ValueError("test_path must be a file")
    test_ref = _workspace_ref(test_path, cwd, "test_path")

    contract_ref = None
    if request.contract_path is not None:
        contract_path = request.contract_path
        if not contract_path.is_absolute():
            contract_path = cwd / contract_path
        contract_path = contract_path.resolve(strict=True)
        if not contract_path.is_file():
            raise ValueError("contract_path must be a file")
        contract_ref = _workspace_ref(contract_path, cwd, "contract_path")

    artifact_root = request.artifact_root
    if not artifact_root.is_absolute():
        artifact_root = cwd / artifact_root
    artifact_root = artifact_root.resolve()
    _workspace_ref(artifact_root, cwd, "artifact_root")

    if not request.known_case_ids:
        raise ValueError("known_case_ids must not be empty")
    if len(set(request.known_case_ids)) != len(request.known_case_ids):
        raise ValueError("known_case_ids must be unique")
    invalid_case_ids = [
        case_id for case_id in request.known_case_ids if not _CASE_ID_PATTERN.fullmatch(case_id)
    ]
    if invalid_case_ids:
        raise ValueError(f"invalid case IDs: {', '.join(invalid_case_ids)}")

    run_id = request.run_id or f"run_{uuid.uuid4().hex}"
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id must start with 'run_' and contain lowercase safe characters")
    run_dir = artifact_root / "runs" / run_id
    require_run_directory(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")

    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    junit_path = run_dir / "junit.xml"
    return _PreparedRun(
        run_id=run_id,
        cwd=cwd,
        test_ref=test_ref,
        run_dir=run_dir,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        junit_path=junit_path,
        stdout_ref=_workspace_ref(stdout_path, cwd, "stdout_path"),
        stderr_ref=_workspace_ref(stderr_path, cwd, "stderr_path"),
        junit_ref=_workspace_ref(junit_path, cwd, "junit_path"),
        known_case_ids=request.known_case_ids,
        contract_ref=contract_ref,
    )


def _workspace_ref(path: Path, cwd: Path, label: str) -> str:
    try:
        return path.relative_to(cwd).as_posix()
    except ValueError as error:
        raise ValueError(f"{label} must resolve below cwd") from error


def _controlled_environment(target: TargetRef, contract_ref: str | None) -> dict[str, str]:
    environment = {
        key.upper(): value
        for key, value in os.environ.items()
        if key.upper() in _ENVIRONMENT_ALLOWLIST
    }
    environment.update(
        {
            "EVIDENCEGUARD_SYMBOL": target.symbol,
            "EVIDENCEGUARD_TARGET": target.module,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
    )
    if contract_ref is not None:
        environment["EVIDENCEGUARD_CONTRACT"] = contract_ref
    return environment


def _classify_completed_run(
    exit_code: int,
    junit_path: Path,
    known_case_ids: tuple[str, ...],
) -> tuple[RunOutcome, tuple[CaseResult, ...], str | None]:
    if exit_code in _EXIT_OUTCOMES:
        outcome = _EXIT_OUTCOMES[exit_code]
        return outcome, (), f"pytest exited with status {exit_code} ({outcome.value})"
    if exit_code not in {0, 1}:
        return RunOutcome.PROCESS_ERROR, (), f"pytest exited with unexpected status {exit_code}"

    if not junit_path.is_file():
        return RunOutcome.PROCESS_ERROR, (), "pytest did not produce a JUnit report"

    parsed = _parse_junit(junit_path, known_case_ids)
    if parsed.problems:
        return RunOutcome.PROCESS_ERROR, parsed.case_results, "; ".join(parsed.problems)

    failed_cases = [case for case in parsed.case_results if case.outcome is CaseOutcome.FAILED]
    non_pass_or_failure = [
        case
        for case in parsed.case_results
        if case.outcome not in {CaseOutcome.PASSED, CaseOutcome.FAILED}
    ]
    if non_pass_or_failure:
        case_ids = ", ".join(case.case_id for case in non_pass_or_failure)
        detail = f"JUnit contains skipped or errored contract cases: {case_ids}"
        return RunOutcome.PROCESS_ERROR, parsed.case_results, detail

    if exit_code == 0:
        if failed_cases:
            return (
                RunOutcome.PROCESS_ERROR,
                parsed.case_results,
                "pytest exited 0 but JUnit contains failed cases",
            )
        return RunOutcome.PASSED, parsed.case_results, None

    if not failed_cases:
        return (
            RunOutcome.PROCESS_ERROR,
            parsed.case_results,
            "pytest exited 1 without a known failed contract case",
        )
    return RunOutcome.TEST_FAILED, parsed.case_results, None


def _parse_junit(junit_path: Path, known_case_ids: tuple[str, ...]) -> _JunitResult:
    try:
        root = ET.parse(junit_path).getroot()
    except (ET.ParseError, OSError) as error:
        return _JunitResult((), (f"invalid JUnit report: {type(error).__name__}: {error}",))

    known = set(known_case_ids)
    by_case_id: dict[str, CaseResult] = {}
    unknown_nodes: list[str] = []
    duplicate_ids: list[str] = []

    for test_case in root.iter("testcase"):
        name = test_case.get("name", "")
        match = _CASE_ID_SUFFIX.search(name)
        case_id = match.group(1) if match else None
        node_id = _junit_node_id(test_case, name)
        if case_id not in known:
            unknown_nodes.append(node_id)
            continue
        if case_id in by_case_id:
            duplicate_ids.append(case_id)
            continue
        by_case_id[case_id] = _case_result(test_case, case_id, node_id)

    problems: list[str] = []
    if unknown_nodes:
        problems.append(f"JUnit contains unknown test nodes: {', '.join(sorted(unknown_nodes))}")
    if duplicate_ids:
        problems.append(f"JUnit contains duplicate case IDs: {', '.join(sorted(duplicate_ids))}")
    missing_ids = [case_id for case_id in known_case_ids if case_id not in by_case_id]
    if missing_ids:
        problems.append(f"JUnit is missing case IDs: {', '.join(missing_ids)}")

    ordered_results = tuple(
        sorted(
            by_case_id.values(),
            key=lambda result: (result.case_id, result.node_id),
        )
    )
    return _JunitResult(ordered_results, tuple(problems))


def _junit_node_id(test_case: ET.Element, name: str) -> str:
    classname = test_case.get("classname")
    return f"{classname}::{name}" if classname else name or "<unnamed-testcase>"


def _case_result(test_case: ET.Element, case_id: str, node_id: str) -> CaseResult:
    failure = test_case.find("failure")
    error = test_case.find("error")
    skipped = test_case.find("skipped")
    if error is not None:
        outcome = CaseOutcome.ERROR
        detail = error
    elif failure is not None and _is_import_failure(failure):
        # pytest can report an import performed inside the test body as a
        # <failure>, even though target execution never started.
        outcome = CaseOutcome.ERROR
        detail = failure
    elif failure is not None:
        outcome = CaseOutcome.FAILED
        detail = failure
    elif skipped is not None:
        outcome = CaseOutcome.SKIPPED
        detail = skipped
    else:
        outcome = CaseOutcome.PASSED
        detail = None

    duration_ms = _duration_ms(test_case.get("time"))
    message = _junit_message(detail) if detail is not None else None
    if outcome is CaseOutcome.ERROR and message is None:
        message = "pytest reported an error without details"
    return CaseResult(
        case_id=case_id,
        node_id=node_id,
        outcome=outcome,
        duration_ms=duration_ms,
        message=message,
    )


def _is_import_failure(failure: ET.Element) -> bool:
    exception_type = failure.get("type", "").rsplit(".", 1)[-1]
    # pytest's JUnit writer may omit type and expose the exception class at
    # the start of the structured message attribute instead.
    message_type = failure.get("message", "").partition(":")[0].strip()
    return bool({exception_type, message_type} & _IMPORT_ERROR_TYPES)


def _duration_ms(raw_seconds: str | None) -> int:
    if raw_seconds is None:
        return 0
    try:
        seconds = float(raw_seconds)
    except ValueError:
        return 0
    if not math.isfinite(seconds) or seconds < 0:
        return 0
    return round(seconds * 1000)


def _junit_message(element: ET.Element) -> str | None:
    pieces = [element.get("message", "").strip(), (element.text or "").strip()]
    message = "\n".join(piece for piece in pieces if piece)
    return message[:8000] or None


def _output_bytes(output: bytes | str | None) -> bytes:
    if output is None:
        return b""
    if isinstance(output, bytes):
        return output
    return output.encode("utf-8", errors="replace")


def require_pytest() -> str:
    """Check this interpreter before creating output or starting the pytest executor."""
    try:
        version = importlib.metadata.version("pytest")
        if importlib.util.find_spec("pytest") is not None:
            return version
    except (importlib.metadata.PackageNotFoundError, ImportError, ValueError):
        pass
    raise RunnerDependencyError(
        "pytest runner is unavailable. Install evidenceguard[runner] in this Python environment: "
        'python -m pip install "evidenceguard[runner]"'
    ) from None
