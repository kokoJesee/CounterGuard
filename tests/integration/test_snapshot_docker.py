"""Only tool-owned histories enter the existing reviewed, pinned Docker runner."""

import importlib
import json
import os
from pathlib import Path

import pytest

from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import RunOutcome, RunRole
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.snapshot_admission import issue_snapshot_review
from counterguard.snapshot_execution import SnapshotSession
from tests.snapshot_support import assert_snapshot_attack_observed, snapshot_history

pytestmark = [pytest.mark.slow, pytest.mark.docker]


@pytest.fixture
def no_host_execution(monkeypatch):
    runner = resolve_runner(runner_id="root-pytest8", image_digest=None)
    value = os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST")
    if not value:
        pytest.skip("set COUNTERGUARD_RUNNER_IMAGE_DIGEST to the reviewed exact image ID")
    assert value == runner.image_digest

    def forbidden(*args, **kwargs):
        pytest.fail("candidate reached a local executor")

    monkeypatch.setattr(LocalTrustedExecutor, "execute", forbidden)
    original = importlib.import_module

    def guarded(name, *args, **kwargs):
        if name == "snapshot_sample" or name.startswith("snapshot_sample."):
            pytest.fail("snapshot package imported on host")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", guarded)


def session(tmp_path, repo, *, timeout=10.0):
    review = issue_snapshot_review(
        repo,
        tmp_path / "binding.json",
        kind="execution",
        reason="tool-owned full-package fixture, original oracles and pinned Docker reviewed",
        output=tmp_path / "review.json",
        timeout=timeout,
    )
    return SnapshotSession(
        repo, tmp_path, tmp_path / "binding.json", tmp_path / "review.json", review.artifact_digest
    )


def test_real_capture_minimal_guard_and_repeat_replay_with_large_full_snapshot(
    tmp_path, monkeypatch, no_host_execution
):
    monkeypatch.chdir(tmp_path)
    repo, binding = snapshot_history(tmp_path, large_media=True)
    engine = session(tmp_path, repo)
    evidence = engine.capture(evidence_id="evd_snapshot_fixture_v1", output=Path("capture"))
    assert evidence.reproduced and len(evidence.failing_case_ids) == 2
    assert evidence.buggy.run.pytest_exit_code == 1 and evidence.fixed.run.pytest_exit_code == 0
    assert len(evidence.buggy.run.case_results) == len(evidence.fixed.run.case_results) == 4
    assert engine.verify_evidence(tmp_path / "capture/evidence.json") == evidence
    guard = engine.compile(
        tmp_path / "capture/evidence.json", guard_id="grd_snapshot_fixture_v1", output=Path("guard")
    )
    assert guard.case_ids == evidence.failing_case_ids
    assert len(guard.buggy_check.run.case_results) == len(guard.fixed_check.run.case_results) == 2
    assert guard.state == "fixture_candidate_not_schedulable"
    counts = []
    for index in range(2):
        replay = engine.replay(
            tmp_path / "guard/guard.json",
            evidence_path=tmp_path / "capture/evidence.json",
            role="fixed",
            output=Path(f"replay-{index}"),
        )
        assert replay.execution.run.outcome is RunOutcome.PASSED
        assert replay.execution.run.role is RunRole.REPLAY
        assert replay.target_manifest_digest == binding.trees["fixed"].artifact_digest
        counts.append(tuple((c.case_id, c.outcome) for c in replay.execution.run.case_results))
    assert counts[0] == counts[1]
    sandbox = tmp_path / "capture/f/r/runs/run_snapshot/sandbox-input"
    assert (sandbox / "src/snapshot_sample/data.bin").stat().st_size == 1024 * 1024 + 1
    assert not (sandbox / "media.bin").exists()
    for omitted in ("conftest.py", "tests", "pyproject.toml", "setup.py"):
        assert not (sandbox / omitted).exists()
    # Re-signing changed claims cannot replace source reconstruction or raw JUnit.
    path = tmp_path / "capture/evidence.json"
    altered = json.loads(path.read_bytes())
    altered["failing_case_ids"].pop()
    altered["artifact_digest"] = digest_json_artifact(altered)
    path.write_bytes(canonical_json_bytes(altered))
    with pytest.raises(ArtifactIntegrityError):
        engine.verify_evidence(path)


@pytest.mark.parametrize(
    "behavior", ["network", "write", "environment", "timeout", "memory", "process"]
)
def test_attack_does_not_become_a_reproduced_bug(
    tmp_path, monkeypatch, no_host_execution, behavior
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COUNTERGUARD_HOST_SECRET", "must-not-enter-container")
    repo, _ = snapshot_history(tmp_path, behavior=behavior)
    engine = session(tmp_path, repo, timeout=2.0 if behavior == "timeout" else 10.0)
    value = engine.capture(evidence_id="evd_snapshot_attack_v1", output=Path("capture"))
    assert not value.reproduced and "fixed_did_not_pass" in value.rejection_reasons
    assert_snapshot_attack_observed(value.fixed.run, behavior)
    assert (tmp_path / "capture/f/r/record.json").is_file()
    assert engine.verify_evidence(tmp_path / "capture/evidence.json") == value
    with pytest.raises(ArtifactIntegrityError, match="not_reproduced"):
        engine.compile(
            tmp_path / "capture/evidence.json", guard_id="grd_rejected_v1", output=Path("forbidden")
        )
    assert not (tmp_path / "forbidden").exists()
