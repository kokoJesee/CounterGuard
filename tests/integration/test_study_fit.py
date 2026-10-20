"""Actual target Git snapshots; source verifier is explicitly a unit double here."""

from pathlib import Path

import pytest

import counterguard.study_fit as fit_module
from counterguard.study_fit import StudyFitSession, issue_fit_review
from tests.repository_support import git
from tests.study_fit_support import prepare_training
from tests.unit.test_study_fit import source_fixture

pytestmark = pytest.mark.slow


def test_real_git_training_ignores_dirty_targets_and_rebuilds_without_execution(
    tmp_path, monkeypatch
):
    source_repo = tmp_path / "source-double"
    source_repo.mkdir()
    source = source_fixture(source_repo)
    monkeypatch.setattr(fit_module, "inspect_source", lambda *a, **kw: (source, None, ()))

    def commit_files(name, files):
        repo = tmp_path / ("repo-" + name)
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "CounterGuard fixture")
        git(repo, "config", "user.email", "fixture@example.invalid")
        for ref, raw in files.items():
            path = repo / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        git(repo, "add", ".")
        git(repo, "commit", "-m", "tool-owned static training fixture")
        return repo, git(repo, "rev-parse", "HEAD")

    _, _, repositories, _ = prepare_training(tmp_path, source, commit_files)
    review = issue_fit_review(
        source_repo,
        tmp_path,
        "protocol.json",
        output_ref="review.json",
        operator="fixture reviewer",
        reason="Fixed actual Git training trees, manual fixture labels",
    )
    session = StudyFitSession(source_repo, tmp_path, repositories, review.artifact_digest)
    first = session.fit("protocol.json", "review.json", phase="refined", output=Path("fit.json"))
    for repo in repositories.values():
        (repo / "src/fixture_target/core.py").write_text(
            "raise RuntimeError('dirty source must never load')\n", encoding="utf-8"
        )
        (repo / "conftest.py").write_text(
            "raise RuntimeError('bootstrap must never load')\n", encoding="utf-8"
        )
    repeated = session.fit("protocol.json", "review.json", phase="refined")
    assert repeated == first
    assert session.verify(Path("fit.json")) == first
    assert first.learning.training_confusion.tp == first.learning.training_confusion.tn == 2
    assert len(first.scope.clauses) == 2 and not first.execution_allowed
