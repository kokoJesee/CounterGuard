"""Independent tool-owned full-snapshot research contracts; no execution authority."""

from copy import deepcopy
from typing import Annotated, Literal

from pydantic import Field, create_model, model_validator

from counterguard.models import Digest, FrozenModel
from counterguard.project_config import Identifier, RepositoryPath
from counterguard.snapshot_comparison_models import CaseId
from counterguard.standalone_contracts import CommitId
from counterguard.study_features import (
    StudyFeatureAudit,
    StudyFeatureContext,
    StudyFeatureRecord,
)
from counterguard.study_fit_models import (
    StudyFit,
    StudyFitProtocol,
    StudyFitReview,
    StudyLabelReview,
    StudyLearnedScope,
    StudySample,
    StudySplit,
)

PURPOSE = "tool_owned_snapshot_study_only"
EXTRACTOR = "ast-features.snapshot-study.v1"


def _fields(model):
    # Copy field constraints without inheriting fixture/observation model identity.
    # The relevant cross-field validators are explicitly retained below.
    return create_model(
        "_Snapshot" + model.__name__ + "Fields",
        __base__=FrozenModel,
        __module__=__name__,
        **{name: (field.annotation, deepcopy(field)) for name, field in model.model_fields.items()},
    )


class SnapshotStudySource(FrozenModel):
    schema_version: Literal["snapshot-study-source.v1"] = "snapshot-study-source.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    source_id: Identifier
    repository_identity_digest: Digest
    evidence_ref: RepositoryPath
    guard_ref: RepositoryPath
    binding_digest: Digest
    evidence_digest: Digest
    guard_digest: Digest
    source_review_digest: Digest
    buggy_commit: CommitId
    fixed_commit: CommitId
    head_commit: CommitId
    case_ids: Annotated[tuple[CaseId, ...], Field(min_length=1, max_length=256)]
    execution_allowed: Literal[False] = False
    artifact_digest: Digest

    @model_validator(mode="after")
    def unique_cases(self):
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("Snapshot study source cases must retain unique source identities")
        return self


class SnapshotStudyContext(_fields(StudyFeatureContext)):
    schema_version: Literal["snapshot-study-feature-context.v1"] = (
        "snapshot-study-feature-context.v1"
    )
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    target_digest: Digest
    definition_algorithm: Literal["direct_or_static-root-reexport.v2"] = (
        "direct_or_static-root-reexport.v2"
    )

    @model_validator(mode="after")
    def nonblank(self):
        return StudyFeatureContext.nonblank(self)


class SnapshotStudyFeatureRecord(_fields(StudyFeatureRecord)):
    schema_version: Literal["snapshot-study-feature-record.v1"] = "snapshot-study-feature-record.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    extractor: Literal["ast-features.snapshot-study.v1"] = EXTRACTOR
    target_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        return StudyFeatureRecord.coherent(self)


class SnapshotStudyFeatureAudit(_fields(StudyFeatureAudit)):
    schema_version: Literal["snapshot-study-feature-audit.v1"] = "snapshot-study-feature-audit.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    record: SnapshotStudyFeatureRecord


class SnapshotStudySample(_fields(StudySample)):
    schema_version: Literal["snapshot-study-sample.v1"] = "snapshot-study-sample.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE


class SnapshotStudyLabelReview(_fields(StudyLabelReview)):
    schema_version: Literal["snapshot-study-label-review.v1"] = "snapshot-study-label-review.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE

    @model_validator(mode="after")
    def coherent(self):
        return StudyLabelReview.coherent(self)


class SnapshotStudySplit(_fields(StudySplit)):
    schema_version: Literal["snapshot-study-split.v1"] = "snapshot-study-split.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE

    @model_validator(mode="after")
    def separated(self):
        return StudySplit.separated(self)


class SnapshotStudyFitProtocol(_fields(StudyFitProtocol)):
    schema_version: Literal["snapshot-study-fit-protocol.v1"] = "snapshot-study-fit-protocol.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    extractor: Literal["ast-features.snapshot-study.v1"] = EXTRACTOR


class SnapshotStudyFitReview(_fields(StudyFitReview)):
    schema_version: Literal["snapshot-study-fit-review.v1"] = "snapshot-study-fit-review.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE

    @model_validator(mode="after")
    def coherent(self):
        return StudyFitReview.coherent(self)


class SnapshotStudyLearnedScope(_fields(StudyLearnedScope)):
    schema_version: Literal["snapshot-study-learned-scope.v1"] = "snapshot-study-learned-scope.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE

    @model_validator(mode="after")
    def canonical(self):
        return StudyLearnedScope.canonical(self)


class SnapshotStudyFit(_fields(StudyFit)):
    schema_version: Literal["snapshot-study-fit.v1"] = "snapshot-study-fit.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = PURPOSE
    scope: SnapshotStudyLearnedScope | None

    @model_validator(mode="after")
    def coherent(self):
        return StudyFit.coherent(self)
