"""Optional feature-only certificates; never rewrite a learning or Scope artifact."""

import json
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from evidenceguard.artifacts import write_immutable
from evidenceguard.baselines import ScopeClause
from evidenceguard.digests import canonical_json_bytes, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.features import FeatureRecord
from evidenceguard.models import Digest, FrozenModel
from evidenceguard.predicates import FeatureVector
from evidenceguard.protocol import _load_model, _path, _read_samples, verify_protocol
from evidenceguard.replay import verify_scope_binding
from evidenceguard.scope import (
    FitManifest,
    ScopeLearningResult,
    TrainingExample,
    _matches,
    learn_scope,
)


class ClauseWitness(FrozenModel):
    clause: ScopeClause
    counterexample_features: tuple[FeatureVector, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_witnesses(self) -> Self:
        keys = tuple(canonical_json_bytes(row) for row in self.counterexample_features)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("Counterexample features must be unique and canonically sorted")
        return self


class ScopeExplanation(FrozenModel):
    schema_version: Literal["scope-explanation.v1"] = "scope-explanation.v1"
    learner_version: Literal["conjunction.v1"] = "conjunction.v1"
    label_basis: Literal["supplied_training_labels"] = "supplied_training_labels"
    learning_digest: Digest
    training_dataset_digest: Digest
    positive_count: int = Field(ge=2)
    negative_count: int = Field(ge=1)
    clause_witnesses: tuple[ClauseWitness, ...] = Field(min_length=1, max_length=3)
    artifact_digest: Digest

    @model_validator(mode="after")
    def removal_really_admits_each_witness(self) -> Self:
        clauses = tuple(item.clause for item in self.clause_witnesses)
        keys = [(item.field, item.op, item.value) for item in clauses]
        if keys != sorted(set(keys)):
            raise ValueError("Explained clauses must be unique and canonically sorted")
        for index, item in enumerate(self.clause_witnesses):
            reduced = clauses[:index] + clauses[index + 1 :]
            if any(
                _matches(clauses, features) or not _matches(reduced, features)
                for features in item.counterexample_features
            ):
                raise ValueError("Every witness must be rejected only by its removed clause")
        return self


def explain_scope(
    result: ScopeLearningResult, examples: tuple[TrainingExample, ...]
) -> ScopeExplanation:
    """Bind to the exact training multiset and list all distinct removal witnesses.

    This proves clause necessity relative to supplied negative labels, not that
    those labels are independently correct or that the rule generalizes.
    """
    if type(result) is not ScopeLearningResult:
        raise TypeError("Explanation requires an exact ScopeLearningResult")
    ScopeLearningResult.model_validate_json(result.model_dump_json())
    if result.artifact_digest != digest_json_artifact(result):
        raise ArtifactIntegrityError("Learning self digest does not match its contents")
    recomputed = learn_scope(examples)
    if (
        result.clauses != recomputed.clauses
        or result.training_dataset_digest != recomputed.training_dataset_digest
        or result.training_confusion != recomputed.training_confusion
        or (
            result.schema_version == "scope-learning.v1"
            and result.candidate_count != recomputed.combination_count
        )
        or (
            result.schema_version == "scope-learning.v2"
            and canonical_json_bytes(result) != canonical_json_bytes(recomputed)
        )
    ):
        raise ArtifactIntegrityError("Learning does not match the supplied training multiset")
    witnesses = []
    for index, clause in enumerate(result.clauses):
        reduced = result.clauses[:index] + result.clauses[index + 1 :]
        distinct = {
            canonical_json_bytes(row.features): row.features
            for row in examples
            if not row.guard_applicable and _matches(reduced, row.features)
        }
        witnesses.append(
            ClauseWitness(
                clause=clause,
                counterexample_features=tuple(distinct[key] for key in sorted(distinct)),
            )
        )
    draft = ScopeExplanation(
        learning_digest=result.artifact_digest,
        training_dataset_digest=result.training_dataset_digest,
        positive_count=sum(row.guard_applicable for row in examples),
        negative_count=sum(not row.guard_applicable for row in examples),
        clause_witnesses=tuple(witnesses),
        artifact_digest="sha256:" + "0" * 64,
    )
    return ScopeExplanation.model_validate_json(
        canonical_json_bytes(
            {**draft.model_dump(mode="json"), "artifact_digest": digest_json_artifact(draft)}
        )
    )


def verify_scope_explanation(
    explanation: ScopeExplanation,
    result: ScopeLearningResult,
    examples: tuple[TrainingExample, ...],
) -> None:
    """A self digest alone cannot prove that a witness was a training negative."""
    if type(explanation) is not ScopeExplanation:
        raise TypeError("Verification requires an exact ScopeExplanation")
    ScopeExplanation.model_validate_json(explanation.model_dump_json())
    if explanation.artifact_digest != digest_json_artifact(explanation):
        raise ArtifactIntegrityError("Explanation self digest does not match its contents")
    if canonical_json_bytes(explanation) != canonical_json_bytes(explain_scope(result, examples)):
        raise ArtifactIntegrityError("Explanation is not supported by the bound training evidence")


def explain_fitted_scopes(
    fit_path: str | Path, *, output: str | Path, cwd: str | Path
) -> dict[str, ScopeExplanation]:
    """Audit a published fit read-only, then append independent explanation files."""
    workspace = Path(cwd).resolve(strict=True)
    manifest_path = _path(Path(fit_path), workspace)
    destination = _path(Path(output), workspace)
    manifest = _load_model(manifest_path, FitManifest)
    protocol_path = Path("experiments/scope_v1.json")
    protocol, split, _ = verify_protocol(protocol_path, cwd=workspace)
    bindings = {item.guard_id: item for item in protocol.guards}
    first = manifest.groups[0]
    if first.guard_id not in bindings:
        raise ArtifactIntegrityError("Fitted Guard does not belong to the frozen protocol")
    # This audits all fit groups, their features, membership and learning results.
    _, verified_manifest = verify_scope_binding(
        Path(first.scope_ref),
        Path(bindings[first.guard_id].guard_ref),
        cwd=workspace,
        protocol_path=protocol_path,
        fit_manifest_path=manifest_path,
    )
    if verified_manifest != manifest:
        raise ArtifactIntegrityError("Fit changed while preparing explanations")
    audit = json.loads(_path(Path(manifest.feature_audit_ref), workspace).read_bytes())
    audit_rows = {item["sample_id"]: item for item in audit["entries"]}
    samples = {
        item.sample_id: item
        for file in split.files
        if file.split == "train"
        for item in _read_samples(_path(Path(file.path), workspace))
    }
    explanations = {}
    for group in manifest.groups:
        result = _load_model(_path(Path(group.learning_ref), workspace), ScopeLearningResult)
        examples = []
        for sample_id in group.training_sample_ids:
            audited = audit_rows[sample_id]
            record = _load_model(_path(Path(audited["feature_ref"]), workspace), FeatureRecord)
            if record.artifact_digest != audited["feature_digest"]:
                raise ArtifactIntegrityError("Audited training feature changed")
            examples.append(
                TrainingExample(
                    features=record.features,
                    guard_applicable=samples[sample_id].labels.guard_applicable,
                )
            )
        if result.artifact_digest != group.learning_digest:
            raise ArtifactIntegrityError("Learning changed while preparing explanations")
        explanations[group.guard_id] = explain_scope(result, tuple(examples))
    # No file is published until every group has a valid explanation.
    for guard_id, explanation in explanations.items():
        write_immutable(
            destination / f"{guard_id}.scope-explanation.json", canonical_json_bytes(explanation)
        )
    return explanations
