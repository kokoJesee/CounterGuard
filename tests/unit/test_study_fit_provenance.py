"""Full source verification with Git/transport-shaped doubles; no real target run."""

from dataclasses import replace
from pathlib import Path

import pytest

from counterguard.digests import digest_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.study_data import inspect_source
from counterguard.study_fit import StudyFitSession, issue_fit_review
from tests.study_fit_support import prepare_training
from tests.unit.test_bootstrap_binding import pins
from tests.unit.test_bootstrap_binding import repository as repository
from tests.unit.test_standalone_capture import capture_inputs as capture_inputs
from tests.unit.test_standalone_capture import resign
from tests.unit.test_standalone_guard import compile_fixture
from tests.unit.test_standalone_guard import guard_inputs as guard_inputs

pytestmark = pytest.mark.slow  # Deep provenance setup, even though processes are doubles.


@pytest.fixture
def source_training(guard_inputs, monkeypatch):
    import counterguard.study_data as data

    source_repo, _, _, _, calls, workspace, _ = guard_inputs
    compile_fixture(source_repo)
    source, _, _ = inspect_source(source_repo, workspace, "g/guard.json", source_id="source")
    trees = {}

    def commit_files(name, files):
        repo = workspace / ("target-" + name)
        repo.mkdir()
        revision = digest_bytes(name.encode()).split(":")[1][:40]
        trees[repo.resolve()] = (revision, files, pins(files))
        return repo, revision

    monkeypatch.setattr(data, "read_committed_files", lambda repo, rev: trees[repo.resolve()])
    _, _, repositories, _ = prepare_training(workspace, source, commit_files)
    review = issue_fit_review(
        source_repo,
        workspace,
        "protocol.json",
        output_ref="review.json",
        operator="fixture reviewer",
        reason="Reviewed source-chain and fixed synthetic cohort",
    )
    return StudyFitSession(source_repo, workspace, repositories, review.artifact_digest), calls


def test_complete_source_chain_rebuilds_both_phases_without_new_execution(source_training):
    session, calls = source_training
    before = len(calls)
    assert before == 4  # Synthetic B/F and Guard self-check transport envelopes only.
    initial = session.fit(
        "protocol.json", "review.json", phase="initial", output=Path("fit-initial.json")
    )
    refined = session.fit(
        "protocol.json", "review.json", phase="refined", output=Path("fit-refined.json")
    )
    assert len(initial.scope.clauses) == 1 and len(refined.scope.clauses) == 2
    assert session.verify(Path("fit-refined.json")) == refined
    assert len(calls) == before


def test_guard_resigning_cannot_replace_verified_source_history(source_training):
    session, _ = source_training
    resign(session.workspace / "g/guard.json", lambda row: row.update(case_ids=[]))
    with pytest.raises((ArtifactIntegrityError, ValueError)):
        session.fit("protocol.json", "review.json", phase="initial")


def test_source_repository_substitution_does_not_rebuild_chain(source_training):
    session, _ = source_training
    alternate = session.workspace / "alternate-source"
    alternate.mkdir()
    # Same source files/declared commit IDs still cannot substitute local repository identity.
    with pytest.raises(ArtifactIntegrityError, match="source_not_rebuilt"):
        replace(session, source_repo=alternate).fit("protocol.json", "review.json", phase="initial")
