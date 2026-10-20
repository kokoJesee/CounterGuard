"""Full provenance with transport doubles; separate external trust is mandatory."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from counterguard.digests import digest_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.standalone_capture import _seal
from counterguard.study_models import StudyAuthorization
from counterguard.study_observation import StudyObservationSession, issue_observation_review
from counterguard.study_observation_models import (
    StudyObservationAuthorization,
    StudyObservationPlan,
)
from tests.unit.test_bootstrap_binding import repository as repository
from tests.unit.test_standalone_capture import capture_inputs as capture_inputs
from tests.unit.test_standalone_guard import guard_inputs as guard_inputs
from tests.unit.test_study_fit import rewrite
from tests.unit.test_study_replay import study as study

pytestmark = pytest.mark.slow


@pytest.fixture
def observation(study):
    original, old_plan, calls, *_ = study
    plan = _seal(
        StudyObservationPlan(
            **old_plan.model_dump(
                exclude={"schema_version", "purpose", "artifact_digest", "review_ref"}
            ),
            review_ref="external-review.json",
            artifact_digest="sha256:" + "0" * 64,
        )
    )
    review = issue_observation_review(
        original.source_repo,
        original.target_repo,
        original.workspace,
        plan,
        output_ref=plan.review_ref,
        review_id="external-review",
        operator="tool-owned fixture",
        reason="Explicit separate observation review on tool-owned histories for qualification",
        source_interface="value_return",
        target_interface="stdout_write",
    )
    session = StudyObservationSession(
        original.source_repo, original.target_repo, original.workspace, review.artifact_digest
    )
    return session, plan, calls, original


def test_two_lanes_share_original_runtime_and_v8_is_not_v6(observation):
    session, plan, calls, original = observation
    for lane, outcome in (("guard", "test_failed"), ("witness", "passed")):
        result = session.replay(_seal(plan.model_copy(update={"lane": lane})), Path(lane))
        assert result.outcome == outcome and result.integrity == "current"
        assert result.admission.scope_interpretation == "execution_policy_not_semantic_label"
        assert session.verify(Path(lane) / "result.json") == result
        raw = (session.workspace / result.authorization_ref).read_bytes()
        auth = StudyObservationAuthorization.model_validate_json(raw)
        assert auth.purpose == result.purpose == "external_snapshot_observation_only"
        with pytest.raises(ValidationError):
            StudyAuthorization.model_validate_json(raw)
    assert len(calls) == 2
    with pytest.raises(ValidationError):
        original.audit(plan)


@pytest.mark.parametrize("ref", ["m.json", "w.json", "external-review.json"])
def test_schema_valid_resigning_does_not_replace_external_trust(observation, ref):
    session, plan, calls, _ = observation
    changes = {
        "m.json": {"map_id": "another-map"},
        "w.json": {"basis_refs": ["LICENSE"]},
        "external-review.json": {"reason": "Another valid-looking external approval"},
    }
    rewrite(session.workspace / ref, lambda row: row.update(changes[ref]))
    result = session.replay(plan, Path("rejected"))
    assert result.integrity == "invalid" and result.run is None and not calls


def test_fixture_anchor_cannot_approve_observation_and_withdrawal_never_discovers_docker(
    observation,
    monkeypatch,
):
    import counterguard.study_replay as replay

    session, plan, calls, original = observation
    wrong = replace(session, review_anchor=original.review_anchor)
    refused = wrong.replay(plan, Path("fixture-anchor"))
    assert refused.integrity == "invalid" and refused.run is None and not calls
    withdrawn = issue_observation_review(
        session.source_repo,
        session.target_repo,
        session.workspace,
        plan,
        output_ref="withdrawn.json",
        review_id="withdrawn",
        operator="tool-owned fixture",
        reason="Withdraw qualification review",
        source_interface="value_return",
        target_interface="stdout_write",
        action="withdraw",
        previous_ref=plan.review_ref,
        previous_anchor=session.review_anchor,
    )

    def forbidden():
        pytest.fail("unknown observation reached Docker discovery")

    monkeypatch.setattr(replay, "_docker_executable", forbidden)
    current = replace(session, review_anchor=withdrawn.artifact_digest)
    plan = _seal(plan.model_copy(update={"review_ref": "withdrawn.json"}))
    result = current.replay(plan, Path("withdrawn"))
    assert result.outcome == "skipped_unknown" and result.run is None and not calls
    assert current.verify(Path("withdrawn/result.json")) == result


def test_late_external_review_change_preserves_actual_run(observation, monkeypatch):
    import counterguard.study_replay as replay

    session, plan, calls, _ = observation
    original = replay._execute_with_adapter

    def changed(request, adapter):
        run = original(request, adapter)
        rewrite(session.workspace / plan.review_ref, lambda row: row.update(reason="Changed later"))
        return run

    monkeypatch.setattr(replay, "_execute_with_adapter", changed)
    result = session.replay(plan, Path("late"))
    assert result.integrity == "stale" and result.run is not None and len(calls) == 1
    with pytest.raises(ArtifactIntegrityError):
        session.verify(Path("late/result.json"))


def test_observation_does_not_accept_fit_inputs_in_cli(observation, capsys):
    from types import SimpleNamespace

    from counterguard.study_cli import execute_study_command

    session, plan, calls, _ = observation
    (session.workspace / "plan.json").write_text(plan.model_dump_json())
    args = SimpleNamespace(
        command="audit",
        workspace=session.workspace,
        source_repo=session.source_repo,
        target_repo=session.target_repo,
        review_digest=session.review_anchor,
        plan=Path("plan.json"),
        fit_review_digest=digest_bytes(b"unrelated fit"),
        training_repository=[],
    )
    assert execute_study_command(args) == 5 and not calls
    assert json.loads(capsys.readouterr().out)["reason_code"] == "study_input_invalid"
    args.fit_review_digest = None
    assert execute_study_command(args) == 0 and not calls
    admission = json.loads(capsys.readouterr().out)
    assert admission["schema_version"] == "study-admission.v3"
    assert admission["scope_interpretation"] == "execution_policy_not_semantic_label"
