"""Trusted local pytest adapter retained for the frozen MVP workflows."""

from __future__ import annotations

import platform
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace

from evidenceguard.models import RunOutcome
from evidenceguard.runners.base import PreparedRun, RawExecution

ProcessRunner = Callable[..., subprocess.CompletedProcess[bytes]]


@dataclass(frozen=True, slots=True)
class LocalTrustedExecutor:
    """Run only caller-trusted workspaces in the current Python environment."""

    process_runner: ProcessRunner = subprocess.run
    _pytest_version: str | None = None

    def execute(self, request):
        from evidenceguard.execution import _execute_with_adapter, require_pytest

        adapter = replace(self, _pytest_version=require_pytest())
        return _execute_with_adapter(request, adapter)

    def execute_process(
        self,
        request,
        prepared: PreparedRun,
    ) -> RawExecution:
        from evidenceguard.execution import _controlled_environment

        if self._pytest_version is None:
            raise RuntimeError(
                "LocalTrustedExecutor must preflight pytest before preparing outputs"
            )
        pytest_version = self._pytest_version
        argv = (
            sys.executable,
            "-m",
            "pytest",
            prepared.test_ref,
            "-c",
            prepared.config_ref,
            "--noconftest",
            "-q",
            "--junitxml",
            prepared.junit_ref,
        )
        environment = _controlled_environment(request.target, prepared.contract_ref)
        try:
            completed = self.process_runner(
                argv,
                cwd=prepared.cwd,
                env=environment,
                capture_output=True,
                timeout=request.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            return RawExecution(
                argv=argv,
                stdout=_output_bytes(error.stdout),
                stderr=_output_bytes(error.stderr),
                junit=_read_optional(prepared.junit_path),
                junit_produced=prepared.junit_path.is_file(),
                pytest_exit_code=None,
                terminal_outcome=RunOutcome.TIMEOUT,
                error_detail=f"pytest exceeded timeout of {request.timeout_seconds:g} seconds",
                python_version=platform.python_version(),
                pytest_version=pytest_version,
            )
        except OSError as error:
            detail = f"could not launch pytest: {type(error).__name__}"
            return RawExecution(
                argv=argv,
                stdout=b"",
                stderr=(detail + f": {error}").encode("utf-8", errors="replace"),
                junit=_read_optional(prepared.junit_path),
                junit_produced=prepared.junit_path.is_file(),
                pytest_exit_code=None,
                terminal_outcome=RunOutcome.LAUNCH_ERROR,
                error_detail=detail,
                python_version=platform.python_version(),
                pytest_version=pytest_version,
            )
        junit_produced = prepared.junit_path.is_file()
        return RawExecution(
            argv=argv,
            stdout=_output_bytes(completed.stdout),
            stderr=_output_bytes(completed.stderr),
            junit=_read_optional(prepared.junit_path),
            junit_produced=junit_produced,
            pytest_exit_code=completed.returncode,
            python_version=platform.python_version(),
            pytest_version=pytest_version,
        )


def _read_optional(path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return b""


def _output_bytes(output: bytes | str | None) -> bytes:
    if output is None:
        return b""
    if isinstance(output, bytes):
        return output
    return output.encode("utf-8", errors="replace")
