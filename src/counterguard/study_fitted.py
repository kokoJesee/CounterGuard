"""A fit-aware research adapter using the original closed Docker replay implementation."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from counterguard.baselines import ClauseTrace, ScopeDecision, evaluate_clauses
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import digest_json_artifact
from counterguard.errors import FeatureExtractionError
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import DockerPolicyV1
from counterguard.standalone_capture import ZERO, _model, _require, _seal
from counterguard.study_data import StudyNotReady, load_facts, load_review_model, persist
from counterguard.study_features import (
    StudyFeatureAudit,
    StudyFeatureContext,
    verify_target_feature_audit,
)
from counterguard.study_fit import StudyFitSession
from counterguard.study_fitted_models import (
    StudyFittedAdmission,
    StudyFittedAuthorization,
    StudyFittedPlan,
    StudyFittedReplay,
    StudyFittedReview,
)
from counterguard.study_replay import StudySession


def _checked_inputs(fit_session, plan, loaded):
    source, target, _, _, _, _, files, _ = loaded
    initial = fit_session.verify(Path(plan.initial_fit_ref))
    refined = fit_session.verify(Path(plan.refined_fit_ref))
    _require(initial.phase == "initial" and refined.phase == "refined", "study_fit_phases_changed")
    for fit in (initial, refined):
        _require(
            fit.source_digest == source.artifact_digest
            and fit.guard_digest == source.guard_digest
            and fit.review_digest == fit_session.review_anchor,
            "study_fit_replay_source_or_anchor_changed",
        )
    _require(
        (initial.protocol_digest, initial.split_digest)
        == (refined.protocol_digest, refined.split_digest),
        "study_fit_replay_protocols_differ",
    )
    context = _model(fit_session.workspace, plan.context_ref, StudyFeatureContext)
    audit = _model(fit_session.workspace, plan.audit_ref, StudyFeatureAudit)
    try:
        verify_target_feature_audit(target, files, context, audit)
    except FeatureExtractionError as error:
        raise StudyNotReady("study_fitted_feature_unsupported") from error
    if not audit.matched:
        raise StudyNotReady("study_fitted_feature_annotation_mismatch")
    return initial, refined, context, audit


def issue_fitted_review(
    source_repo,
    target_repo,
    workspace,
    plan,
    fit_session,
    *,
    output_ref,
    review_id,
    operator,
    reason,
    source_interface,
    target_interface,
    runner_id="root-pytest8",
    action="approve",
    previous_ref=None,
    previous_anchor=None,
):
    """Trusted local action; fit trust is passed separately, never obtained from plan JSON."""
    session = StudyFittedSession(source_repo, target_repo, workspace, ZERO, fit_session)
    plan = session._checked_plan(plan)
    loaded = load_facts(session.source_repo, session.target_repo, session.workspace, plan)
    source, target, mapping, witness, _, facts, _, _ = loaded
    initial, refined, context, audit = _checked_inputs(fit_session, plan, loaded)
    _require(context.interface_kind == target_interface, "study_fitted_review_interface_changed")
    runner = resolve_runner(runner_id=runner_id, image_digest=None)
    _require(runner == facts[2].runner, "study_source_runner_mismatch")
    previous = None
    if previous_ref is not None:
        previous = load_review_model(
            session.workspace, previous_ref, previous_anchor, StudyFittedReview
        )
    else:
        _require(previous_anchor is None, "study_review_predecessor_incomplete")
    review = _seal(
        StudyFittedReview(
            review_id=review_id,
            created_at=datetime.now(UTC),
            operator=operator,
            reason=reason,
            action=action,
            source_digest=source.artifact_digest,
            target_digest=target.artifact_digest,
            map_digest=mapping.artifact_digest,
            witness_digest=witness.artifact_digest if witness else None,
            source_interface=source_interface,
            target_interface=target_interface,
            runner=runner,
            policy_digest=digest_json_artifact(DockerPolicyV1()),
            implementation_digests=inspection_implementation_digests(),
            previous_review_ref=previous_ref,
            previous_review_digest=previous.artifact_digest if previous else None,
            fit_review_digest=fit_session.review_anchor,
            initial_fit_digest=initial.artifact_digest,
            refined_fit_digest=refined.artifact_digest,
            context_digest=context.artifact_digest,
            audit_digest=audit.artifact_digest,
            artifact_digest=ZERO,
        )
    )
    from counterguard.study_fit import _destination

    output = _destination(
        session.workspace,
        Path(output_ref),
        (
            session.source_repo,
            session.target_repo,
            *fit_session.repositories.values(),
        ),
    )
    return persist(output, review)


@dataclass(frozen=True)
class StudyFittedSession(StudySession):
    fit_session: StudyFitSession
    _plan_model: ClassVar[type] = StudyFittedPlan
    _result_model: ClassVar[type] = StudyFittedReplay
    _authorization_model: ClassVar[type] = StudyFittedAuthorization

    def __post_init__(self):
        super().__post_init__()
        _require(
            self.fit_session.source_repo == self.source_repo
            and self.fit_session.workspace == self.workspace,
            "study_fitted_session_roots_changed",
        )

    def _review(self, plan):
        return load_review_model(
            self.workspace, plan.review_ref, self.review_anchor, StudyFittedReview
        )

    def replay(self, plan, output):
        from counterguard.study_fit import _destination

        output = _destination(
            self.workspace, Path(output), tuple(self.fit_session.repositories.values())
        )
        return super().replay(plan, output)

    def _decide(self, plan, loaded, review):
        source, target, mapping, witness, _, _, _, _ = loaded
        initial, refined, context, audit = _checked_inputs(self.fit_session, plan, loaded)
        _require(
            (
                review.fit_review_digest,
                review.initial_fit_digest,
                review.refined_fit_digest,
                review.context_digest,
                review.audit_digest,
            )
            == (
                self.fit_session.review_anchor,
                initial.artifact_digest,
                refined.artifact_digest,
                context.artifact_digest,
                audit.artifact_digest,
            ),
            "study_fitted_review_inputs_changed",
        )
        _require(
            context.interface_kind == review.target_interface, "study_fitted_interface_changed"
        )
        scope = None
        if review.action != "approve":
            reason = "study_review_withdrawn"
            decision = ScopeDecision(decision="unknown", trace=(), reason=reason)
        elif plan.lane == "witness" and (witness is None or plan.method != "b1_always"):
            reason = "study_witness_requires_reviewed_unscoped_plan"
            decision = ScopeDecision(decision="unknown", trace=(), reason=reason)
        elif plan.method == "b1_always":
            reason = "study_unscoped_method"
            decision = ScopeDecision(decision="applicable", trace=())
        elif plan.method == "b2_interface":
            matched = context.interface_kind == review.source_interface
            reason = (
                "study_fixture_interface_matches" if matched else "study_fixture_interface_differs"
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
                reason = "study_fitted_scope_refused"
                decision = ScopeDecision(decision="unknown", trace=(), reason=fit.refusal_code)
            else:
                reason = "study_fitted_scope_evaluated"
                decision = evaluate_clauses(
                    scope.clauses, audit.record.features.model_dump(mode="json")
                )
        return _seal(
            StudyFittedAdmission(
                decision=decision.decision,
                reason_code=reason,
                source_digest=source.artifact_digest,
                target_digest=target.artifact_digest,
                map_digest=mapping.artifact_digest,
                review_digest=review.artifact_digest,
                witness_digest=witness.artifact_digest if witness else None,
                method=plan.method,
                lane=plan.lane,
                fit_review_digest=self.fit_session.review_anchor,
                initial_fit_digest=initial.artifact_digest,
                refined_fit_digest=refined.artifact_digest,
                context_digest=context.artifact_digest,
                audit_digest=audit.artifact_digest,
                scope_digest=scope.artifact_digest if scope else None,
                scope_decision=decision,
                artifact_digest=ZERO,
            )
        )

    def _make_authorization(self, plan, admission, **payload):
        return super()._make_authorization(
            plan,
            admission,
            **payload,
            **{
                field: getattr(admission, field)
                for field in (
                    "fit_review_digest",
                    "initial_fit_digest",
                    "refined_fit_digest",
                    "context_digest",
                    "audit_digest",
                    "scope_digest",
                )
            },
        )

    def _make_result(self, **payload):
        return super()._make_result(**payload, fit_review_anchor=self.fit_session.review_anchor)

    def _check_result_anchors(self, result):
        super()._check_result_anchors(result)
        _require(
            result.fit_review_anchor == self.fit_session.review_anchor,
            "study_fitted_result_fit_anchor_changed",
        )
