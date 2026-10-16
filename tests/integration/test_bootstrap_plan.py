"""Real Git reads must retain excluded bootstrap files without loading them."""

import json

import pytest
from typer.testing import CliRunner

from counterguard.bootstrap_plan import plan_bootstrap
from counterguard.cli import app
from tests.repository_support import git

pytestmark = pytest.mark.slow


def test_committed_closure_and_test_projection_ignore_dirty_tree_not_committed_conftest(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "CounterGuard fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    package = repo / "src/sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("raise RuntimeError('never load package')\n")
    (package / "core.py").write_text("def price(x): return x + 1\n")
    tests = repo / "tests"
    tests.mkdir()
    (tests / "conftest.py").write_text("raise RuntimeError('never load bootstrap')\n")
    (tests / "test_core.py").write_text(
        "raise RuntimeError('never import tests')\nfrom sample.core import price\n"
        "def test_price(): assert price(1) == 2\n"
    )
    (repo / "pyproject.toml").write_text('[project]\nname="sample"\ndependencies=[]\n')
    git(repo, "add", ".")
    git(repo, "commit", "-m", "readonly planning fixture")
    (tests / "conftest.py").unlink()
    (package / "core.py").write_text("import undeclared_library\n")
    monkeypatch.chdir(tmp_path)
    args = [
        "bootstrap",
        "plan",
        "--repo",
        str(repo),
        "--revision",
        "HEAD",
        "--target",
        "sample.core:price",
        "--import-root",
        "src",
        "--test-ref",
        "tests/test_core.py",
        "--test-function",
        "test_price",
        "--output",
        "first",
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 4, result.output
    value = json.loads(result.stdout)
    assert value["status"] == "review_required" and not value["execution_allowed"]
    assert any(pin["path"] == "tests/conftest.py" for pin in value["files"])
    assert not value["target_closure"]["findings"]
    assert value["test_projection"]["cases"][0]["expected"]["value"] == 2
    repeat = plan_bootstrap(
        repo,
        "HEAD",
        target="sample.core:price",
        import_root="src",
        test_ref="tests/test_core.py",
        test_function="test_price",
        output=tmp_path / "second",
    )
    assert repeat == value
    assert (tmp_path / "first/plan.json").read_bytes() == (
        tmp_path / "second/plan.json"
    ).read_bytes()
