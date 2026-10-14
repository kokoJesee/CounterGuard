"""CLI smoke tests."""

import subprocess
import sys

import pytest
from typer.testing import CliRunner

from evidenceguard import __version__
from evidenceguard.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_capture_help_documents_required_inputs() -> None:
    result = runner.invoke(app, ["capture", "--help"])
    assert result.exit_code == 0
    assert "--buggy-target" in result.stdout
    assert "--fixed-target" in result.stdout


def test_capture_rejects_invalid_id_without_traceback() -> None:
    result = runner.invoke(
        app,
        [
            "capture",
            "--evidence-id",
            "invalid",
            "--contract",
            "unused.json",
            "--test",
            "unused.py",
            "--buggy-target",
            "unused:target",
            "--fixed-target",
            "unused:target",
        ],
    )
    assert result.exit_code == 2
    assert "evidence_id" in result.stderr
    assert "Traceback" not in result.output


@pytest.mark.slow
def test_python_module_entrypoint_matches_console_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "evidenceguard", "version"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert result.stdout.strip() == __version__
