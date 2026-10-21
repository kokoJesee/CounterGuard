"""Real independent fixture comparison; no external repositories or research labels."""

import importlib
import os
from dataclasses import replace
from pathlib import Path

import pytest

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import RunOutcome
from counterguard.runner_catalog import resolve_runner
from counterguard.runners import docker
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.snapshot_admission import issue_snapshot_review, seal
from counterguard.snapshot_comparison import SnapshotComparisonSession
from counterguard.snapshot_comparison_data import (
    create_comparison_map,
    inspect_snapshot_target,
    issue_comparison_review,
)
from counterguard.snapshot_comparison_models import (
    SnapshotComparisonPlan,
    SnapshotOwnWitness,
    SnapshotTargetEntry,
)
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_models import ZERO
from tests.snapshot_comparison_support import comparison_target_history
from tests.snapshot_support import snapshot_history

pytestmark = [pytest.mark.slow, pytest.mark.docker]


def test_real_independent_guard_own_witness_skip_and_late_input_change(tmp_path, monkeypatch):
    runner = resolve_runner(runner_id="root-pytest8", image_digest=None)
    if not os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST"):
        pytest.skip("set COUNTERGUARD_RUNNER_IMAGE_DIGEST to the reviewed exact image ID")
    assert os.environ["COUNTERGUARD_RUNNER_IMAGE_DIGEST"] == runner.image_digest
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        LocalTrustedExecutor, "execute", lambda *a, **k: pytest.fail("local fallback")
    )
    original_import = importlib.import_module

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"snapshot_sample", "research_target"}:
            pytest.fail("candidate imported on host")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", guarded)
    actual_runs = []
    original_bounded = docker._run_bounded

    def bounded(argv, **kwargs):
        if len(argv) > 1 and argv[1] == "run":
            actual_runs.append(argv)
        return original_bounded(argv, **kwargs)

    monkeypatch.setattr(docker, "_run_bounded", bounded)
    repo, binding = snapshot_history(tmp_path)
    review = issue_snapshot_review(
        repo,
        tmp_path / "binding.json",
        kind="execution",
        reason="tool-owned source snapshot and original test reviewed",
        output=tmp_path / "source-review.json",
    )
    source = SnapshotSession(
        repo,
        tmp_path,
        tmp_path / "binding.json",
        tmp_path / "source-review.json",
        review.artifact_digest,
    )
    evidence = source.capture(
        evidence_id="evd_comparison_fixture_v1", output=Path("source-capture")
    )
    assert evidence.reproduced
    guard = source.compile(
        tmp_path / "source-capture/evidence.json",
        guard_id="grd_comparison_fixture_v1",
        output=Path("source-guard"),
    )
    assert len(guard.case_ids) == 2 and len(actual_runs) == 4
    target_repo, revision = comparison_target_history(tmp_path)
    target, _ = inspect_snapshot_target(
        target_repo,
        revision,
        target_id="independent",
        entry=SnapshotTargetEntry(
            target_module="research_target",
            target_symbol="normalize",
            source_ref="src/research_target/__init__.py",
            import_root="src",
        ),
        license_ref="LICENSE",
        interface_kind="value_return",
        interface_basis_ref="README.md",
        output=tmp_path / "target.json",
    )
    mapping = create_comparison_map(guard, binding.contract, target)
    write_immutable(tmp_path / "map.json", canonical_json_bytes(mapping))
    cases = tuple(c for c in binding.contract.cases if c.case_id in guard.case_ids)
    witness = seal(
        SnapshotOwnWitness(
            target_digest=target.artifact_digest,
            map_digest=mapping.artifact_digest,
            basis_refs=("README.md",),
            cases=tuple(c.model_copy(update={"exception_match": "own API rejects"}) for c in cases),
            artifact_digest=ZERO,
        )
    )
    write_immutable(tmp_path / "witness.json", canonical_json_bytes(witness))
    plan = seal(
        SnapshotComparisonPlan(
            evidence_ref="source-capture/evidence.json",
            guard_ref="source-guard/guard.json",
            target_ref="target.json",
            map_ref="map.json",
            witness_ref="witness.json",
            review_ref="comparison-review.json",
            method="b1_always",
            artifact_digest=ZERO,
        )
    )
    comparison_review = issue_comparison_review(
        source,
        target_repo,
        plan,
        output=tmp_path / "comparison-review.json",
        reason=(
            "all original inputs and source oracle preserved; "
            "target has independent exception-message policy"
        ),
        source_interface="value_return",
        source_interface_basis_ref="src/snapshot_sample/core.py",
    )
    engine = SnapshotComparisonSession(source, target_repo, comparison_review.artifact_digest)
    repeated = []
    for index in range(2):
        result = engine.run(plan, output=f"guard-{index}")
        assert result.outcome == "test_failed" and result.run.outcome is RunOutcome.TEST_FAILED
        assert len(result.run.case_results) == 2
        assert engine.verify(tmp_path / f"guard-{index}/replay.json") == result
        repeated.append(tuple((c.case_id, c.outcome) for c in result.run.case_results))
    assert repeated[0] == repeated[1]
    own_plan = seal(plan.model_copy(update={"lane": "own_contract"}))
    own = engine.run(own_plan, output="own")
    assert own.outcome == "passed" and len(own.run.case_results) == 2
    assert engine.verify(tmp_path / "own/replay.json") == own
    b2 = seal(plan.model_copy(update={"method": "b2_interface"}))
    assert engine.run(b2, output="b2").outcome == "test_failed"
    assert len(actual_runs) == 8
    for method in ("learned_initial", "learned_refined"):
        result = engine.run(seal(plan.model_copy(update={"method": method})), output=method)
        assert result.admission.decision == "unknown" and result.run is None
        assert result.outcome == "skipped_unknown"
        assert engine.verify(tmp_path / method / "replay.json") == result
    assert len(actual_runs) == 8
    bad_anchor = replace(engine, review_anchor=ZERO)
    with pytest.raises(ArtifactIntegrityError):
        bad_anchor.run(plan, output="bad-anchor")
    assert not (tmp_path / "bad-anchor").exists() and len(actual_runs) == 8
    stdout_repo, stdout_revision = comparison_target_history(
        tmp_path, name="stdout-target", stdout=True
    )
    stdout_target, _ = inspect_snapshot_target(
        stdout_repo,
        stdout_revision,
        target_id="stdout",
        entry=target.entry,
        license_ref="LICENSE",
        interface_kind="stdout_write",
        interface_basis_ref="README.md",
        output=tmp_path / "stdout-target.json",
    )
    stdout_map = create_comparison_map(guard, binding.contract, stdout_target)
    write_immutable(tmp_path / "stdout-map.json", canonical_json_bytes(stdout_map))
    stdout_plan = seal(
        plan.model_copy(
            update={
                "target_ref": "stdout-target.json",
                "map_ref": "stdout-map.json",
                "witness_ref": None,
                "review_ref": "stdout-review.json",
                "method": "b2_interface",
            }
        )
    )
    stdout_review = issue_comparison_review(
        source,
        stdout_repo,
        stdout_plan,
        output=tmp_path / "stdout-review.json",
        reason="tool-owned stdout interface differs from source value return",
        source_interface="value_return",
        source_interface_basis_ref="src/snapshot_sample/core.py",
    )
    stdout_engine = SnapshotComparisonSession(source, stdout_repo, stdout_review.artifact_digest)
    skipped = stdout_engine.run(stdout_plan, output="b2-skip")
    assert (
        skipped.outcome == "skipped_inapplicable" and skipped.run is None and len(actual_runs) == 8
    )
    assert stdout_engine.verify(tmp_path / "b2-skip/replay.json") == skipped
    # Changing an execution input after the actual run must retain the Run, mark
    # stale and refuse verification. Other completed results are left untouched.
    from counterguard import snapshot_comparison as module

    original_execute = module._execute_with_adapter

    def late_change(request, adapter):
        run = original_execute(request, adapter)
        request.test_path.write_bytes(request.test_path.read_bytes() + b"\n# late changed input\n")
        return run

    monkeypatch.setattr(module, "_execute_with_adapter", late_change)
    late = engine.run(plan, output="late")
    assert late.integrity == "stale" and late.run is not None and late.outcome == "integrity_error"
    assert (tmp_path / late.record_ref).is_file() and len(actual_runs) == 9
    with pytest.raises(ArtifactIntegrityError):
        engine.verify(tmp_path / "late/replay.json")
    sandbox = tmp_path / "guard-0/runtime/r/runs/run_comparison/sandbox-input"
    assert (sandbox / "src/research_target/resource.txt").is_file()
    assert (sandbox / "cg_control/contract.json").read_bytes() == (
        repo / "contracts/range.json"
    ).read_bytes()
    assert not (sandbox / "src/snapshot_sample").exists() and not (sandbox / "conftest.py").exists()
    assert not (sandbox / "pyproject.toml").exists()
