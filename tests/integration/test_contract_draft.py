"""Real committed tests are read as data, including tests in a blocked project."""

import json

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.contract_draft_models import ContractProposal
from tests.repository_support import git

pytestmark = pytest.mark.slow


def test_dirty_tree_and_conftest_do_not_execute_or_replace_committed_assertions(
    tmp_path, monkeypatch
):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "CounterGuard fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / "tests").mkdir()
    test = repo / "tests/test_price.py"
    test.write_text("""raise RuntimeError('never import this test')
from nonexistent.pricing import price
def test_price():
    assert price('glass') == 'glass'
    assert price(price('Glasses')) == 'Glass'
""")
    (repo / "tests/conftest.py").write_text("raise RuntimeError('never load conftest')\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "static-only test fixture")
    test.write_text("raise RuntimeError('dirty test must not be read')\n")
    monkeypatch.chdir(tmp_path)
    values = []
    for output in ("one", "two"):
        result = CliRunner().invoke(
            app,
            [
                "contract",
                "draft",
                "--repo",
                str(repo),
                "--revision",
                "HEAD",
                "--test-ref",
                "tests/test_price.py",
                "--test-function",
                "test_price",
                "--target",
                "nonexistent.pricing:price",
                "--output",
                output,
            ],
        )
        assert result.exit_code == 4, result.output
        proposal = ContractProposal.model_validate_json(
            (tmp_path / output / "proposal.json").read_bytes()
        )
        assert proposal.status == "partial" and len(proposal.cases) == 1
        assert len(proposal.unsupported) == 1 and proposal.source_assertions == 2
        assert proposal.human_review_required and not proposal.execution_allowed
        values.append(json.loads(result.stdout))
    assert values[0] == values[1]
