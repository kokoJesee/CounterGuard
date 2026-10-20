"""Closed, explicitly reviewed external observations; never training or production authority."""

from typing import Literal

from counterguard.models import ArtifactRef, Digest
from counterguard.study_models import (
    StudyAdmission,
    StudyAuthorization,
    StudyReplay,
    StudyReplayPlan,
    StudyReview,
)

Purpose = Literal["external_snapshot_observation_only"]
Policy = Literal["original_guard_and_reviewed_stdout_subset_no_labels.v1"]


class StudyObservationPlan(StudyReplayPlan):
    schema_version: Literal["study-replay-plan.v3"] = "study-replay-plan.v3"
    purpose: Purpose = "external_snapshot_observation_only"
    method: Literal["b1_always"] = "b1_always"
    witness_ref: ArtifactRef
    observation_policy: Policy = "original_guard_and_reviewed_stdout_subset_no_labels.v1"


class StudyObservationReview(StudyReview):
    schema_version: Literal["study-review.v3"] = "study-review.v3"
    purpose: Purpose = "external_snapshot_observation_only"
    interface_vocabulary: Literal["external-observation-io.v1"] = "external-observation-io.v1"
    witness_digest: Digest
    observation_policy: Policy = "original_guard_and_reviewed_stdout_subset_no_labels.v1"


class StudyObservationAdmission(StudyAdmission):
    schema_version: Literal["study-admission.v3"] = "study-admission.v3"
    method: Literal["b1_always"] = "b1_always"
    witness_digest: Digest
    scope_interpretation: Literal["execution_policy_not_semantic_label"] = (
        "execution_policy_not_semantic_label"
    )


class StudyObservationAuthorization(StudyAuthorization):
    schema_version: Literal["docker-execution-authorization.v8"] = (
        "docker-execution-authorization.v8"
    )
    purpose: Purpose = "external_snapshot_observation_only"
    witness_digest: Digest
    observation_policy: Policy = "original_guard_and_reviewed_stdout_subset_no_labels.v1"


class StudyObservationReplay(StudyReplay):
    schema_version: Literal["study-replay.v3"] = "study-replay.v3"
    purpose: Purpose = "external_snapshot_observation_only"
    admission: StudyObservationAdmission | None
    observation_policy: Policy = "original_guard_and_reviewed_stdout_subset_no_labels.v1"
