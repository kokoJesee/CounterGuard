"""Real CLI processes share the same immutable local registration and disable state."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from counterguard.registry import Registry
from tests.unit.test_integrity import captured  # noqa: F401
from tests.unit.test_registry import registered_inputs  # noqa: F401

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parents[2]


def test_separate_cli_processes_preserve_registration_and_terminal_disable(
    registered_inputs,  # noqa: F811
    monkeypatch,
    tmp_path,
):
    workspace, path, guard = registered_inputs
    monkeypatch.undo()  # The source-evidence fixture used controlled subprocess responses.
    root = tmp_path / "registry"

    def command(*args, code=0):
        result = subprocess.run(
            [sys.executable, "-m", "counterguard", "registry", *args, "--root", str(root)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == code, result.stderr
        return json.loads(result.stdout) if result.stdout.strip() else None

    first = command("add", str(path), "--cwd", str(workspace))
    assert command("add", str(path), "--cwd", str(workspace)) == first
    assert command("list", "--format", "json")[0]["schedulable"] is True
    assert command("show", guard.guard_id, "--with-evidence")["evidence"]["reproduced"]
    assert command("disable", guard.guard_id, "--reason", "review")["status"] == "disabled"
    assert command("add", str(path), "--cwd", str(workspace))["status"] == "disabled"
    (workspace / guard.validation_run.junit_ref).write_bytes(b"corrupt")
    damaged = command("show", guard.guard_id, code=5)
    assert damaged["integrity"] == "invalid" and damaged["schedulable"] is False
    assert Registry(root).list()[0]["status"] == "disabled"
