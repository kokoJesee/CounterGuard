"""Missing optional execution dependencies fail at public boundaries."""

import importlib.metadata
import importlib.util
import subprocess

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.errors import RunnerDependencyError
from counterguard.execution import run_pytest
from tests.unit.test_execution import _request


@pytest.fixture(params=["metadata", "module"])
def missing_runner(monkeypatch, request):
    if request.param == "metadata":
        installed_distribution = importlib.metadata.distribution

        def distribution(name):
            if name == "pytest":
                raise importlib.metadata.PackageNotFoundError(name)
            return installed_distribution(name)

        monkeypatch.setattr(importlib.metadata, "distribution", distribution)
    else:
        installed_spec = importlib.util.find_spec

        def find_spec(name, *args, **kwargs):
            return None if name == "pytest" else installed_spec(name, *args, **kwargs)

        monkeypatch.setattr(importlib.util, "find_spec", find_spec)


@pytest.mark.parametrize("command", ["demo", "pipeline"])
def test_missing_pytest_gives_install_hint_before_output(tmp_path, missing_runner, command):
    args = [command]
    if command == "pipeline":
        args += ["run", "--scenario", "examples/demo/mvp.yaml"]
    result = CliRunner().invoke(app, args + ["--cwd", str(tmp_path), "--workspace", "out"])
    assert result.exit_code == 3, repr(result.exception)
    assert "counterguard[runner]" in result.stderr
    assert "Traceback" not in result.output
    assert not (tmp_path / "out").exists()


def test_executor_missing_pytest_never_launches_or_publishes(tmp_path, missing_runner, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Missing runner must be detected before subprocess execution")

    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(RunnerDependencyError, match=r"counterguard\[runner\]"):
        run_pytest(_request(tmp_path))
    assert not (tmp_path / "artifacts").exists()


def test_base_install_can_still_show_cli_version(missing_runner):
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"
