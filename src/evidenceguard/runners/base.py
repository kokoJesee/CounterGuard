"""Small execution seam shared by trusted-local and Docker adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from evidenceguard.models import RunOutcome

if TYPE_CHECKING:
    from evidenceguard.execution import PytestRunRequest
    from evidenceguard.models import RunRecord


class ExecutionBackend(Protocol):
    """Turn one fully described pytest request into an immutable run record."""

    def execute(self, request: PytestRunRequest) -> RunRecord: ...


@dataclass(frozen=True, slots=True)
class PreparedRun:
    run_id: str
    cwd: Path
    test_ref: str
    run_dir: Path
    config_ref: str
    stdout_path: Path
    stderr_path: Path
    junit_path: Path
    stdout_ref: str
    stderr_ref: str
    junit_ref: str
    known_case_ids: tuple[str, ...]
    contract_ref: str | None


@dataclass(frozen=True, slots=True)
class RawExecution:
    """Bounded raw process result before shared JUnit classification."""

    argv: tuple[str, ...]
    stdout: bytes
    stderr: bytes
    junit: bytes
    junit_produced: bool
    pytest_exit_code: int | None
    python_version: str
    pytest_version: str
    terminal_outcome: RunOutcome | None = None
    error_detail: str | None = None


class ProcessAdapter(Protocol):
    def execute_process(
        self, request: PytestRunRequest, prepared: PreparedRun
    ) -> RawExecution: ...
