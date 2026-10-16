"""Actual Git tree inspection, with no local execution of target Python."""

import json

import pytest
from typer.testing import CliRunner

from counterguard.admission import admission_repository
from counterguard.cli import app
from tests.repository_support import git

pytestmark = pytest.mark.slow


def test_committed_src_project_and_hidden_conftest(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "CounterGuard fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / "pyproject.toml").write_text('[project]\nname="example"\ndependencies=[]\n')
    source = repo / "src/sample"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("raise RuntimeError('never import candidate')\n")
    (source / "core.py").write_text("import math\ndef total(x): return math.ceil(x)\n")
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_core.py").write_text(
        "from sample.core import total\ndef test_total(): assert total(1) == 1\n"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "minimal static fixture")
    first = admission_repository(repo, "HEAD", import_root="src")
    assert first["status"] == "eligible_candidate" and first["execution_allowed"] is False
    assert first == admission_repository(repo, "HEAD", import_root="src")
    result = CliRunner().invoke(
        app,
        [
            "preflight",
            "--repo",
            str(repo),
            "--revision",
            "HEAD",
            "--profile",
            "minimal-python",
            "--import-root",
            "src",
        ],
    )
    assert result.exit_code == 0 and json.loads(result.stdout) == first
    (tests / "conftest.py").write_text("raise RuntimeError('never load')\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "add bootstrap blocker")
    (tests / "conftest.py").unlink()
    result = CliRunner().invoke(
        app,
        [
            "preflight",
            "--repo",
            str(repo),
            "--revision",
            "HEAD",
            "--profile",
            "minimal-python",
            "--import-root",
            "src",
        ],
    )
    assert result.exit_code == 4
    assert "repository_conftest" in result.stdout
