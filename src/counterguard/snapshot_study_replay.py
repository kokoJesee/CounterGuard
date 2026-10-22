"""Four-method fixture replay with separately anchored source, fit and execution reviews."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.baselines import ClauseTrace, ScopeDecision, evaluate_clauses
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.snapshot_admission import ZERO, require, seal
from counterguard.snapshot_comparison import SnapshotComparisonSession, _outcome
from counterguard.snapshot_comparison_data import load_comparison_facts
from counterguard.snapshot_comparison_models import SnapshotComparisonPlan
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_study_features import verify_snapshot_study_feature_audit
from counterguard.snapshot_study_fit import SnapshotStudyFitSession
from counterguard.snapshot_study_models import (
    SnapshotStudyContext,
    SnapshotStudyFeatureAudit,
    SnapshotStudyFitProtocol,
    SnapshotStudySource,
)
from counterguard.snapshot_study_replay_models import (
    SnapshotStudyAdmission,
    SnapshotStudyAuthorization,
    SnapshotStudyExecutionReview,
    SnapshotStudyPlan,
    SnapshotStudyReplay,
)
from counterguard.standalone_capture import _model
from counterguard.study_fit import _destination

FIT_PINS = (
    "fit_review_digest",
    "initial_fit_digest",
    "refined_fit_digest",
    "context_digest",
    "audit_digest",
)


def _checked_plan(plan):
    require(type(plan) is SnapshotStudyPlan, "snapshot_study_plan_type_required")
    plan = SnapshotStudyPlan.model_validate_json(canonical_json_bytes(plan))
    require(
        plan.artifact_digest == digest_json_artifact(plan), "snapshot_study_plan_digest_changed"
    )
    return plan


def load_snapshot_study_facts(source, target_repo, plan):
    """Share only the old read-only fact loader, never its execution authority."""
    require(type(source) is SnapshotSession, "snapshot_study_fixture_source_type_required")
    plan = _checked_plan(plan)
    # The old parser stays closed. This explicit read-only view carries only
    # source/target references; the original plan and fits remain independently
    # checked and pinned by the study review, admission and authorization.
    view = seal(
        SnapshotComparisonPlan(
            evidence_ref=plan.evidence_ref,
            guard_ref=plan.guard_ref,
            target_ref=plan.target_ref,
            map_ref=plan.map_ref,
            witness_ref=plan.witness_ref,
            review_ref=plan.review_ref,
            method="b1_always",
            lane="guard",
            timeout_seconds=plan.timeout_seconds,
            artifact_digest=ZERO,
        )
    )
    return load_comparison_facts(source, target_repo, view)


def _checked_fit_inputs(fit_session, plan, facts):
    require(
        type(fit_session) is SnapshotStudyFitSession, "snapshot_study_fit_session_type_required"
    )
    fits = tuple(fit_session.verify(ref) for ref in (plan.initial_fit_ref, plan.refined_fit_ref))
    initial, refined = fits
    require(
        initial.phase == "initial"
        and refined.phase == "refined"
        and all(
            getattr(initial, key) == getattr(refined, key)
            for key in (
                "protocol_digest",
                "split_digest",
                "source_digest",
                "guard_digest",
                "review_digest",
            )
        )
        and initial.guard_digest == facts.guard.artifact_digest
        and initial.review_digest == fit_session.review_anchor,
        "snapshot_study_fit_subjects_changed",
    )
    protocol = _model(fit_session.workspace, initial.protocol_ref, SnapshotStudyFitProtocol)
    source = _model(fit_session.workspace, protocol.source_ref, SnapshotStudySource)
    require(
        source.binding_digest == facts.binding.artifact_digest
        and source.guard_digest == facts.guard.artifact_digest
        and source.source_review_digest == facts.source_review.artifact_digest,
        "snapshot_study_fit_source_differs_from_execution",
    )
    context = _model(fit_session.workspace, plan.context_ref, SnapshotStudyContext)
    audit = _model(fit_session.workspace, plan.audit_ref, SnapshotStudyFeatureAudit)
    verify_snapshot_study_feature_audit(facts.target, facts.target_files, context, audit)
    require(audit.matched, "snapshot_study_query_feature_mismatch")
    return initial, refined, context, audit


def _pins(fit_session, checked):
    initial, refined, context, audit = checked
    return dict(
        zip(
            FIT_PINS,
            (
                fit_session.review_anchor,
                initial.artifact_digest,
                refined.artifact_digest,
                context.artifact_digest,
                audit.artifact_digest,
            ),
            strict=True,
        )
    )


def issue_snapshot_study_execution_review(
    fit_session,
    target_repo,
    plan,
    *,
    output,
    reason,
    source_interface,
    source_interface_basis_ref,
    action="approve",
):
    require(
        type(fit_session) is SnapshotStudyFitSession, "snapshot_study_fit_session_type_required"
    )
    source = fit_session.source
    plan = _checked_plan(plan)
    facts = load_snapshot_study_facts(source, Path(target_repo), plan)
    checked = _checked_fit_inputs(fit_session, plan, facts)
    require(reason.strip(), "snapshot_study_execution_review_reason_required")
    require(
        source_interface_basis_ref in facts.binding.package_refs["fixed"],
        "snapshot_study_source_interface_basis_missing",
    )
    require(
        plan.timeout_seconds <= facts.source_review.timeout_seconds,
        "snapshot_study_execution_timeout_exceeds_source_review",
    )
    review = seal(
        SnapshotStudyExecutionReview(
            created_at=datetime.now(UTC),
            reason=reason,
            action=action,
            source_review_digest=source.trusted_digest,
            source_guard_digest=facts.guard.artifact_digest,
            source_binding_digest=facts.binding.artifact_digest,
            target_digest=facts.target.artifact_digest,
            map_digest=facts.mapping.artifact_digest,
            witness_digest=facts.witness.artifact_digest if facts.witness else None,
            source_interface=source_interface,
            source_interface_basis_ref=source_interface_basis_ref,
            runner=facts.source_review.runner,
            policy_digest=facts.source_review.policy_digest,
            timeout_seconds=plan.timeout_seconds,
            implementation_digests=inspection_implementation_digests(),
            **_pins(fit_session, checked),
            artifact_digest=ZERO,
        )
    )
    path = _destination(
        source.workspace,
        Path(output),
        (source.repo, Path(target_repo).resolve(), *fit_session.repositories.values()),
    )
    write_immutable(path, canonical_json_bytes(review))
    return review


@dataclass(frozen=True)
class SnapshotStudyReplaySession(SnapshotComparisonSession):
    fit_session: SnapshotStudyFitSession

    _PLAN = SnapshotStudyPlan
    _REVIEW = SnapshotStudyExecutionReview
    _AUTHORIZATION = SnapshotStudyAuthorization
    _RESULT = SnapshotStudyReplay

    def __post_init__(self):
        require(type(self.source) is SnapshotSession, "snapshot_study_fixture_source_type_required")
        require(
            type(self.fit_session) is SnapshotStudyFitSession
            and self.source == self.fit_session.source,
            "snapshot_study_fit_execution_roots_changed",
        )
        super().__post_init__()

    def _checked_plan(self, value):
        return _checked_plan(value)

    def _facts(self, plan):
        return load_snapshot_study_facts(self.source, self.target_repo, plan)

    def _decision(self, plan, facts, review):
        checked = _checked_fit_inputs(self.fit_session, plan, facts)
        pins = _pins(self.fit_session, checked)
        require(
            all(getattr(review, key) == value for key, value in pins.items()),
            "snapshot_study_execution_fit_pins_changed",
        )
        initial, refined, context, audit = checked
        require(
            context.interface_kind == facts.target.interface_kind,
            "snapshot_study_query_interface_changed",
        )
        scope = None
        if review.action != "approve":
            reason = "snapshot_study_execution_review_withdrawn"
            decision = ScopeDecision(decision="unknown", trace=(), reason=reason)
        elif plan.method == "b1_always":
            reason = "snapshot_study_unscoped_method"
            decision = ScopeDecision(decision="applicable", trace=())
        elif plan.method == "b2_interface":
            matched = context.interface_kind == review.source_interface
            reason = (
                "snapshot_study_interface_matches"
                if matched
                else "snapshot_study_interface_differs"
            )
            decision = ScopeDecision(
                decision="applicable" if matched else "inapplicable",
                trace=(
                    ClauseTrace(
                        field="interface_kind",
                        op="eq",
                        expected=review.source_interface,
                        actual=context.interface_kind,
                        matched=matched,
                    ),
                ),
            )
        else:
            fit = initial if plan.method == "learned_initial" else refined
            scope = fit.scope
            if fit.status == "refused":
                reason = "snapshot_study_scope_refused"
                decision = ScopeDecision(decision="unknown", trace=(), reason=fit.refusal_code)
            else:
                reason = "snapshot_study_scope_evaluated"
                decision = evaluate_clauses(
                    scope.clauses, audit.record.features.model_dump(mode="json")
                )
        return seal(
            SnapshotStudyAdmission(
                plan_digest=plan.artifact_digest,
                guard_digest=facts.guard.artifact_digest,
                target_digest=facts.target.artifact_digest,
                map_digest=facts.mapping.artifact_digest,
                review_digest=review.artifact_digest,
                witness_digest=facts.witness.artifact_digest if facts.witness else None,
                method=plan.method,
                lane=plan.lane,
                decision=decision.decision,
                reason_code=reason,
                **pins,
                scope_digest=scope.artifact_digest if scope else None,
                scope_decision=decision,
                artifact_digest=ZERO,
            )
        )

    def _authorize(self, plan, request, loaded):
        # Reuse the closed transport's complete input/request/path checks. The
        # intermediate base value never leaves this function or authorizes a run.
        checked = SnapshotComparisonSession(self.source, self.target_repo, self.review_anchor)
        base = checked._authorize(plan, request, loaded)
        values = {name: getattr(base, name) for name in type(base).model_fields}
        admission = loaded[0]
        values.update(
            schema_version="snapshot-study-execution-authorization.v1",
            purpose="tool_owned_snapshot_study_only",
            **{key: getattr(admission, key) for key in (*FIT_PINS, "scope_digest")},
            artifact_digest=ZERO,
        )
        return seal(SnapshotStudyAuthorization(**values))

    def _output(self, output):
        path = _destination(
            self.source.workspace,
            Path(output),
            (self.source.repo, self.target_repo, *self.fit_session.repositories.values()),
        )
        return super()._output(path)

    def _result(self, plan, directory, admission, *, run=None, stale=False):
        executed = run is not None
        outcome = (
            "integrity_error"
            if stale
            else _outcome(run)
            if executed
            else "skipped_" + admission.decision
        )
        return seal(
            SnapshotStudyReplay(
                created_at=datetime.now(UTC),
                plan_ref=self.source._ref(directory / "plan.json"),
                plan_digest=plan.artifact_digest,
                source_review_digest=self.source.trusted_digest,
                comparison_review_digest=self.review_anchor,
                fit_review_digest=self.fit_session.review_anchor,
                admission=admission,
                integrity="stale" if stale else "current",
                outcome=outcome,
                reason_code="comparison_changed_after_execution"
                if stale
                else admission.reason_code,
                workspace_ref=self.source._ref(directory / "runtime") if executed else None,
                authorization_ref=self.source._ref(directory / "authorization.json")
                if executed
                else None,
                record_ref=self.source._ref(directory / "runtime/r/record.json")
                if executed
                else None,
                run=run,
                artifact_digest=ZERO,
            )
        )

    def verify(self, path):
        result = super().verify(path)
        require(
            result.fit_review_digest == self.fit_session.review_anchor,
            "snapshot_study_result_fit_anchor_changed",
        )
        return result
