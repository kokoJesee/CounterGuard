"""Explicitly reviewed N-by-four fixture orchestration and source-backed verification."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.evaluation_metrics import Prediction
from counterguard.models import CaseOutcome, Digest, RunOutcome
from counterguard.path_limits import require_paths, require_publication, require_run_directory
from counterguard.project_config import reject_links
from counterguard.snapshot_admission import ZERO, require, seal
from counterguard.snapshot_execution import CONTRACT_REF, TEST_REF
from counterguard.snapshot_study_evaluation_models import (
    METHODS,
    SnapshotStudyEvaluation,
    SnapshotStudyEvaluationFailure,
    SnapshotStudyEvaluationPin,
    SnapshotStudyEvaluationPlan,
    SnapshotStudyEvaluationReview,
    SnapshotStudyEvaluationSlot,
    SnapshotStudyQueryLabel,
    SnapshotStudySourceBug,
)
from counterguard.snapshot_study_fit import snapshot_study_target_key
from counterguard.snapshot_study_replay import SnapshotStudyReplaySession
from counterguard.snapshot_study_replay_models import SnapshotStudyPlan
from counterguard.standalone_capture import _model
from counterguard.study_data import StudyNotReady
from counterguard.study_fit import _destination
from counterguard.study_metrics import StudyMetricInput, StudyMetricRow, summarize_study_metrics


def _prepare(workspace, sessions, plan_ref):
    plan = _model(workspace, plan_ref, SnapshotStudyEvaluationPlan)
    require(set(sessions) == {m.row_id for m in plan.members}, "snapshot_evaluation_roster_changed")
    prepared, pins, identities, samples, guards, fits = [], [], {}, {}, {}, {}
    for member in plan.members:
        session = sessions[member.row_id]
        require(
            type(session) is SnapshotStudyReplaySession and session.source.workspace == workspace,
            "snapshot_evaluation_session_type_or_workspace_changed",
        )
        replay_plan = _model(workspace, member.plan_ref, SnapshotStudyPlan)
        require(
            replay_plan.method == "b1_always", "snapshot_evaluation_requires_canonical_base_plan"
        )
        admission, facts, execution_review = session._load(replay_plan)
        require(
            guards.setdefault(facts.guard.guard_id, facts.guard.artifact_digest)
            == facts.guard.artifact_digest,
            "snapshot_evaluation_guard_id_alias",
        )
        fit_identity = (
            session.fit_session.review_anchor,
            admission.initial_fit_digest,
            admission.refined_fit_digest,
            execution_review.source_interface,
        )
        require(
            fits.setdefault(facts.guard.artifact_digest, fit_identity) == fit_identity,
            "snapshot_evaluation_per_guard_methods_changed_between_queries",
        )
        label = _model(workspace, member.label_ref, SnapshotStudyQueryLabel)
        require(
            label.artifact_digest == member.label_digest
            and label.sample_id == member.sample_id
            and label.project_group == member.project_group
            and label.guard_digest == member.guard_digest == facts.guard.artifact_digest
            and label.target_digest == facts.target.artifact_digest
            and label.labels.guard_id == facts.guard.guard_id
            and snapshot_study_target_key(facts.target) == member.target_key,
            "snapshot_evaluation_label_or_member_subject_changed",
        )
        require(
            all(
                p.ref in facts.target_files
                and digest_bytes(facts.target_files[p.ref]) == p.content_digest
                for p in label.basis_pins
            ),
            "snapshot_evaluation_label_basis_changed",
        )
        identity = facts.target.repository_identity_digest
        require(
            identities.setdefault(identity, member.project_group) == member.project_group,
            "snapshot_evaluation_repository_group_alias",
        )
        require(
            samples.setdefault(member.sample_id, member.target_key) == member.target_key,
            "snapshot_evaluation_sample_alias",
        )
        pins.append(
            SnapshotStudyEvaluationPin(
                row_id=member.row_id,
                plan_digest=replay_plan.artifact_digest,
                label_digest=label.artifact_digest,
                guard_digest=facts.guard.artifact_digest,
                target_digest=facts.target.artifact_digest,
                execution_review_digest=session.review_anchor,
                fit_review_digest=session.fit_session.review_anchor,
                initial_fit_digest=admission.initial_fit_digest,
                refined_fit_digest=admission.refined_fit_digest,
            )
        )
        prepared.append((member, replay_plan, label, facts))
    return plan, tuple(pins), tuple(prepared)


def _repositories(sessions):
    return tuple(
        {
            p
            for session in sessions.values()
            for p in (
                session.source.repo,
                session.target_repo,
                *session.fit_session.repositories.values(),
            )
        }
    )


def issue_snapshot_study_evaluation_review(
    workspace, sessions, plan_ref, *, output, operator, reason, action="approve"
):
    workspace = Path(workspace)
    reject_links(workspace)
    workspace = workspace.resolve(strict=True)
    plan, pins, _ = _prepare(workspace, sessions, plan_ref)
    review = seal(
        SnapshotStudyEvaluationReview(
            created_at=datetime.now(UTC),
            operator=operator,
            reason=reason,
            action=action,
            plan_digest=plan.artifact_digest,
            members=pins,
            implementation_digests=inspection_implementation_digests(),
            artifact_digest=ZERO,
        )
    )
    path = _destination(workspace, Path(output), _repositories(sessions))
    write_immutable(path, canonical_json_bytes(review))
    return review


def _prediction(method, member, label, guard_id, replay):
    run = replay.run
    outcome = run.outcome if run else None
    verdict = (
        "stale"
        if replay.integrity == "stale"
        else replay.outcome
        if run is None
        else {
            RunOutcome.PASSED: "pass",
            RunOutcome.TEST_FAILED: "violation",
            RunOutcome.NO_TESTS_COLLECTED: "collection_error",
            RunOutcome.TIMEOUT: "timeout",
        }.get(outcome, "execution_error")
    )
    return Prediction(
        method=method,
        guard_id=guard_id,
        sample_id=member.sample_id,
        labels=label.labels,
        scope_decision=replay.admission.decision,
        decision_trace=replay.admission.scope_decision.trace,
        verdict=verdict,
        violated_case_ids=tuple(
            c.case_id for c in run.case_results if c.outcome is CaseOutcome.FAILED
        )
        if outcome is RunOutcome.TEST_FAILED
        else (),
        run_outcome=outcome,
    )


def _source_bugs(prepared):
    values = {}
    for _, _, _, facts in prepared:
        guard = facts.guard
        row = SnapshotStudySourceBug(
            guard_id=guard.guard_id,
            guard_digest=guard.artifact_digest,
            buggy_run_digest=digest_json_artifact(guard.buggy_check.run),
            fixed_run_digest=digest_json_artifact(guard.fixed_check.run),
            detected=guard.buggy_check.run.outcome is RunOutcome.TEST_FAILED
            and any(c.outcome is CaseOutcome.FAILED for c in guard.buggy_check.run.case_results),
            fixed_passed=guard.fixed_check.run.outcome is RunOutcome.PASSED,
        )
        require(values.setdefault(guard.guard_id, row) == row, "snapshot_evaluation_guard_id_alias")
    return tuple(values[key] for key in sorted(values))


def _metrics(slots, prepared):
    groups = {member.row_id: member.project_group for member, *_ in prepared}
    return summarize_study_metrics(
        StudyMetricInput(
            rows=tuple(
                StudyMetricRow(project_group=groups[slot.row_id], prediction=slot.prediction)
                for slot in slots
            )
        )
    )


@dataclass(frozen=True)
class SnapshotStudyEvaluationSession:
    workspace: Path
    sessions: dict[str, SnapshotStudyReplaySession]
    review_anchor: str

    def __post_init__(self):
        reject_links(self.workspace)
        object.__setattr__(self, "workspace", Path(self.workspace).resolve(strict=True))
        TypeAdapter(Digest).validate_python(self.review_anchor)
        require(
            all(type(s) is SnapshotStudyReplaySession for s in self.sessions.values()),
            "snapshot_evaluation_requires_closed_snapshot_sessions",
        )
        object.__setattr__(self, "sessions", dict(self.sessions))

    def _load(self, plan_ref, review_ref):
        review = _model(self.workspace, review_ref, SnapshotStudyEvaluationReview)
        require(review.artifact_digest == self.review_anchor, "snapshot_evaluation_anchor_changed")
        require(
            review.implementation_digests == inspection_implementation_digests(),
            "snapshot_evaluation_implementation_stale",
        )
        if review.action != "approve":
            raise StudyNotReady("snapshot_evaluation_review_withdrawn")
        plan, pins, prepared = _prepare(self.workspace, self.sessions, plan_ref)
        require(
            review.plan_digest == plan.artifact_digest and review.members == pins,
            "snapshot_evaluation_review_subject_changed",
        )
        return plan, prepared

    def audit(self, plan_ref, review_ref):
        plan, _ = self._load(plan_ref, review_ref)
        return plan

    def _output(self, output):
        path = _destination(self.workspace, Path(output), _repositories(self.sessions))
        require(
            not path.exists() and path != self.workspace, "snapshot_evaluation_new_output_required"
        )
        return path

    def evaluate(self, plan_ref, review_ref, *, output):
        plan, prepared = self._load(plan_ref, review_ref)
        directory = self._output(output)
        require_publication(directory / "evaluation.json")
        # Check every possible execution layout before any output or container.
        for member, base, _, facts in prepared:
            for method in METHODS:
                variant = seal(base.model_copy(update={"method": method}))
                destination = directory / member.row_id / method
                for ref in ("plan.json", "replay.json", "authorization.json"):
                    require_publication(destination / ref)
                runtime = destination / "runtime"
                run_directory = runtime / "r/runs/run_comparison"
                require_run_directory(run_directory)
                for ref in (*facts.target.package_refs, CONTRACT_REF, TEST_REF):
                    require_publication(runtime / ref)
                    require_paths(run_directory / "sandbox-input" / ref)
        directory.mkdir(parents=True, exist_ok=False)
        slots = []
        try:
            for member, base, label, facts in prepared:
                session = self.sessions[member.row_id]
                for method in METHODS:
                    variant = seal(base.model_copy(update={"method": method}))
                    destination = directory / member.row_id / method
                    replay = session.run(variant, output=destination)
                    require(replay.integrity == "current", "snapshot_evaluation_stale_replay")
                    session.verify(destination / "replay.json")
                    slots.append(
                        SnapshotStudyEvaluationSlot(
                            row_id=member.row_id,
                            method=method,
                            replay_ref=(destination / "replay.json")
                            .relative_to(self.workspace)
                            .as_posix(),
                            replay_digest=replay.artifact_digest,
                            prediction=_prediction(
                                method, member, label, facts.guard.guard_id, replay
                            ),
                        )
                    )
            # Rebuild all labels/plans/reviews after execution; never publish a
            # complete matrix after an intervening change in another row.
            self._load(plan_ref, review_ref)
        except (ArtifactIntegrityError, OSError, ValueError, KeyError, TypeError):
            failure = seal(
                SnapshotStudyEvaluationFailure(
                    plan_digest=plan.artifact_digest,
                    review_digest=self.review_anchor,
                    completed_slots=tuple(slots),
                    artifact_digest=ZERO,
                )
            )
            write_immutable(directory / "failure.json", canonical_json_bytes(failure))
            raise
        result = seal(
            SnapshotStudyEvaluation(
                created_at=datetime.now(UTC),
                plan_ref=plan_ref,
                plan_digest=plan.artifact_digest,
                review_ref=review_ref,
                review_digest=self.review_anchor,
                slots=tuple(slots),
                source_bugs=_source_bugs(prepared),
                metrics=_metrics(slots, prepared),
                execution_failures=sum(
                    slot.prediction.verdict
                    in {"collection_error", "execution_error", "timeout", "stale"}
                    for slot in slots
                ),
                implementation_digests=inspection_implementation_digests(),
                artifact_digest=ZERO,
            )
        )
        write_immutable(directory / "evaluation.json", canonical_json_bytes(result))
        return result

    def verify(self, path):
        path = Path(path)
        path = path if path.is_absolute() else self.workspace / path
        reject_links(path)
        require(
            path.resolve().is_relative_to(self.workspace), "snapshot_evaluation_result_path_escape"
        )
        result = _model(
            self.workspace,
            path.resolve().relative_to(self.workspace).as_posix(),
            SnapshotStudyEvaluation,
        )
        require(
            result.review_digest == self.review_anchor, "snapshot_evaluation_result_anchor_changed"
        )
        plan, prepared = self._load(result.plan_ref, result.review_ref)
        require(
            result.plan_digest == plan.artifact_digest
            and result.implementation_digests == inspection_implementation_digests(),
            "snapshot_evaluation_result_inputs_changed",
        )
        expected_keys = [(m.row_id, method) for m, *_ in prepared for method in METHODS]
        require(
            [(s.row_id, s.method) for s in result.slots] == expected_keys,
            "snapshot_evaluation_matrix_incomplete",
        )
        rebuilt = []
        for slot, (member, base, label, facts) in zip(
            result.slots, (r for r in prepared for _ in METHODS), strict=True
        ):
            session = self.sessions[member.row_id]
            replay = session.verify(slot.replay_ref)
            variant = seal(base.model_copy(update={"method": slot.method}))
            replay_path = self.workspace / slot.replay_ref
            recorded = _model(
                self.workspace,
                (replay_path.parent / "plan.json").relative_to(self.workspace).as_posix(),
                SnapshotStudyPlan,
            )
            require(
                recorded == variant and replay.artifact_digest == slot.replay_digest,
                "snapshot_evaluation_replay_changed",
            )
            prediction = _prediction(slot.method, member, label, facts.guard.guard_id, replay)
            require(prediction == slot.prediction, "snapshot_evaluation_prediction_not_rebuilt")
            rebuilt.append(slot)
        require(
            result.metrics == _metrics(rebuilt, prepared)
            and result.source_bugs == _source_bugs(prepared)
            and result.execution_failures
            == sum(
                s.prediction.verdict in {"collection_error", "execution_error", "timeout", "stale"}
                for s in rebuilt
            ),
            "snapshot_evaluation_summary_not_rebuilt",
        )
        return result

    def export(self, path, *, output):
        result = self.verify(path)
        directory = self._output(output)
        exports = {
            "evaluation.json": canonical_json_bytes(result),
            "metrics.json": canonical_json_bytes(result.metrics),
            "paired.json": canonical_json_bytes(result.metrics.paired),
            "predictions.jsonl": b"\n".join(canonical_json_bytes(s) for s in result.slots) + b"\n",
            "source-bugs.jsonl": b"\n".join(canonical_json_bytes(s) for s in result.source_bugs)
            + b"\n",
        }
        for ref in exports:
            require_publication(directory / ref)
        for ref, raw in exports.items():
            write_immutable(directory / ref, raw)
        return result

    def report(self, path, *, output):
        result = self.verify(path)
        destination = _destination(self.workspace, Path(output), _repositories(self.sessions))
        lines = [
            "# Snapshot fixture evaluation",
            "",
            "Scope: tool-owned known fixture queries; no scientific or external conclusion.",
            "",
            "| Method | Passed | Guard failed | Skipped inapplicable | Unknown | "
            "Execution errors |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for method in METHODS:
            rows = [s.prediction for s in result.slots if s.method == method]
            values = [
                sum(r.verdict == v for r in rows)
                for v in ("pass", "violation", "skipped_inapplicable", "skipped_unknown")
            ]
            errors = sum(
                r.verdict in {"execution_error", "collection_error", "timeout", "stale"}
                for r in rows
            )
            lines.append("| " + method + " | " + " | ".join(map(str, (*values, errors))) + " |")
        lines += [
            "",
            "Source Bug checks are unscoped Guard self-checks, reported separately from "
            "query denominators. They do not prove learned-scope source retention.",
            "",
            "Metrics retain null denominators; unknown and skips are never passes.",
            "",
            "```json",
            result.metrics.model_dump_json(indent=2),
            "```",
            "",
        ]
        write_immutable(destination, "\n".join(lines).encode())
        return result

    def compare(self, path, *, output):
        result = self.verify(path)
        destination = _destination(self.workspace, Path(output), _repositories(self.sessions))
        write_immutable(destination, canonical_json_bytes(result.metrics.paired))
        return result.metrics.paired
