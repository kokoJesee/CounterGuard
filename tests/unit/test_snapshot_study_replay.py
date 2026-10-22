"""Snapshot four-method decisions and closed namespaces, with explicit source doubles."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import counterguard.snapshot_study_replay as replay_module
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.runner_catalog import resolve_runner
from counterguard.runners import docker
from counterguard.runners.docker import DockerPolicyV1
from counterguard.snapshot_admission import ZERO, seal
from counterguard.snapshot_comparison_models import (
    SnapshotComparisonPlan,
    SnapshotComparisonReplay,
    SnapshotComparisonTarget,
)
from counterguard.snapshot_study_models import (
    SnapshotStudyContext,
    SnapshotStudyFeatureAudit,
    SnapshotStudySource,
)
from counterguard.snapshot_study_replay import (
    SnapshotStudyReplaySession,
    issue_snapshot_study_execution_review,
    load_snapshot_study_facts,
)
from counterguard.snapshot_study_replay_models import SnapshotStudyPlan
from counterguard.standalone_capture import _model
from tests.unit.test_snapshot_study_fit import training as _training

snapshot_training = pytest.fixture(name="snapshot_training")(_training.__wrapped__)


@pytest.fixture
def replay(snapshot_training, monkeypatch):
    fit_session, _, _, _, snapshots = snapshot_training
    root = fit_session.workspace
    initial = fit_session.fit(
        "protocol.json", "review.json", phase="initial", output="initial.json"
    )
    refined = fit_session.fit(
        "protocol.json", "review.json", phase="refined", output="refined.json"
    )
    target = _model(root, "d/target.json", SnapshotComparisonTarget)
    context = _model(root, "d/context.json", SnapshotStudyContext)
    audit = _model(root, "d/audit.json", SnapshotStudyFeatureAudit)
    source = _model(root, "source.json", SnapshotStudySource)
    facts = SimpleNamespace(
        guard=SimpleNamespace(artifact_digest=source.guard_digest, guard_id="grd_fixture"),
        binding=SimpleNamespace(
            artifact_digest=source.binding_digest,
            package_refs={"fixed": ("src/snapshot_sample/core.py",)},
        ),
        source_review=SimpleNamespace(
            artifact_digest=source.source_review_digest,
            runner=resolve_runner(runner_id="root-pytest8", image_digest=None),
            policy_digest=digest_json_artifact(DockerPolicyV1()),
            timeout_seconds=10.0,
        ),
        target=target,
        target_files=snapshots["d"],
        mapping=SimpleNamespace(artifact_digest=ZERO),
        witness=None,
        real_checked_fit_inputs=replay_module._checked_fit_inputs,
    )
    monkeypatch.setattr(replay_module, "load_comparison_facts", lambda *a, **k: facts)
    # Each fit was actually built above. Pure decision tests do not repeatedly
    # reconstruct all training/source facts; dedicated tests and Docker cover that.
    monkeypatch.setattr(
        replay_module, "_checked_fit_inputs", lambda *a: (initial, refined, context, audit)
    )
    monkeypatch.setattr(SnapshotStudyReplaySession, "_facts", lambda *a: facts)
    plan = seal(
        SnapshotStudyPlan(
            evidence_ref=source.evidence_ref,
            guard_ref=source.guard_ref,
            target_ref="d/target.json",
            map_ref="map.json",
            review_ref="execution.json",
            initial_fit_ref="initial.json",
            refined_fit_ref="refined.json",
            context_ref="d/context.json",
            audit_ref="d/audit.json",
            method="b1_always",
            artifact_digest=ZERO,
        )
    )
    review = issue_snapshot_study_execution_review(
        fit_session,
        fit_session.repositories[target.repository_identity_digest],
        plan,
        output="execution.json",
        reason="Explicit synthetic query execution review",
        source_interface="value_return",
        source_interface_basis_ref="src/snapshot_sample/core.py",
    )
    session = SnapshotStudyReplaySession(
        fit_session.source,
        fit_session.repositories[target.repository_identity_digest],
        review.artifact_digest,
        fit_session,
    )
    return session, plan, review, facts, (initial, refined, context, audit)


def test_four_methods_bind_the_same_fits_and_preserve_three_way_decision(replay):
    session, plan, _, _, checked = replay
    expected = {
        "b1_always": "applicable",
        "b2_interface": "inapplicable",
        "learned_initial": "applicable",
        "learned_refined": "inapplicable",
    }
    for method, decision in expected.items():
        admission = session.audit(seal(plan.model_copy(update={"method": method})))
        assert admission.decision == admission.scope_decision.decision == decision
        assert admission.initial_fit_digest == checked[0].artifact_digest
        assert admission.refined_fit_digest == checked[1].artifact_digest
        assert admission.fit_review_digest == session.fit_session.review_anchor
        if method == "learned_refined":
            assert admission.scope_digest == checked[1].scope.artifact_digest
            assert len(admission.scope_decision.trace) == 2


def test_fact_view_is_explicit_read_only_without_widening_the_old_plan(replay, monkeypatch):
    session, base, _, facts, _ = replay
    observed = []

    def load(source, repo, view):
        assert source is session.source and repo == session.target_repo
        assert type(view) is SnapshotComparisonPlan
        assert view.method == "b1_always" and view.lane == "guard"
        assert view.evidence_ref == base.evidence_ref and view.target_ref == base.target_ref
        assert not hasattr(view, "initial_fit_ref")
        observed.append(view)
        return facts

    monkeypatch.setattr(replay_module, "load_comparison_facts", load)
    plan = seal(base.model_copy(update={"method": "learned_refined"}))
    assert load_snapshot_study_facts(session.source, session.target_repo, plan) is facts
    assert len(observed) == 1
    with pytest.raises(ArtifactIntegrityError, match="plan_type_required"):
        load_snapshot_study_facts(session.source, session.target_repo, observed[0])
    assert len(observed) == 1


def test_inapplicable_is_a_real_zero_launch_skip_and_can_be_verified(replay, monkeypatch):
    session, plan, _, _, _ = replay
    monkeypatch.setattr(
        docker, "_run_bounded", lambda *a, **k: pytest.fail("Docker discovery/start")
    )
    plan = seal(plan.model_copy(update={"method": "learned_refined"}))
    result = session.run(plan, output=Path("skip"))
    assert result.outcome == "skipped_inapplicable" and result.run is None
    assert result.authorization_ref is result.record_ref is result.workspace_ref is None
    assert session.verify("skip/replay.json") == result
    with pytest.raises(ValidationError):
        SnapshotComparisonReplay.model_validate_json(result.model_dump_json())


def test_refusal_is_unknown_not_inapplicable_or_passed(replay, monkeypatch):
    session, plan, _, _, checked = replay
    initial, refined, context, audit = checked
    initial = seal(
        initial.model_copy(
            update={
                "status": "refused",
                "refusal_code": "no_counterexample",
                "scope": None,
                "learning": None,
                "explanation": None,
            }
        )
    )
    monkeypatch.setattr(
        replay_module, "_checked_fit_inputs", lambda *a: (initial, refined, context, audit)
    )
    review = issue_snapshot_study_execution_review(
        session.fit_session,
        session.target_repo,
        plan,
        output="unknown-review.json",
        reason="Synthetic explicit refusal fixture",
        source_interface="value_return",
        source_interface_basis_ref="src/snapshot_sample/core.py",
    )
    unknown = SnapshotStudyReplaySession(
        session.source, session.target_repo, review.artifact_digest, session.fit_session
    )
    plan = seal(
        plan.model_copy(update={"review_ref": "unknown-review.json", "method": "learned_initial"})
    )
    monkeypatch.setattr(
        docker, "_run_bounded", lambda *a, **k: pytest.fail("unknown started Docker")
    )
    result = unknown.run(plan, output=Path("unknown"))
    assert result.admission.decision == "unknown" and result.outcome == "skipped_unknown"
    assert result.admission.scope_decision.reason == "no_counterexample"
    assert result.run is None and result.admission.scope_digest is None
    assert unknown.verify("unknown/replay.json") == result


def test_old_plan_and_external_purpose_are_not_execution_inputs(replay):
    session, plan, _, _, _ = replay
    with pytest.raises(ValidationError):
        SnapshotComparisonPlan.model_validate_json(plan.model_dump_json())
    data = json.loads(plan.model_dump_json())
    data["purpose"] = "reviewed_external_snapshot_observation_only"
    with pytest.raises(ValidationError):
        SnapshotStudyPlan.model_validate_json(json.dumps(data))
    with pytest.raises(ArtifactIntegrityError, match="type_required"):
        session.audit(SimpleNamespace(**data))


def test_resigned_plan_and_result_cannot_replace_an_independent_fit_anchor(replay):
    session, plan, _, _, _ = replay
    plan = seal(plan.model_copy(update={"method": "learned_refined"}))
    session.run(plan, output=Path("skip"))
    path = session.source.workspace / "skip/replay.json"
    raw = json.loads(path.read_bytes())
    raw["fit_review_digest"] = ZERO
    raw["artifact_digest"] = digest_json_artifact(raw)
    path.write_bytes(canonical_json_bytes(raw))
    with pytest.raises(ArtifactIntegrityError, match="fit_anchor"):
        session.verify(path)


def test_checked_fit_inputs_rebuilds_both_fits_and_binds_actual_snapshot_source(replay):
    session, plan, _, facts, checked = replay
    assert facts.real_checked_fit_inputs(session.fit_session, plan, facts) == checked
    path = session.source.workspace / "initial.json"
    raw = json.loads(path.read_bytes())
    raw["scope"]["clauses"][0]["value"] = "forged"
    raw["artifact_digest"] = digest_json_artifact(raw)
    path.write_bytes(canonical_json_bytes(raw))
    with pytest.raises((ArtifactIntegrityError, ValidationError)):
        facts.real_checked_fit_inputs(session.fit_session, plan, facts)
