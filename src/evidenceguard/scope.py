"""A feature-only deterministic learner, wrapped by provenance and split enforcement."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from evidenceguard.artifacts import write_immutable
from evidenceguard.baselines import ConfusionCounts, ScopeClause, ScopePredicate
from evidenceguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError, InsufficientScopeEvidence
from evidenceguard.evidence import verify_evidence
from evidenceguard.features import FeatureRecord, audit_features
from evidenceguard.models import ArtifactRef, Digest, FrozenModel, NonEmptyText, UtcDateTime
from evidenceguard.module_context import SCOPE_V1_CONTEXT_DIGEST
from evidenceguard.predicates import FeatureVector
from evidenceguard.protocol import _load_model, _path, _read_samples, verify_protocol

LEARNER_VERSION = "conjunction.v1"
SCOPE_V1_PROTOCOL_DIGEST = "sha256:1f401186a3f51c17e582dbbdc96f9324e47e128f90fcb91f29594690bc8daa3a"
FIELD_ORDER = (
    "contract_family",
    "contract_version",
    "interface_kind",
    "symbol_signature",
    "module_group",
    "ast_features",
)


class TrainingExample(FrozenModel):
    features: FeatureVector
    guard_applicable: bool

    @field_validator("features", mode="after")
    @classmethod
    def exact_feature_boundary(cls, value):
        if isinstance(value, FeatureVector) and type(value) is not FeatureVector:
            raise ValueError("FeatureVector subclasses may contain forbidden fields")
        return value


class ScopeLearningResult(FrozenModel):
    schema_version: Literal["scope-learning.v1"] = "scope-learning.v1"
    learner_version: Literal["conjunction.v1"] = LEARNER_VERSION
    clauses: tuple[ScopeClause, ...] = Field(min_length=1, max_length=3)
    training_dataset_digest: Digest
    training_confusion: ConfusionCounts
    candidate_count: int = Field(gt=0)
    artifact_digest: Digest

    @model_validator(mode="after")
    def supported_result(self) -> Self:
        counts = self.training_confusion
        if counts.tp < 2 or counts.tn < 1 or counts.fp or counts.fn:
            raise ValueError(
                "Published learning results require sufficient zero-error training evidence"
            )
        keys = [(clause.field, clause.op, clause.value) for clause in self.clauses]
        if keys != sorted(set(keys)):
            raise ValueError("Learned clauses must be unique and canonically sorted")
        return self


def _matches(clauses: tuple[ScopeClause, ...], features: FeatureVector) -> bool:
    return all(
        getattr(features, clause.field) == clause.value
        if clause.op == "eq"
        else clause.value in features.ast_features
        for clause in clauses
    )


def _confusion(
    clauses: tuple[ScopeClause, ...], examples: tuple[TrainingExample, ...]
) -> ConfusionCounts:
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for example in examples:
        predicted = _matches(clauses, example.features)
        key = (
            "tp"
            if example.guard_applicable and predicted
            else "fn"
            if example.guard_applicable
            else "fp"
            if predicted
            else "tn"
        )
        counts[key] += 1
    return ConfusionCounts(**counts)


def learn_scope(examples: tuple[TrainingExample, ...]) -> ScopeLearningResult:
    """Search receives neither Guard/FeatureRecord nor sample identity or provenance."""
    if type(examples) is not tuple or any(type(row) is not TrainingExample for row in examples):
        raise TypeError("Learner accepts only a tuple of exact TrainingExample values")
    # Validate again at the boundary, including objects made through model_construct.
    for row in examples:
        if type(row.features) is not FeatureVector or type(row.guard_applicable) is not bool:
            raise TypeError("Learner accepts only exact FeatureVector and bool fields")
        TrainingExample.model_validate_json(row.model_dump_json())
    positive = tuple(row for row in examples if row.guard_applicable)
    negative = tuple(row for row in examples if not row.guard_applicable)
    if len(positive) < 2:
        raise InsufficientScopeEvidence(
            "too_few_positives", "At least two applicable examples are required"
        )
    if not negative:
        raise InsufficientScopeEvidence(
            "no_counterexample", "A confirmed inapplicable counterexample is required"
        )
    labels = {}
    for row in examples:
        key = canonical_json_bytes(row.features)
        if key in labels and labels[key] != row.guard_applicable:
            raise InsufficientScopeEvidence(
                "conflicting_labels", "Identical FeatureVectors have conflicting labels"
            )
        labels[key] = row.guard_applicable
    candidate_keys = set()
    for row in positive:
        for field in FIELD_ORDER[:-1]:
            candidate_keys.add((field, "eq", getattr(row.features, field)))
        for token in row.features.ast_features:
            candidate_keys.add(("ast_features", "contains", token))
    candidates = tuple(
        ScopeClause(field=field, op=op, value=value) for field, op, value in sorted(candidate_keys)
    )
    rules = []
    tested = 0
    for size in range(1, 4):
        for clauses in itertools.combinations(candidates, size):
            tested += 1
            counts = _confusion(clauses, examples)
            if counts.fp or counts.fn:
                continue
            if not all(
                any(
                    _matches(clauses[:index] + clauses[index + 1 :], row.features)
                    for row in negative
                )
                for index in range(len(clauses))
            ):
                continue
            rules.append((clauses, counts))
    if not rules:
        raise InsufficientScopeEvidence(
            "no_supported_rule", "No irredundant zero-error conjunction within three clauses"
        )

    def ranking(item):
        clauses = item[0]
        return (
            len(clauses),
            sum(clause.field == "ast_features" for clause in clauses),
            tuple(sorted(FIELD_ORDER.index(clause.field) for clause in clauses)),
            canonical_json_bytes(clauses),
        )

    clauses, counts = min(rules, key=ranking)
    input_digest = digest_bytes(
        canonical_json_bytes(
            sorted([row.model_dump(mode="json") for row in examples], key=canonical_json_bytes)
        )
    )
    draft = ScopeLearningResult(
        clauses=clauses,
        training_dataset_digest=input_digest,
        training_confusion=counts,
        candidate_count=tested,
        artifact_digest="sha256:" + "0" * 64,
    )
    return ScopeLearningResult.model_validate(
        {**draft.model_dump(), "artifact_digest": digest_json_artifact(draft)}
    )


class FitGroup(FrozenModel):
    guard_id: NonEmptyText
    guard_digest: Digest
    training_sample_ids: tuple[NonEmptyText, ...]
    source_bug_sample_id: NonEmptyText
    fixed_sample_id: NonEmptyText
    training_dataset_digest: Digest
    learning_ref: ArtifactRef
    learning_digest: Digest
    scope_ref: ArtifactRef
    scope_digest: Digest

    @model_validator(mode="after")
    def source_pair_in_training(self) -> Self:
        if tuple(sorted(set(self.training_sample_ids))) != self.training_sample_ids:
            raise ValueError("Training identities must be sorted and unique")
        pair = {self.source_bug_sample_id, self.fixed_sample_id}
        if len(pair) != 2 or not pair.issubset(self.training_sample_ids):
            raise ValueError("Fit must contain distinct source-bug and fixed identities")
        return self


class FitManifest(FrozenModel):
    schema_version: Literal["fit-manifest.v1"] = "fit-manifest.v1"
    protocol_id: Literal["scope_v1"] = "scope_v1"
    protocol_digest: Digest
    split_digest: Digest
    phase: Literal["initial", "refined"]
    module_context_ref: ArtifactRef
    module_context_digest: Digest
    feature_audit_ref: ArtifactRef
    feature_audit_digest: Digest
    train_file_digests: dict[ArtifactRef, Digest]
    groups: tuple[FitGroup, ...]
    created_at: UtcDateTime
    artifact_digest: Digest

    @model_validator(mode="after")
    def distinct_groups(self) -> Self:
        if len(self.groups) != 2 or len({group.guard_id for group in self.groups}) != 2:
            raise ValueError("Fit manifest requires two distinct Guard groups")
        return self


def fit_scopes(
    path: str | Path,
    *,
    phase: str,
    output: str | Path,
    cwd: str | Path,
    artifact_root: str | Path = "artifacts",
) -> FitManifest:
    if phase not in {"initial", "refined"}:
        raise ValueError("Phase must be initial or refined; holdout cannot be fitted")
    workspace = Path(cwd).resolve(strict=True)
    protocol, split, guards = verify_protocol(path, cwd=workspace)
    if protocol.artifact_digest != SCOPE_V1_PROTOCOL_DIGEST:
        raise ArtifactIntegrityError("Frozen scope_v1 protocol changed; use a new protocol")
    root = _path(Path(artifact_root), workspace)
    destination = _path(Path(output), workspace)
    audit_ref = (root / "audits/scope-v1-features-context.json").relative_to(workspace).as_posix()
    context_ref = "benchmarks/context/scope_v1.json"
    report = audit_features(
        benchmark_root="benchmarks",
        output=audit_ref,
        cwd=workspace,
        artifact_root=root,
        module_context_path=context_ref,
    )
    expected_ids = set().union(
        *(
            set(part.initial + part.refinement_additions + part.holdout)
            for part in split.phases.values()
        )
    )
    if report["mismatched"] or report["errors"] or report["matched"] != len(expected_ids):
        raise InsufficientScopeEvidence(
            "feature_audit_failed", "Feature/context audit must pass before learning"
        )
    if (
        report["module_context_digest"] != SCOPE_V1_CONTEXT_DIGEST
        or report["dataset_digests"] != {item.path: item.content_digest for item in split.files}
        or {row["sample_id"] for row in report["entries"]} != expected_ids
    ):
        raise ArtifactIntegrityError("Feature audit does not cover the frozen protocol and context")
    audit_rows = {row["sample_id"]: row for row in report["entries"]}
    samples = {
        sample.sample_id: sample
        for item in split.files
        if item.split == "train"
        for sample in _read_samples(_path(Path(item.path), workspace))
    }
    computations = []
    for guard_id, phases in split.phases.items():
        selected = (
            phases.initial if phase == "initial" else phases.initial + phases.refinement_additions
        )
        if set(selected) & set(phases.holdout) or any(
            sample_id not in samples for sample_id in selected
        ):
            raise InsufficientScopeEvidence(
                "holdout_leakage", "Only frozen training members may enter fit"
            )
        selected_samples = [samples[sample_id] for sample_id in sorted(selected)]
        guard = guards[guard_id]
        evidence = verify_evidence(guard.source_evidence_ref, cwd=workspace)
        source_ids = {}
        for role, target in (("buggy", evidence.buggy_target), ("fixed", evidence.fixed_target)):
            matches = [
                sample.sample_id
                for sample in selected_samples
                if (sample.target.module, sample.target.symbol) == (target.module, target.symbol)
                and sample.labels.guard_applicable
            ]
            if len(matches) != 1:
                raise InsufficientScopeEvidence(
                    "missing_source_pair",
                    "Fit must contain the verified source-bug and fixed positive pair",
                )
            source_ids[role] = matches[0]
        if not any(
            not sample.labels.guard_applicable and sample.labels.contract_compliant
            for sample in selected_samples
        ):
            raise InsufficientScopeEvidence(
                "no_legal_counterexample",
                "Fit requires at least one confirmed legal counterexample",
            )
        examples = []
        for sample in selected_samples:
            row = audit_rows[sample.sample_id]
            record = _load_model(_path(Path(row["feature_ref"]), workspace), FeatureRecord)
            if (
                record.schema_version != "feature-extraction.v2"
                or record.artifact_digest != row["feature_digest"]
                or record.module_context_digest != SCOPE_V1_CONTEXT_DIGEST
                or (record.target.module, record.target.symbol)
                != (sample.target.module, sample.target.symbol)
            ):
                raise ArtifactIntegrityError("FeatureRecord source/context identity mismatch")
            examples.append(
                TrainingExample(
                    features=record.features, guard_applicable=sample.labels.guard_applicable
                )
            )
        result = learn_scope(tuple(examples))
        computations.append((guard, selected, source_ids, result))
    # All groups must succeed before publishing any fitted scopes.
    groups = []
    for guard, selected, source_ids, result in computations:
        scope_path = destination / f"{guard.guard_id}.json"
        created_at = (
            _load_model(scope_path, ScopePredicate).created_at
            if scope_path.exists()
            else datetime.now(UTC)
        )
        draft = ScopePredicate(
            scope_id=f"scp_scope_v1_{phase}_{guard.guard_id}",
            guard_id=guard.guard_id,
            guard_digest=guard.artifact_digest,
            protocol_digest=protocol.artifact_digest,
            strategy="learned_conjunction",
            clauses=result.clauses,
            learner_version=LEARNER_VERSION,
            training_dataset_digest=result.training_dataset_digest,
            training_sample_ids=tuple(sorted(selected)),
            training_confusion=result.training_confusion,
            created_at=created_at,
            artifact_digest="sha256:" + "0" * 64,
        )
        scope = ScopePredicate.model_validate(
            {**draft.model_dump(), "artifact_digest": digest_json_artifact(draft)}
        )
        learning_path = destination / f"{guard.guard_id}.learning.json"
        write_immutable(learning_path, canonical_json_bytes(result))
        write_immutable(scope_path, canonical_json_bytes(scope))
        groups.append(
            FitGroup(
                guard_id=guard.guard_id,
                guard_digest=guard.artifact_digest,
                training_sample_ids=tuple(sorted(selected)),
                source_bug_sample_id=source_ids["buggy"],
                fixed_sample_id=source_ids["fixed"],
                training_dataset_digest=result.training_dataset_digest,
                learning_ref=learning_path.relative_to(workspace).as_posix(),
                learning_digest=result.artifact_digest,
                scope_ref=scope_path.relative_to(workspace).as_posix(),
                scope_digest=scope.artifact_digest,
            )
        )
    manifest_path = destination / "fit-manifest.json"
    created_at = (
        _load_model(manifest_path, FitManifest).created_at
        if manifest_path.exists()
        else datetime.now(UTC)
    )
    draft = FitManifest(
        protocol_digest=protocol.artifact_digest,
        split_digest=split.artifact_digest,
        phase=phase,
        module_context_ref=context_ref,
        module_context_digest=SCOPE_V1_CONTEXT_DIGEST,
        feature_audit_ref=audit_ref,
        feature_audit_digest=report["artifact_digest"],
        train_file_digests={
            item.path: item.content_digest for item in split.files if item.split == "train"
        },
        groups=tuple(groups),
        created_at=created_at,
        artifact_digest="sha256:" + "0" * 64,
    )
    manifest = FitManifest.model_validate(
        {**draft.model_dump(), "artifact_digest": digest_json_artifact(draft)}
    )
    write_immutable(manifest_path, canonical_json_bytes(manifest))
    return manifest
