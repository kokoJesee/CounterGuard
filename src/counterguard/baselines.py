"""Frozen baseline definitions and a feature-only scope decision boundary."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from counterguard.digests import digest_json_artifact
from counterguard.models import Digest, FrozenModel, Guard, NonEmptyText, UtcDateTime
from counterguard.predicates import AstFeature as AstFeature
from counterguard.predicates import FeatureVector as FeatureVector

ScalarFeature = Literal[
    "contract_family",
    "contract_version",
    "interface_kind",
    "symbol_signature",
    "module_group",
]


class ConfusionCounts(FrozenModel):
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    tn: int = Field(ge=0)
    fn: int = Field(ge=0)


class ScopeClause(FrozenModel):
    field: ScalarFeature | Literal["ast_features"]
    op: Literal["eq", "contains"]
    value: NonEmptyText

    @model_validator(mode="after")
    def validate_operation(self) -> Self:
        if (self.field == "ast_features") != (self.op == "contains"):
            raise ValueError("Use contains for AST features and eq for scalar features")
        return self


class ScopePredicate(FrozenModel):
    schema_version: Literal["scope-predicate.v1"] = "scope-predicate.v1"
    scope_id: NonEmptyText
    guard_id: NonEmptyText
    guard_digest: Digest
    protocol_digest: Digest
    strategy: Literal["always", "fixed_interface", "learned_conjunction"]
    clauses: tuple[ScopeClause, ...] = Field(max_length=3)
    training_dataset_digest: Digest | None = None
    training_sample_ids: tuple[str, ...] = ()
    training_confusion: ConfusionCounts | None = None
    learner_version: NonEmptyText
    created_at: UtcDateTime
    artifact_digest: Digest

    @model_validator(mode="after")
    def validate_strategy(self) -> Self:
        if not self.scope_id.startswith("scp_"):
            raise ValueError("scope_id must use the scp_ namespace")
        if self.strategy == "always" and self.clauses:
            raise ValueError("B1 must have zero clauses")
        if self.strategy == "fixed_interface" and (
            len(self.clauses) != 1
            or self.clauses[0].field != "interface_kind"
            or self.clauses[0].op != "eq"
        ):
            raise ValueError("B2 must contain only one interface_kind equality")
        if self.strategy == "learned_conjunction" and (
            not self.clauses
            or self.training_dataset_digest is None
            or self.training_confusion is None
            or not self.training_sample_ids
        ):
            raise ValueError("Learned scopes require clauses and explicit training provenance")
        if self.strategy != "learned_conjunction" and (
            self.training_dataset_digest is not None
            or self.training_sample_ids
            or self.training_confusion is not None
        ):
            raise ValueError("Baselines cannot contain fitted training metadata")
        clause_keys = [(clause.field, clause.op, clause.value) for clause in self.clauses]
        if clause_keys != sorted(set(clause_keys)):
            raise ValueError("Clauses must be unique and canonically sorted")
        if len(self.training_sample_ids) != len(set(self.training_sample_ids)):
            raise ValueError("Training sample IDs must be unique")
        return self


class ClauseTrace(FrozenModel):
    field: str
    op: str
    expected: str
    actual: str | tuple[str, ...] | None
    matched: bool | None


class ScopeDecision(FrozenModel):
    decision: Literal["applicable", "inapplicable", "unknown"]
    trace: tuple[ClauseTrace, ...]
    reason: str | None = None


def make_baseline(
    guard: Guard,
    method: str,
    *,
    interface_kind: str,
    protocol_digest: Digest,
) -> ScopePredicate:
    if method not in {"b1_always", "b2_interface"}:
        raise ValueError("Only the two frozen baselines are implemented at this milestone")
    if interface_kind != guard.target_interface.interface_kind:
        raise ValueError("Baseline interface must match the verified Guard")
    clauses = (
        ()
        if method == "b1_always"
        else (ScopeClause(field="interface_kind", op="eq", value=interface_kind),)
    )
    draft = ScopePredicate(
        scope_id=f"scp_scope_v1_{method}_{guard.guard_id}",
        guard_id=guard.guard_id,
        guard_digest=guard.artifact_digest,
        protocol_digest=protocol_digest,
        strategy="always" if method == "b1_always" else "fixed_interface",
        clauses=clauses,
        learner_version="baseline.v1",
        created_at=datetime.now(UTC),
        artifact_digest="sha256:" + "0" * 64,
    )
    return ScopePredicate.model_validate(
        {**draft.model_dump(), "artifact_digest": digest_json_artifact(draft)}
    )


def decide_scope(scope: ScopePredicate, features: Mapping[str, object]) -> ScopeDecision:
    """Only the clauses determine which features can be read; IDs/labels stay outside."""
    return evaluate_clauses(scope.clauses, features)


def evaluate_clauses(
    clauses: tuple[ScopeClause, ...], features: Mapping[str, object]
) -> ScopeDecision:
    """Pure three-way predicate evaluation shared by separately authorized consumers."""
    trace = []
    for clause in clauses:
        actual = features.get(clause.field)
        if clause.op == "eq":
            valid = isinstance(actual, str) and bool(actual)
            value = actual if valid else None
            matched = actual == clause.value if valid else None
        else:
            valid = isinstance(actual, (list, tuple, set, frozenset)) and all(
                isinstance(v, str) for v in actual
            )
            value = tuple(sorted(actual)) if valid else None
            matched = clause.value in actual if valid else None
        trace.append(
            ClauseTrace(
                field=clause.field,
                op=clause.op,
                expected=clause.value,
                actual=value,
                matched=matched,
            )
        )
    if any(item.matched is None for item in trace):
        return ScopeDecision(
            decision="unknown", trace=tuple(trace), reason="Missing or invalid scope feature"
        )
    decision = "applicable" if all(item.matched for item in trace) else "inapplicable"
    return ScopeDecision(decision=decision, trace=tuple(trace))


def count_predictions(rows: list[tuple[bool, str]]) -> ConfusionCounts:
    """Count binary decisions; unknown needs a separate coverage report."""
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for label, decision in rows:
        if (
            type(label) is not bool
            or type(decision) is not str
            or decision not in {"applicable", "inapplicable"}
        ):
            raise ValueError(
                "Binary confusion counts require bool labels and known scope decisions"
            )
        predicted = decision == "applicable"
        counts["tp" if label and predicted else "fn" if label else "fp" if predicted else "tn"] += 1
    return ConfusionCounts(**counts)
