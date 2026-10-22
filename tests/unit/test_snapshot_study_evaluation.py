"""N-by-four orchestration, pins and arithmetic with explicitly doubled replay I/O."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import counterguard.snapshot_study_evaluation as evaluation_module
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import CaseOutcome, RunOutcome
from counterguard.protocol import SampleLabels
from counterguard.snapshot_admission import ZERO, seal
from counterguard.snapshot_study_evaluation import (
    SnapshotStudyEvaluationSession,
    issue_snapshot_study_evaluation_review,
)
from counterguard.snapshot_study_evaluation_models import (
    METHODS,
    SnapshotStudyEvaluationMember,
    SnapshotStudyEvaluationPlan,
    SnapshotStudyQueryLabel,
    SnapshotStudySourceBug,
)
from counterguard.snapshot_study_fit import snapshot_study_target_key
from counterguard.snapshot_study_replay import SnapshotStudyReplaySession
from counterguard.snapshot_study_replay_models import SnapshotStudyPlan
from counterguard.study_data import StudyNotReady, persist
from counterguard.study_fit_models import StudyBasisPin
from tests.unit.test_snapshot_study_replay import replay as _replay
from tests.unit.test_snapshot_study_replay import snapshot_training as _training

snapshot_training = _training
replay = pytest.fixture(name="replay")(_replay.__wrapped__)


@pytest.fixture
def evaluation(replay, monkeypatch):
    session, base, _, facts, _ = replay
    root = session.source.workspace
    persist(root / "base-plan.json", base)
    label = seal(
        SnapshotStudyQueryLabel(
            created_at=datetime.now(UTC),
            operator="fixture reviewer",
            reason="Synthetic stdout-clamping query; source raises rule is inapplicable",
            sample_id="query",
            project_group="query-group",
            guard_digest=facts.guard.artifact_digest,
            target_digest=facts.target.artifact_digest,
            labels=SampleLabels(
                guard_id="grd_fixture",
                guard_applicable=False,
                guard_violation=None,
                contract_compliant=True,
                basis="Tool-owned fixture README policy",
            ),
            basis_pins=(
                StudyBasisPin(
                    ref="README.md", content_digest=digest_bytes(facts.target_files["README.md"])
                ),
            ),
            artifact_digest=ZERO,
        )
    )
    persist(root / "query-label.json", label)
    plan = seal(
        SnapshotStudyEvaluationPlan(
            evaluation_id="fixture-matrix",
            members=(
                SnapshotStudyEvaluationMember(
                    row_id="row",
                    sample_id="query",
                    project_group="query-group",
                    guard_digest=facts.guard.artifact_digest,
                    target_key=snapshot_study_target_key(facts.target),
                    plan_ref="base-plan.json",
                    label_ref="query-label.json",
                    label_digest=label.artifact_digest,
                ),
            ),
            artifact_digest=ZERO,
        )
    )
    persist(root / "evaluation-plan.json", plan)
    roster = {"row": session}
    review = issue_snapshot_study_evaluation_review(
        root,
        roster,
        "evaluation-plan.json",
        output="evaluation-review.json",
        operator="fixture reviewer",
        reason="Freeze known synthetic query and complete four-method matrix",
    )
    engine = SnapshotStudyEvaluationSession(root, roster, review.artifact_digest)
    observed = {}
    calls = []

    def run(self, variant, *, output):
        admission = self.audit(variant)
        calls.append(variant.method)
        path = Path(output)
        path = path if path.is_absolute() else root / path
        run = None
        if admission.decision == "applicable":
            run = SimpleNamespace(
                outcome=RunOutcome.TEST_FAILED,
                case_results=(SimpleNamespace(case_id="case-fixture", outcome=CaseOutcome.FAILED),),
            )
        value = SimpleNamespace(
            integrity="current",
            run=run,
            admission=admission,
            outcome="test_failed" if run else "skipped_" + admission.decision,
            artifact_digest=digest_bytes(canonical_json_bytes(variant) + str(path).encode()),
        )
        path.mkdir(parents=True, exist_ok=False)
        persist(path / "plan.json", variant)
        observed[path / "replay.json"] = value
        return value

    def verify(self, path):
        path = Path(path)
        path = path if path.is_absolute() else root / path
        return observed[path]

    monkeypatch.setattr(SnapshotStudyReplaySession, "run", run)
    monkeypatch.setattr(SnapshotStudyReplaySession, "verify", verify)
    bug = SnapshotStudySourceBug(
        guard_id="grd_fixture",
        guard_digest=facts.guard.artifact_digest,
        buggy_run_digest=ZERO,
        fixed_run_digest=ZERO,
        detected=True,
        fixed_passed=True,
    )
    # Unit provenance double only; real source Run/JUnit is checked by Docker integration.
    monkeypatch.setattr(evaluation_module, "_source_bugs", lambda prepared: (bug,))
    return engine, plan, review, calls


def test_complete_matrix_metrics_report_export_and_independent_rebuild(evaluation):
    engine, _, _, calls = evaluation
    result = engine.evaluate("evaluation-plan.json", "evaluation-review.json", output="matrix")
    assert calls == list(METHODS)
    assert len(result.slots) == 4 and result.metrics.evaluation_pair_count == 1
    assert result.metrics.paired.totals.corrected_false_applications == 1
    assert result.metrics.metrics.methods["learned_refined"].micro.execution_count == 0
    assert result.source_bugs[0].detected and result.execution_failures == 0
    assert result.research_support == "fixture_engineering_only_not_scientific_evidence"
    assert engine.verify("matrix/evaluation.json") == result
    engine.report("matrix/evaluation.json", output="report.md")
    text = (engine.workspace / "report.md").read_text()
    assert "Skipped inapplicable" in text and "never passes" in text
    engine.compare("matrix/evaluation.json", output="paired.json")
    engine.export("matrix/evaluation.json", output="export")
    assert len((engine.workspace / "export/predictions.jsonl").read_bytes().splitlines()) == 4
    assert len(calls) == 4  # verify/report/compare/export never execute or refit published files.


def test_all_labels_are_checked_before_first_replay(evaluation):
    engine, _, _, calls = evaluation
    path = engine.workspace / "query-label.json"
    data = json.loads(path.read_bytes())
    data["basis_pins"][0]["content_digest"] = ZERO
    data["artifact_digest"] = digest_json_artifact(data)
    path.write_bytes(canonical_json_bytes(data))
    with pytest.raises(ArtifactIntegrityError):
        engine.evaluate("evaluation-plan.json", "evaluation-review.json", output="forbidden")
    assert calls == [] and not (engine.workspace / "forbidden").exists()


def test_two_query_rows_form_eight_slots_and_second_label_is_preflighted(evaluation, monkeypatch):
    from counterguard.standalone_capture import _model

    engine, plan, _, calls = evaluation
    first = engine.sessions["row"]
    base = _model(engine.workspace, "base-plan.json", SnapshotStudyPlan)
    admission, facts, review = first._load(base)
    second = replace(first)
    target = seal(
        facts.target.model_copy(
            update={
                "target_id": "second",
                "repository_identity_digest": digest_bytes(b"second fixture"),
            }
        )
    )
    second_facts = SimpleNamespace(**(vars(facts) | {"target": target}))
    second_admission = seal(admission.model_copy(update={"target_digest": target.artifact_digest}))
    original = SnapshotStudyReplaySession._load

    def load(self, value):
        return (second_admission, second_facts, review) if self is second else original(self, value)

    monkeypatch.setattr(SnapshotStudyReplaySession, "_load", load)
    label = seal(
        _model(engine.workspace, "query-label.json", SnapshotStudyQueryLabel).model_copy(
            update={
                "sample_id": "query2",
                "project_group": "query-group2",
                "target_digest": target.artifact_digest,
            }
        )
    )
    persist(engine.workspace / "second-label.json", label)
    second_member = plan.members[0].model_copy(
        update={
            "row_id": "row2",
            "sample_id": label.sample_id,
            "project_group": label.project_group,
            "target_key": snapshot_study_target_key(target),
            "label_ref": "second-label.json",
            "label_digest": label.artifact_digest,
        }
    )
    plan = seal(plan.model_copy(update={"members": (*plan.members, second_member)}))
    persist(engine.workspace / "two-plan.json", plan)
    sessions = {"row": first, "row2": second}
    reviewed = issue_snapshot_study_evaluation_review(
        engine.workspace,
        sessions,
        "two-plan.json",
        output="two-review.json",
        operator="fixture reviewer",
        reason="Two explicit synthetic queries; fixed per-Guard methods",
    )
    two = SnapshotStudyEvaluationSession(engine.workspace, sessions, reviewed.artifact_digest)
    result = two.evaluate("two-plan.json", "two-review.json", output="two-matrix")
    assert len(result.slots) == 8 and calls == list(METHODS) * 2
    assert result.metrics.evaluation_pair_count == 2
    assert two.verify("two-matrix/evaluation.json") == result
    path = engine.workspace / "second-label.json"
    path.write_bytes(
        canonical_json_bytes(seal(label.model_copy(update={"reason": "later change"})))
    )
    before = list(calls)
    with pytest.raises(ArtifactIntegrityError):
        two.evaluate("two-plan.json", "two-review.json", output="bad-second-label")
    assert calls == before and not (engine.workspace / "bad-second-label").exists()


def test_withdrawn_or_wrong_evaluation_anchor_never_executes(evaluation):
    engine, _, _, calls = evaluation
    invalid = SnapshotStudyEvaluationSession(engine.workspace, engine.sessions, ZERO)
    with pytest.raises(ArtifactIntegrityError, match="anchor"):
        invalid.evaluate("evaluation-plan.json", "evaluation-review.json", output="wrong")
    review = issue_snapshot_study_evaluation_review(
        engine.workspace,
        engine.sessions,
        "evaluation-plan.json",
        output="withdrawn.json",
        operator="fixture reviewer",
        reason="Withdraw synthetic evaluation before execution",
        action="withdraw",
    )
    withdrawn = SnapshotStudyEvaluationSession(
        engine.workspace, engine.sessions, review.artifact_digest
    )
    with pytest.raises(StudyNotReady, match="withdrawn"):
        withdrawn.evaluate("evaluation-plan.json", "withdrawn.json", output="withdrawn")
    assert calls == []


def test_resigned_summary_and_query_labels_do_not_rebuild(evaluation):
    engine, _, _, _ = evaluation
    engine.evaluate("evaluation-plan.json", "evaluation-review.json", output="matrix")
    path = engine.workspace / "matrix/evaluation.json"
    data = json.loads(path.read_bytes())
    data["metrics"]["row_count"] += 4
    data["metrics"]["artifact_digest"] = digest_json_artifact(data["metrics"])
    data["artifact_digest"] = digest_json_artifact(data)
    path.write_bytes(canonical_json_bytes(data))
    with pytest.raises(ArtifactIntegrityError, match="summary_not_rebuilt"):
        engine.verify(path)


def test_late_change_preserves_partial_records_and_never_publishes_complete(
    evaluation, monkeypatch
):
    engine, _, _, calls = evaluation
    original = SnapshotStudyReplaySession.run

    def changed(self, variant, *, output):
        value = original(self, variant, output=output)
        if len(calls) == 4:
            path = engine.workspace / "query-label.json"
            data = json.loads(path.read_bytes())
            data["reason"] = "Changed after actual synthetic slots"
            data["artifact_digest"] = digest_json_artifact(data)
            path.write_bytes(canonical_json_bytes(data))
        return value

    monkeypatch.setattr(SnapshotStudyReplaySession, "run", changed)
    with pytest.raises(ArtifactIntegrityError):
        engine.evaluate("evaluation-plan.json", "evaluation-review.json", output="partial")
    assert not (engine.workspace / "partial/evaluation.json").exists()
    failure = json.loads((engine.workspace / "partial/failure.json").read_bytes())
    assert failure["complete"] is False and len(failure["completed_slots"]) == 4


def test_evaluation_cannot_drop_methods_duplicate_targets_or_claim_holdout(evaluation):
    _, plan, _, _ = evaluation
    for updates in (
        {"methods": ["b1_always"]},
        {"dataset_role": "sealed_holdout"},
        {"members": [plan.members[0].model_dump(mode="json")] * 2},
    ):
        with pytest.raises(ValidationError):
            SnapshotStudyEvaluationPlan.model_validate_json(
                json.dumps(plan.model_dump(mode="json") | updates)
            )


def test_one_guard_cannot_switch_fits_or_baseline_between_query_rows(evaluation, monkeypatch):
    from counterguard.standalone_capture import _model

    engine, plan, _, calls = evaluation
    session = engine.sessions["row"]
    base = _model(engine.workspace, "base-plan.json", SnapshotStudyPlan)
    admission, facts, execution_review = session._load(base)
    second = replace(session, review_anchor=digest_bytes(b"second execution review"))
    target = seal(
        facts.target.model_copy(
            update={
                "repository_identity_digest": digest_bytes(b"second fixture repository"),
                "target_id": "second",
            }
        )
    )
    second_facts = SimpleNamespace(**(vars(facts) | {"target": target}))
    changed = seal(admission.model_copy(update={"initial_fit_digest": ZERO}))
    original = SnapshotStudyReplaySession._load

    def load(self, value):
        return (
            (changed, second_facts, execution_review) if self is second else original(self, value)
        )

    monkeypatch.setattr(SnapshotStudyReplaySession, "_load", load)
    persist(engine.workspace / "second-plan.json", base)
    member = plan.members[0].model_copy(
        update={
            "row_id": "row2",
            "sample_id": "query2",
            "project_group": "second-group",
            "target_key": snapshot_study_target_key(target),
            "plan_ref": "second-plan.json",
            "label_ref": "unused-second-label.json",
        }
    )
    changed_plan = seal(plan.model_copy(update={"members": (*plan.members, member)}))
    persist(engine.workspace / "conflict-plan.json", changed_plan)
    with pytest.raises(ArtifactIntegrityError, match="per_guard_methods_changed"):
        issue_snapshot_study_evaluation_review(
            engine.workspace,
            {"row": session, "row2": second},
            "conflict-plan.json",
            output="forbidden-review.json",
            operator="fixture reviewer",
            reason="Must reject drift",
        )
    assert calls == [] and not (engine.workspace / "forbidden-review.json").exists()


@pytest.mark.parametrize(
    "outcome,verdict",
    [
        (RunOutcome.PASSED, "pass"),
        (RunOutcome.TEST_FAILED, "violation"),
        (RunOutcome.NO_TESTS_COLLECTED, "collection_error"),
        (RunOutcome.TIMEOUT, "timeout"),
        (RunOutcome.INTERRUPTED, "execution_error"),
        (RunOutcome.PYTEST_INTERNAL_ERROR, "execution_error"),
        (RunOutcome.PYTEST_USAGE_ERROR, "execution_error"),
        (RunOutcome.LAUNCH_ERROR, "execution_error"),
        (RunOutcome.PROCESS_ERROR, "execution_error"),
    ],
)
def test_prediction_uses_run_outcome_and_never_converts_errors_to_guard_failures(outcome, verdict):
    member = SimpleNamespace(sample_id="query")
    label = SimpleNamespace(
        labels=SampleLabels(
            guard_id="grd_fixture",
            guard_applicable=False,
            guard_violation=None,
            contract_compliant=True,
            basis="Synthetic policy",
        )
    )
    run = SimpleNamespace(
        outcome=outcome,
        case_results=(SimpleNamespace(case_id="case-fixture", outcome=CaseOutcome.FAILED),),
    )
    replay = SimpleNamespace(
        run=run,
        integrity="current",
        admission=SimpleNamespace(decision="applicable", scope_decision=SimpleNamespace(trace=())),
    )
    row = evaluation_module._prediction("b1_always", member, label, "grd_fixture", replay)
    assert row.verdict == verdict
    assert bool(row.violated_case_ids) == (outcome is RunOutcome.TEST_FAILED)
