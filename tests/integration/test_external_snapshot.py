"""Qualify external-purpose code only on tool-owned, unmarked Git/Docker fixtures."""

import importlib
import os
from dataclasses import replace

import pytest
from pydantic import ValidationError

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.external_snapshot import (
    ExternalSnapshotSession,
    issue_external_snapshot_review,
    verify_external_snapshot_review,
)
from counterguard.external_snapshot_comparison import (
    ExternalSnapshotComparisonSession,
    create_external_snapshot_map,
    inspect_external_snapshot_target,
    issue_external_comparison_review,
)
from counterguard.external_snapshot_models import (
    ExternalComparisonPlan,
    ExternalSnapshotWitness,
)
from counterguard.models import RunOutcome
from counterguard.runner_catalog import resolve_runner
from counterguard.runners import docker
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.snapshot_admission import (
    FIXTURE_REF,
    issue_snapshot_review,
    read_value,
    seal,
)
from counterguard.snapshot_comparison_models import SnapshotComparisonReplay, SnapshotTargetEntry
from counterguard.snapshot_models import ZERO, SnapshotEvidence, SnapshotGuard, SnapshotReview
from tests.snapshot_comparison_support import comparison_target_history
from tests.snapshot_support import assert_snapshot_attack_observed, snapshot_history

pytestmark = pytest.mark.slow
LICENSE = "CounterGuard tool-authored fixture, not an external repository.\n"


def source_fixture(tmp_path, *, behavior="normal", timeout=10.0):
    repo, binding = snapshot_history(
        tmp_path, fixture_marker=False, license_text=LICENSE, behavior=behavior
    )
    review = issue_external_snapshot_review(
        repo,
        tmp_path / "binding.json",
        repository_url="https://github.com/tool-fixture/source",
        license_ref="LICENSE",
        reason="trusted operator reviewed full tool-owned fixture",
        timeout=timeout,
        output=tmp_path / "external-review.json",
    )
    return (
        ExternalSnapshotSession(
            repo,
            tmp_path,
            tmp_path / "binding.json",
            tmp_path / "external-review.json",
            review.artifact_digest,
        ),
        binding,
        review,
    )


def test_unmarked_source_requires_separate_external_review_and_independent_anchor(tmp_path):
    source, binding, review = source_fixture(tmp_path)
    assert not (source.repo / FIXTURE_REF).exists()
    assert verify_external_snapshot_review(
        source.repo, source.binding_path, source.review_path, trusted_digest=review.artifact_digest
    ) == (binding, review)
    with pytest.raises(ValidationError):
        read_value(source.review_path, SnapshotReview)
    with pytest.raises(ArtifactIntegrityError, match="only_tool_owned_fixtures"):
        issue_snapshot_review(
            source.repo,
            source.binding_path,
            kind="execution",
            reason="not a permission switch",
            output=tmp_path / "old-review.json",
        )
    assert not (tmp_path / "old-review.json").exists()
    with pytest.raises(ArtifactIntegrityError, match="trusted_anchor"):
        replace(source, trusted_digest=ZERO).capture(evidence_id="evd_denied", output="denied")
    assert not (tmp_path / "denied").exists()
    changed = seal(review.model_copy(update={"license_digest": ZERO}))
    write_immutable(tmp_path / "wrong-license.json", canonical_json_bytes(changed))
    with pytest.raises(ArtifactIntegrityError, match="license_pin_changed"):
        verify_external_snapshot_review(
            source.repo,
            source.binding_path,
            tmp_path / "wrong-license.json",
            trusted_digest=changed.artifact_digest,
        )


@pytest.fixture
def only_docker(tmp_path, monkeypatch):
    runner = resolve_runner(runner_id="root-pytest8", image_digest=None)
    if not os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST"):
        pytest.skip("set COUNTERGUARD_RUNNER_IMAGE_DIGEST to reviewed exact image ID")
    assert os.environ["COUNTERGUARD_RUNNER_IMAGE_DIGEST"] == runner.image_digest
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(LocalTrustedExecutor, "execute", lambda *a: pytest.fail("local fallback"))
    original = importlib.import_module

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"snapshot_sample", "research_target"}:
            pytest.fail("candidate imported on host")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", guarded)
    calls, bounded = [], docker._run_bounded

    def recorded(argv, **kwargs):
        if len(argv) > 1 and argv[1] == "run":
            calls.append(argv)
        return bounded(argv, **kwargs)

    monkeypatch.setattr(docker, "_run_bounded", recorded)
    return calls


