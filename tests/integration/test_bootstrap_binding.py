"""Actual committed B/F/H objects, without importing any candidate code."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.bootstrap_binding import bind_contract, prepare_contract, verify_binding
from counterguard.cli import app
from tests.repository_support import git

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("import_root", [".", "src"])
def test_prepare_commit_bind_and_rebuild_use_committed_objects_only(
    tmp_path,
    monkeypatch,
    import_root,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "CounterGuard fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    package = repo / ("sample" if import_root == "." else "src/sample")
    package.mkdir(parents=True)
    # Static provenance can pass for code that cannot successfully import. The
    # binding must not call this reproduced Evidence or execution approval.
    (package / "__init__.py").write_text("raise RuntimeError('never import candidate')\n")
    (package / "core.py").write_text("def price(x): return x\n")
    (repo / "tests").mkdir()
    (repo / "tests/conftest.py").write_text("raise RuntimeError('never load hook')\n")
    (repo / "pyproject.toml").write_text('[project]\nname="sample"\n')
    git(repo, "add", ".")
    git(repo, "commit", "-m", "buggy fixture")
    buggy = git(repo, "rev-parse", "HEAD")
    (package / "core.py").write_text("def price(x): return x+1\n")
    (repo / "tests/test_price.py").write_text(
        "raise RuntimeError('never execute test module')\nfrom sample.core import price\n"
        "def test_price():\n assert price(1) == 2\n assert price(price(1)) == 3\n"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixed fixture with regression")
    fixed = git(repo, "rev-parse", "HEAD")
    monkeypatch.chdir(tmp_path)
    prepared = CliRunner().invoke(
        app,
        [
            "contract",
            "prepare",
            "--repo",
            str(repo),
            "--buggy",
            buggy,
            "--fixed",
            fixed,
            "--contract-id",
            "price.v1",
            "--target",
            "sample.core:price",
            "--import-root",
            import_root,
            "--test-ref",
            "tests/test_price.py",
            "--test-function",
            "test_price",
            "--output",
            "prepared",
        ],
    )
    assert prepared.exit_code == 4, prepared.output
    assert json.loads(prepared.stdout)["human_review_required"]
    (repo / "contracts").mkdir()
    contract_bytes = Path("prepared/contract.json").read_bytes()
    (repo / "contracts/price.v1.json").write_bytes(contract_bytes)
    git(repo, "add", "contracts/price.v1.json")
    git(repo, "commit", "-m", "NOT upstream: task-owned contract fixture")
    head = git(repo, "rev-parse", "HEAD")
    # An external/dirty contract cannot substitute for the assertion-head blob.
    (repo / "contracts/price.v1.json").write_text("{}")
    (package / "core.py").write_text("import undeclared_dependency\n")
    (repo / "tests/conftest.py").unlink()
    result = CliRunner().invoke(
        app,
        [
            "bootstrap",
            "bind",
            "--repo",
            str(repo),
            "--head",
            head,
            "--contract-ref",
            "contracts/price.v1.json",
            "--output",
            "bound",
        ],
    )
    assert result.exit_code == 0, result.output
    value = json.loads(result.stdout)
    assert value["capture_input_status"] == "review_required"
    assert value["reproduced"] is None and not value["execution_allowed"]
    assert value["projection_coverage"]["source_assertions"] == 2
    assert value["projection_coverage"]["represented_assertions"] == 1
    assert verify_binding(repo, Path("bound/binding.json")) == value
    repeated = bind_contract(repo, head, "contracts/price.v1.json", output=Path("repeated"))
    assert value == repeated
    assert Path("bound/binding.json").read_bytes() == Path("repeated/binding.json").read_bytes()
    missing = bind_contract(repo, fixed, "contracts/price.v1.json", output=Path("missing"))
    assert missing["reason_code"] == "contract_missing_from_head"
    # Preparing again does not modify HEAD, user files or old outputs.
    prepare_contract(
        repo,
        buggy=buggy,
        fixed=fixed,
        contract_id="price.v1",
        target="sample.core:price",
        import_root=import_root,
        test_ref="tests/test_price.py",
        test_function="test_price",
        output=Path("prepared-again"),
    )
    assert contract_bytes == Path("prepared-again/contract.json").read_bytes()
    assert git(repo, "rev-parse", "HEAD") == head
