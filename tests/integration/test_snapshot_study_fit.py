"""Real B/F/H, Docker source evidence and complete Git training; tool-owned only."""

import importlib
import os
from pathlib import Path

import pytest

from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import _AdmittedDockerProcess
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.snapshot_admission import issue_snapshot_review
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_study_fit import (
    SnapshotStudyFitSession,
    inspect_snapshot_study_source,
    issue_snapshot_study_fit_review,
)
from tests.repository_support import git
from tests.snapshot_study_support import prepare_snapshot_training
from tests.snapshot_support import snapshot_history

pytestmark = [pytest.mark.slow, pytest.mark.docker]


def test_full_source_fit(tmp_path, monkeypatch):
    runner = resolve_runner(runner_id="root-pytest8", image_digest=None)
    image = os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST")
    if not image:
        pytest.skip("set COUNTERGUARD_RUNNER_IMAGE_DIGEST to the reviewed exact image ID")
    assert image == runner.image_digest
    monkeypatch.chdir(tmp_path)
    original_import = importlib.import_module

    def import_guard(name, *args, **kwargs):
        assert name.split(".")[0] not in {"snapshot_sample", "snapshot_target"}
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", import_guard)
    monkeypatch.setattr(
        LocalTrustedExecutor, "execute", lambda *a, **k: pytest.fail("local target fallback")
    )
    starts = []
    original_process = _AdmittedDockerProcess.execute_process

    def counted(self, request, prepared):
        starts.append(request.target.module)
        return original_process(self, request, prepared)

    monkeypatch.setattr(_AdmittedDockerProcess, "execute_process", counted)
    source_repo, binding = snapshot_history(tmp_path)
    execution_review = issue_snapshot_review(
        source_repo,
        tmp_path / "binding.json",
        kind="execution",
        reason="Tool-owned complete snapshot, original test and Docker inputs reviewed",
        output=tmp_path / "execution.json",
    )
    engine = SnapshotSession(
        source_repo,
        tmp_path,
        tmp_path / "binding.json",
        tmp_path / "execution.json",
        execution_review.artifact_digest,
    )
    evidence = engine.capture(evidence_id="evd_snapshot_study", output=Path("c"))
    assert evidence.reproduced
    guard = engine.compile(
        tmp_path / "c/evidence.json", guard_id="grd_snapshot_study", output=Path("g")
    )
    source = inspect_snapshot_study_source(
        engine,
        evidence_ref="c/evidence.json",
        guard_ref="g/guard.json",
        source_id="snapshot-source",
    )
    assert source.guard_digest == guard.artifact_digest
    assert source.head_commit == binding.head_commit and len(starts) == 4

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
        git(repo, "add", "--", *files)
        git(repo, "commit", "-m", "tool-owned complete snapshot training fixture")
        return repo, git(repo, "rev-parse", "HEAD")

    _, _, repositories, _ = prepare_snapshot_training(tmp_path, source, commit_files)
    review = issue_snapshot_study_fit_review(
        engine,
        "protocol.json",
        output_ref="fit-review.json",
        operator="fixture reviewer",
        reason="Fixed complete source/targets and explicit synthetic labels before fitting",
    )
    session = SnapshotStudyFitSession(engine, repositories, review.artifact_digest)
    initial = session.fit(
        "protocol.json", "fit-review.json", phase="initial", output="initial.json"
    )
    refined = session.fit(
        "protocol.json", "fit-review.json", phase="refined", output="refined.json"
    )
    assert len(initial.scope.clauses) == 1 and len(refined.scope.clauses) == 2
    assert session.verify("initial.json") == initial
    assert session.verify("refined.json") == refined
    for repo in repositories.values():
        (repo / "src/snapshot_target/core.py").write_text(
            "raise RuntimeError('dirty tree must not execute')\n", encoding="utf-8"
        )
        (repo / "conftest.py").write_text(
            "raise RuntimeError('dirty bootstrap must not load')\n", encoding="utf-8"
        )
    assert session.fit("protocol.json", "fit-review.json", phase="refined") == refined
    assert len(starts) == 4  # No fitting, source verify or dirty target invokes Docker.