@pytest.mark.docker
def test_external_purpose_capture_guard_and_two_lanes_repeated_on_owned_fixtures(
    tmp_path, monkeypatch, only_docker
):
    source, binding, _ = source_fixture(tmp_path)
    evidence = source.capture(evidence_id="evd_external_fixture_v1", output="capture")
    assert evidence.reproduced and len(evidence.failing_case_ids) == 2
    assert evidence.buggy.run.pytest_exit_code == 1 and evidence.fixed.run.pytest_exit_code == 0
    guard = source.compile(
        tmp_path / "capture/evidence.json", guard_id="grd_external_fixture_v1", output="guard"
    )
    assert guard.case_ids == evidence.failing_case_ids and len(only_docker) == 4
    assert "not_schedulable" in guard.state
    for path, old in (
        (tmp_path / "capture/evidence.json", SnapshotEvidence),
        (tmp_path / "guard/guard.json", SnapshotGuard),
    ):
        with pytest.raises(ValidationError):
            read_value(path, old)
    target_repo, revision = comparison_target_history(tmp_path, marker=False)
    target, _ = inspect_external_snapshot_target(
        target_repo,
        revision,
        repository_url="https://github.com/tool-fixture/target",
        target_id="external-target",
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
    assert not (target_repo / FIXTURE_REF).exists()
    mapping = create_external_snapshot_map(guard, binding.contract, target)
    write_immutable(tmp_path / "map.json", canonical_json_bytes(mapping))
    cases = tuple(c for c in binding.contract.cases if c.case_id in guard.case_ids)
    witness = seal(
        ExternalSnapshotWitness(
            target_digest=target.artifact_digest,
            map_digest=mapping.artifact_digest,
            basis_refs=("README.md",),
            cases=tuple(c.model_copy(update={"exception_match": "own API rejects"}) for c in cases),
            artifact_digest=ZERO,
        )
    )
    write_immutable(tmp_path / "witness.json", canonical_json_bytes(witness))
    plan = seal(
        ExternalComparisonPlan(
            evidence_ref="capture/evidence.json",
            guard_ref="guard/guard.json",
            target_ref="target.json",
            map_ref="map.json",
            witness_ref="witness.json",
            review_ref="comparison-review.json",
            artifact_digest=ZERO,
        )
    )
    review = issue_external_comparison_review(
        source,
        target_repo,
        plan,
        output=tmp_path / "comparison-review.json",
        reason="reviewed original identity mapping and separate target own oracle",
        source_interface="value_return",
        source_interface_basis_ref="src/snapshot_sample/core.py",
    )
    engine = ExternalSnapshotComparisonSession(source, target_repo, review.artifact_digest)
    for lane, outcome in (("guard", "test_failed"), ("own_contract", "passed")):
        observations = []
        for index in range(2):
            result = engine.run(
                seal(plan.model_copy(update={"lane": lane})), output=f"{lane}-{index}"
            )
            assert result.outcome == outcome
            assert engine.verify(tmp_path / f"{lane}-{index}/replay.json") == result
            observations.append(tuple((c.case_id, c.outcome) for c in result.run.case_results))
            with pytest.raises(ValidationError):
                read_value(tmp_path / f"{lane}-{index}/replay.json", SnapshotComparisonReplay)
        assert observations[0] == observations[1]
    assert len(only_docker) == 8
    with pytest.raises(ArtifactIntegrityError):
        replace(engine, review_anchor=ZERO).run(plan, output="wrong-anchor")
    assert len(only_docker) == 8 and not (tmp_path / "wrong-anchor").exists()
    withdrawn = issue_external_comparison_review(
        source,
        target_repo,
        plan,
        action="withdraw",
        output=tmp_path / "withdrawn.json",
        reason="operator withdraws this observation authority",
        source_interface="value_return",
        source_interface_basis_ref="src/snapshot_sample/core.py",
    )
    revoked_plan = seal(plan.model_copy(update={"review_ref": "withdrawn.json"}))
    revoked = replace(engine, review_anchor=withdrawn.artifact_digest)
    result = revoked.run(revoked_plan, output="withdrawn-result")
    assert result.run is None and result.admission.decision == "unknown" and len(only_docker) == 8
    assert revoked.verify(tmp_path / "withdrawn-result/replay.json") == result
    from counterguard import snapshot_comparison as module

    execute = module._execute_with_adapter

    def late_change(request, adapter):
        run = execute(request, adapter)
        request.test_path.write_bytes(request.test_path.read_bytes() + b"\n# late change\n")
        return run

    monkeypatch.setattr(module, "_execute_with_adapter", late_change)
    late = engine.run(plan, output="late")
    assert late.integrity == "stale" and late.run is not None and len(only_docker) == 9
    with pytest.raises(ArtifactIntegrityError):
        engine.verify(tmp_path / "late/replay.json")
    sandbox = tmp_path / "own_contract-0/runtime/r/runs/run_comparison/sandbox-input"
    assert (sandbox / "src/research_target/resource.txt").is_file()
    assert not (sandbox / "src/snapshot_sample").exists()
    assert not (sandbox / "conftest.py").exists()


@pytest.mark.docker
@pytest.mark.parametrize(
    "behavior", ["network", "write", "environment", "timeout", "memory", "process"]
)
def test_external_purpose_preserves_actual_attack_failures(
    tmp_path, monkeypatch, only_docker, behavior
):
    monkeypatch.setenv("COUNTERGUARD_HOST_SECRET", "must-not-enter-container")
    source, _, _ = source_fixture(
        tmp_path, behavior=behavior, timeout=2.0 if behavior == "timeout" else 10.0
    )
    evidence = source.capture(evidence_id="evd_external_attack_v1", output="capture")
    assert not evidence.reproduced and len(only_docker) == 2
    assert evidence.buggy.run.outcome is RunOutcome.TEST_FAILED
    assert_snapshot_attack_observed(evidence.fixed.run, behavior)
    assert source.verify_evidence(tmp_path / "capture/evidence.json") == evidence
    with pytest.raises(ArtifactIntegrityError, match="not_reproduced"):
        source.compile(
            tmp_path / "capture/evidence.json", guard_id="grd_external_denied", output="denied"
        )
    assert not (tmp_path / "denied").exists()
