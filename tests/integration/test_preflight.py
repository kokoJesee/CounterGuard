"""A complete committed-tree preflight ignores dirty files and never imports code."""

import pytest

from counterguard.preflight import preflight_repository
from tests.repository_support import git

pytestmark = pytest.mark.slow


def test_deleted_working_tree_conftest_cannot_hide_committed_requirements(tmp_path):
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Fixture")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="fixture"\ndependencies=[]\n')
    (tmp_path / "library.py").write_text("raise RuntimeError('never import')\n")
    (tmp_path / "conftest.py").write_text("raise RuntimeError('never load')\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "fixture")
    commit = git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "conftest.py").unlink()
    before = (tmp_path / "library.py").read_bytes()
    first = preflight_repository(tmp_path, commit)
    second = preflight_repository(tmp_path, commit)
    assert first == second
    assert first["status"] == "blocked"
    assert "repository_conftest" in {x["code"] for x in first["findings"]}
    assert first["file_count"] == 3 and first["execution_allowed"] is False
    assert (tmp_path / "library.py").read_bytes() == before
    assert not (tmp_path / "conftest.py").exists()
