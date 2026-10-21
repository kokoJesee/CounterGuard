"""Independent reviewed external observations; never fixture or production authority."""

from copy import deepcopy
from typing import Annotated, Literal

from pydantic import Field, create_model, model_validator

from counterguard.models import Digest, FrozenModel
from counterguard.project_config import RepositoryPath
from counterguard.snapshot_comparison_models import (
    SnapshotComparisonAdmission,
    SnapshotComparisonAuthorization,
    SnapshotComparisonMap,
    SnapshotComparisonPlan,
    SnapshotComparisonReplay,
    SnapshotComparisonReview,
    SnapshotComparisonTarget,
    SnapshotOwnWitness,
)
from counterguard.snapshot_models import (
    SnapshotAuthorization,
    SnapshotEvidence,
    SnapshotGuard,
    SnapshotReview,
)

RepositoryUrl = Annotated[
    str,
    Field(
        pattern=r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
        min_length=22,
        max_length=512,
        strict=True,
    ),
]
PURPOSE = "reviewed_external_snapshot_observation_only"


def _independent_fields(model):
    # Share field constraints, not fixture ancestry. Pydantic accepts subclass
    # instances without revalidation even when their schema literals differ.
    return create_model(
        "_" + model.__name__ + "Fields",
        __base__=FrozenModel,
        __module__=__name__,
        **{name: (field.annotation, deepcopy(field)) for name, field in model.model_fields.items()},
    )


class ExternalSnapshotReview(_independent_fields(SnapshotReview)):
    schema_version: Literal["external-snapshot-review.v1"] = "external-snapshot-review.v1"
    purpose: Literal["reviewed_external_snapshot_observation_only"] = PURPOSE
    review_kind: Literal["execution"] = "execution"
    repository_url: RepositoryUrl
    license_ref: RepositoryPath
    license_digest: Digest
    semantic_authority: Literal["execution_review_not_semantic_labels"] = (
        "execution_review_not_semantic_labels"
    )


class ExternalSnapshotAuthorization(_independent_fields(SnapshotAuthorization)):
    schema_version: Literal["external-snapshot-authorization.v1"] = (
        "external-snapshot-authorization.v1"
    )
    purpose: Literal["external_snapshot_capture", "external_snapshot_guard_check"]


class ExternalSnapshotEvidence(_independent_fields(SnapshotEvidence)):
    schema_version: Literal["external-snapshot-evidence.v1"] = "external-snapshot-evidence.v1"
    purpose: Literal["reviewed_external_snapshot_observation_only"] = PURPOSE


class ExternalSnapshotGuard(_independent_fields(SnapshotGuard)):
    schema_version: Literal["external-snapshot-guard.v1"] = "external-snapshot-guard.v1"
    purpose: Literal["reviewed_external_snapshot_observation_only"] = PURPOSE
    state: Literal["external_observation_candidate_not_schedulable"] = (
        "external_observation_candidate_not_schedulable"
    )


class ExternalSnapshotTarget(_independent_fields(SnapshotComparisonTarget)):
    schema_version: Literal["external-snapshot-target.v1"] = "external-snapshot-target.v1"
    repository_url: RepositoryUrl


class ExternalSnapshotMap(_independent_fields(SnapshotComparisonMap)):
    schema_version: Literal["external-snapshot-map.v1"] = "external-snapshot-map.v1"


class ExternalSnapshotWitness(_independent_fields(SnapshotOwnWitness)):
    schema_version: Literal["external-snapshot-own-witness.v1"] = "external-snapshot-own-witness.v1"

    @model_validator(mode="after")
    def finite_witness(self):
        return SnapshotOwnWitness.finite_witness(self)


class ExternalComparisonReview(_independent_fields(SnapshotComparisonReview)):
    schema_version: Literal["external-snapshot-comparison-review.v1"] = (
        "external-snapshot-comparison-review.v1"
    )
    purpose: Literal["reviewed_external_snapshot_observation_only"] = PURPOSE


class ExternalComparisonPlan(_independent_fields(SnapshotComparisonPlan)):
    schema_version: Literal["external-snapshot-comparison-plan.v1"] = (
        "external-snapshot-comparison-plan.v1"
    )
    purpose: Literal["reviewed_external_snapshot_observation_only"] = PURPOSE
    # This version observes original Guard / own oracle, without fitting or
    # exporting four-method research predictions under an unreviewed protocol.
    method: Literal["b1_always"] = "b1_always"


class ExternalComparisonAdmission(_independent_fields(SnapshotComparisonAdmission)):
    schema_version: Literal["external-snapshot-comparison-admission.v1"] = (
        "external-snapshot-comparison-admission.v1"
    )
    method: Literal["b1_always"] = "b1_always"


class ExternalComparisonAuthorization(_independent_fields(SnapshotComparisonAuthorization)):
    schema_version: Literal["external-snapshot-comparison-authorization.v1"] = (
        "external-snapshot-comparison-authorization.v1"
    )
    purpose: Literal["reviewed_external_snapshot_observation_only"] = PURPOSE


class ExternalComparisonReplay(_independent_fields(SnapshotComparisonReplay)):
    schema_version: Literal["external-snapshot-comparison-replay.v1"] = (
        "external-snapshot-comparison-replay.v1"
    )
    purpose: Literal["reviewed_external_snapshot_observation_only"] = PURPOSE
    admission: ExternalComparisonAdmission
