"""Public reader failure behavior for bounded external Git process responses."""

import io
import json
import subprocess

import pytest

from counterguard.repository import read_repository


class Process:
    def __init__(self, mode):
        self.mode = mode
        self.returncode = 0 if mode != "error" else 128
        self.stdout = io.BytesIO(b"x" * (2 * 1024 * 1024 + 1) if mode == "overflow" else b"")
        self.stderr = io.BytesIO(
            b"password=private-needle /private/credentials" if mode == "error" else b""
        )
        self.killed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def wait(self, timeout=None):
        if self.mode == "timeout" and not self.killed:
            raise subprocess.TimeoutExpired("git", timeout)
        return self.returncode

    def kill(self):
        self.killed = True


@pytest.mark.parametrize(
    "mode,reason",
    [("overflow", "git_output_limit"), ("timeout", "git_timeout"), ("error", "git_read_failed")],
)
def test_output_timeout_and_private_stderr_never_become_ready(tmp_path, monkeypatch, mode, reason):
    metadata = tmp_path / ".git"
    (metadata / "objects").mkdir(parents=True)
    (metadata / "HEAD").write_text("a" * 40 + "\n", encoding="ascii")
    process = Process(mode)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    report = read_repository(tmp_path, "HEAD", "HEAD")
    assert report.status == "unknown" and report.reason_codes == (reason,)
    assert "private-needle" not in json.dumps(report.model_dump(mode="json"))
    if mode in {"overflow", "timeout"}:
        assert process.killed
