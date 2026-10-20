"""An unscoped observation under separate external review, using the shared Docker seam."""

from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import digest_json_artifact
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import DockerPolicyV1
from counterguard.standalone_capture import ZERO, _require, _seal
from counterguard.study_data import load_facts, load_review_model, persist
from counterguard.study_fit import _destination
from counterguard.study_observation_models import (
    StudyObservationAdmission,
    StudyObservationAuthorization,
    StudyObservationPlan,
    StudyObservationReplay,
    StudyObservationReview,
)
from counterguard.study_replay import StudySession


class StudyObservationSession(StudySession):
    _plan_model: ClassVar[type] = StudyObservationPlan
    _result_model: ClassVar[type] = StudyObservationReplay
    _authorization_model: ClassVar[type] = StudyObservationAuthorization

    def _review(self, plan):
        return load_review_model(
            self.workspace, plan.review_ref, self.review_anchor, StudyObservationReview
        )

    def _decide(self, plan, loaded, review):
        _require(loaded[3] is not None, "observation_requires_reviewed_stdout_witness")
        original = super()._decide(plan, loaded, review)
        return _seal(
            StudyObservationAdmission(
                **original.model_dump(exclude={"schema_version", "artifact_digest"}),
                artifact_digest=ZERO,
            )
        )


def issue_observation_review(
    source_repo,
    target_repo,
    workspace,
    plan,
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
    """Trusted local external approval; the returned anchor stays outside mutable plans."""
    session = StudyObservationSession(source_repo, target_repo, workspace, ZERO)
    plan = session._checked_plan(plan)
    loaded = load_facts(session.source_repo, session.target_repo, session.workspace, plan)
    source, target, mapping, witness, _, facts, _, _ = loaded
    _require(witness is not None, "observation_requires_reviewed_stdout_witness")
    runner = resolve_runner(runner_id=runner_id, image_digest=None)
    _require(runner == facts[2].runner, "study_source_runner_mismatch")
    previous = None
    if previous_ref is not None:
        previous = load_review_model(
            session.workspace, previous_ref, previous_anchor, StudyObservationReview
        )
    else:
        _require(previous_anchor is None, "study_review_predecessor_incomplete")
    review = _seal(
        StudyObservationReview(
            review_id=review_id,
            created_at=datetime.now(UTC),
            operator=operator,
            reason=reason,
            action=action,
            source_digest=source.artifact_digest,
            target_digest=target.artifact_digest,
            map_digest=mapping.artifact_digest,
            witness_digest=witness.artifact_digest,
            source_interface=source_interface,
            target_interface=target_interface,
            runner=runner,
            policy_digest=digest_json_artifact(DockerPolicyV1()),
            implementation_digests=inspection_implementation_digests(),
            previous_review_ref=previous_ref,
            previous_review_digest=previous.artifact_digest if previous else None,
            artifact_digest=ZERO,
        )
    )
    output = _destination(
        session.workspace, Path(output_ref), (session.source_repo, session.target_repo)
    )
    return persist(output, review)
