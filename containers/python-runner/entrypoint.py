"""PID 1 for the EvidenceGuard Python runner image; emits one bounded JSON envelope."""

from __future__ import annotations

import base64
import contextlib
import importlib.metadata
import json
import math
import os
import platform
import signal
import stat
import subprocess
import sys
import threading
import uuid
from pathlib import Path, PurePosixPath

WORKSPACE = Path("/workspace")
RESPONSE_SCHEMA = "docker-runner-response.v1"
REQUEST_KEYS = {
    "schema_version",
    "test_ref",
    "contract_ref",
    "target_module",
    "target_symbol",
    "timeout_seconds",
    "stdout_limit_bytes",
    "stderr_limit_bytes",
    "junit_limit_bytes",
}


def _request(encoded: str) -> dict[str, object]:
    if len(encoded) > 65536:
        raise ValueError("request_too_large")
    try:
        raw = base64.b64decode(encoded.encode("ascii"), altchars=b"-_", validate=True)
        value = json.loads(raw)
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid_request_encoding") from error
    if not isinstance(value, dict):
        raise ValueError("invalid_request_fields")
    version = value.get("schema_version")
    keys = REQUEST_KEYS | ({"import_root"} if version == "docker-runner-request.v2" else set())
    if set(value) != keys:
        raise ValueError("invalid_request_fields")
    if version not in {"docker-runner-request.v1", "docker-runner-request.v2"}:
        raise ValueError("unsupported_request_schema")
    if version == "docker-runner-request.v2" and value["import_root"] not in {".", "src"}:
        raise ValueError("invalid_import_root")
    for key in ("test_ref", "contract_ref"):
        if not isinstance(value[key], str):
            raise ValueError("invalid_request_path")
        _workspace_file(value[key])
    for key in ("target_module", "target_symbol"):
        if not isinstance(value[key], str) or not value[key] or len(value[key]) > 256:
            raise ValueError("invalid_target_identity")
    timeout = value["timeout_seconds"]
    if type(timeout) not in {int, float} or not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError("invalid_timeout")
    for key in ("stdout_limit_bytes", "stderr_limit_bytes", "junit_limit_bytes"):
        limit = value[key]
        if type(limit) is not int or not 1 <= limit <= 4 * 1024 * 1024:
            raise ValueError("invalid_output_limit")
    return value


def _workspace_file(ref: str) -> Path:
    path = PurePosixPath(ref)
    if (
        not ref
        or "\\" in ref
        or path.is_absolute()
        or ".." in path.parts
        or str(path) != ref
    ):
        raise ValueError("invalid_request_path")
    resolved = (WORKSPACE / ref).resolve(strict=True)
    if not resolved.is_relative_to(WORKSPACE) or not resolved.is_file():
        raise ValueError("invalid_request_path")
    return resolved


def _bounded_process(
    argv: tuple[str, ...],
    *,
    environment: dict[str, str],
    timeout: float,
    stdout_limit: int,
    stderr_limit: int,
) -> tuple[int | None, bytes, bytes, bool, str | None]:
    buffers = [bytearray(), bytearray()]
    overflow = [None]
    process = subprocess.Popen(
        argv,
        cwd=WORKSPACE,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        shell=False,
    )

    def kill_group() -> None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)

    def consume(stream, index: int, maximum: int, label: str) -> None:
        while chunk := stream.read(8192):
            available = maximum - len(buffers[index])
            if available <= 0 or len(chunk) > available:
                if available > 0:
                    buffers[index].extend(chunk[:available])
                overflow[0] = label + "_limit_exceeded"
                kill_group()
                return
            buffers[index].extend(chunk)

    threads = [
        threading.Thread(
            target=consume, args=(process.stdout, 0, stdout_limit, "stdout"), daemon=True
        ),
        threading.Thread(
            target=consume, args=(process.stderr, 1, stderr_limit, "stderr"), daemon=True
        ),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_group()
        process.wait(timeout=3)
    finally:
        for thread in threads:
            thread.join(timeout=1)
    return process.returncode, bytes(buffers[0]), bytes(buffers[1]), timed_out, overflow[0]


def _regular_file(path: Path, limit: int) -> tuple[bytes, bool, str | None]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return b"", False, None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        return b"", False, "invalid_junit_file"
    with path.open("rb") as stream:
        body = stream.read(limit + 1)
    if len(body) > limit:
        return body[:limit], True, "junit_limit_exceeded"
    return body, True, None


def _response(
    *,
    exit_code: int | None,
    stdout: bytes,
    stderr: bytes,
    junit: bytes,
    junit_produced: bool,
    timed_out: bool,
    error_code: str | None,
) -> dict[str, object]:
    try:
        pytest_version = importlib.metadata.version("pytest")
    except importlib.metadata.PackageNotFoundError:
        pytest_version = "unavailable"
    return {
        "schema_version": RESPONSE_SCHEMA,
        "pytest_exit_code": exit_code,
        "timed_out": timed_out,
        "error_code": error_code,
        "junit_produced": junit_produced,
        "stdout_b64": base64.b64encode(stdout).decode("ascii"),
        "stderr_b64": base64.b64encode(stderr).decode("ascii"),
        "junit_b64": base64.b64encode(junit).decode("ascii"),
        "python_version": platform.python_version(),
        "pytest_version": pytest_version,
    }


def _run(value: dict[str, object]) -> dict[str, object]:
    run_dir = Path("/tmp") / ("evidenceguard-" + uuid.uuid4().hex)
    run_dir.mkdir(mode=0o700)
    home = run_dir / "home"
    home.mkdir(mode=0o700)
    config = run_dir / "pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    junit_path = run_dir / "junit.xml"
    environment = {
        "EVIDENCEGUARD_TARGET": str(value["target_module"]),
        "EVIDENCEGUARD_SYMBOL": str(value["target_symbol"]),
        "EVIDENCEGUARD_CONTRACT": str(value["contract_ref"]),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": "/workspace/src" if value.get("import_root") == "src" else "/workspace",
        "PYTHONUTF8": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "TMPDIR": str(run_dir),
    }
    argv = (
        sys.executable,
        "-m",
        "pytest",
        str(_workspace_file(str(value["test_ref"]))),
        "-c",
        str(config),
        "--noconftest",
        "-p",
        "no:cacheprovider",
        "-q",
        "--capture=no",
        "--basetemp",
        str(run_dir / "pytest"),
        "--junitxml",
        str(junit_path),
    )
    exit_code, stdout, stderr, timed_out, error_code = _bounded_process(
        argv,
        environment=environment,
        timeout=float(value["timeout_seconds"]),
        stdout_limit=int(value["stdout_limit_bytes"]),
        stderr_limit=int(value["stderr_limit_bytes"]),
    )
    junit, produced, junit_error = _regular_file(
        junit_path, int(value["junit_limit_bytes"])
    )
    return _response(
        exit_code=None if timed_out else exit_code,
        stdout=stdout,
        stderr=stderr,
        junit=junit,
        junit_produced=produced,
        timed_out=timed_out,
        error_code=error_code or junit_error,
    )


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise ValueError("expected_one_request")
        response = _run(_request(sys.argv[1]))
    except Exception as error:
        response = _response(
            exit_code=None,
            stdout=b"",
            stderr=b"",
            junit=b"",
            junit_produced=False,
            timed_out=False,
            error_code=(str(error) or "runner_internal_error")[:128],
        )
    body = json.dumps(response, sort_keys=True, separators=(",", ":")).encode("utf-8")
    os.write(sys.stdout.fileno(), body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
