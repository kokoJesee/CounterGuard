"""Frozen scope_v1 formulas; unknown remains explicit in the raw predictions."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from counterguard.baselines import ClauseTrace, ConfusionCounts
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.models import Digest, FrozenModel, NonEmptyText, RunOutcome
from counterguard.protocol import SampleLabels
from counterguard.replay import ReplayResult

Method = Literal["b1_always", "b2_interface", "learned_initial", "learned_refined"]
METHOD_ORDER = ("b1_always", "b2_interface", "learned_initial", "learned_refined")
METRIC_VERSION = "scope-v1-metrics.v1"


class Prediction(FrozenModel):
    method: Method
    guard_id: NonEmptyText
    sample_id: NonEmptyText
    labels: SampleLabels
    scope_decision: Literal["applicable", "inapplicable", "unknown"]
    decision_trace: tuple[ClauseTrace, ...]
    verdict: NonEmptyText
    violated_case_ids: tuple[str, ...]
    run_outcome: RunOutcome | None

    @model_validator(mode="after")
    def consistent_row(self) -> Self:
        if self.labels.guard_id != self.guard_id:
            raise ValueError("Prediction label belongs to a different Guard")
        if self.scope_decision != "applicable":
            expected = (
                "skipped_unknown" if self.scope_decision == "unknown" else "skipped_inapplicable"
            )
            if self.run_outcome is not None or self.verdict != expected or self.violated_case_ids:
                raise ValueError(
                    "Skipped prediction must preserve its actual decision and run=null"
                )
        elif self.verdict not in {
            "pass",
            "violation",
            "collection_error",
            "execution_error",
            "timeout",
            "stale",
        }:
            raise ValueError("Unknown execution verdict")
        if self.verdict == "pass" and self.run_outcome is not RunOutcome.PASSED:
            raise ValueError("Pass requires a real passed execution")
        if self.verdict == "violation" and (
            self.run_outcome is not RunOutcome.TEST_FAILED or not self.violated_case_ids
        ):
            raise ValueError("Alert requires real failed Guard cases")
        return self


def prediction_from_replay(
    method: Method, sample_id: str, labels: SampleLabels, replay: ReplayResult
):
    return Prediction(
        method=method,
        guard_id=replay.guard_id,
        sample_id=sample_id,
        labels=labels,
        scope_decision=replay.scope_decision,
        decision_trace=replay.decision_trace,
        verdict=replay.verdict,
        violated_case_ids=replay.violated_case_ids,
        run_outcome=replay.run.outcome if replay.run else None,
    )


class Metric(FrozenModel):
    numerator: float | None = Field(ge=0, allow_inf_nan=False)
    denominator: float = Field(ge=0, allow_inf_nan=False)
    value: float | None = Field(ge=0, allow_inf_nan=False)
    reason: str | None
    included_guards: tuple[str, ...] = ()
    components: dict[str, Metric] = {}

    @model_validator(mode="after")
    def honest_ratio(self) -> Self:
        undefined = self.numerator is None or self.denominator == 0
        if undefined:
            if self.value is not None or not self.reason:
                raise ValueError("Undefined metrics require null and an explicit reason")
        elif self.value != self.numerator / self.denominator or self.reason is not None:
            raise ValueError("Metric value must follow its recorded numerator and denominator")
        return self


def ratio(numerator: int | float, denominator: int | float) -> Metric:
    return Metric(
        numerator=float(numerator),
        denominator=float(denominator),
        value=numerator / denominator if denominator else None,
        reason=None if denominator else "zero_denominator",
    )


class SliceMetrics(FrozenModel):
    sample_count: int = Field(ge=0)
    confusion: ConfusionCounts
    unknown_count: int = Field(ge=0)
    execution_count: int = Field(ge=0)
    verdict_counts: dict[str, int]
    scope: dict[str, Metric]
    end_to_end: dict[str, Metric]


class MethodMetrics(FrozenModel):
    micro: SliceMetrics
    per_guard: dict[str, SliceMetrics]
    macro_scope: dict[str, Metric]
    macro_end_to_end: dict[str, Metric]


class EvaluationMetrics(FrozenModel):
    schema_version: Literal["evaluation-metrics.v1"] = "evaluation-metrics.v1"
    metric_version: Literal["scope-v1-metrics.v1"] = METRIC_VERSION
    unknown_policy: Literal["negative_prediction_with_separate_coverage"] = (
        "negative_prediction_with_separate_coverage"
    )
    methods: dict[Method, MethodMetrics]
    artifact_digest: Digest


def slice_metrics(rows: tuple[Prediction, ...]) -> SliceMetrics:
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for row in rows:
        # Explicit D9 policy: unknown is a negative prediction, not a renamed
        # inapplicable decision. Never pass unknown to binary count_predictions.
        predicted = row.scope_decision == "applicable"
        counts[
            "tp"
            if row.labels.guard_applicable and predicted
            else "fn"
            if row.labels.guard_applicable
            else "fp"
            if predicted
            else "tn"
        ] += 1
    tp, fp, tn, fn = (counts[key] for key in ("tp", "fp", "tn", "fn"))
    n = len(rows)
    unknown = sum(row.scope_decision == "unknown" for row in rows)
    scope = {
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "specificity": ratio(tn, tn + fp),
        "false_application_rate": ratio(fp, fp + tn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "accuracy": ratio(tp + tn, n),
        "execution_coverage": ratio(tp + fp, n),
        "unknown_rate": ratio(unknown, n),
        "decision_coverage": ratio(n - unknown, n),
    }
    components = {key: scope[key] for key in ("recall", "specificity")}
    balanced = (
        (scope["recall"].value + scope["specificity"].value)
        if all(item.value is not None for item in components.values())
        else None
    )
    scope["balanced_accuracy"] = Metric(
        numerator=balanced,
        denominator=2.0,
        value=balanced / 2 if balanced is not None else None,
        reason=None if balanced is not None else "undefined_component",
        components=components,
    )

    def bugs(row):
        return row.labels.guard_applicable and row.labels.guard_violation is True

    def alert(row):
        return row.scope_decision == "applicable" and row.verdict == "violation"

    def clean(row):
        return row.labels.guard_applicable and row.labels.guard_violation is False

    runs = tuple(row for row in rows if row.run_outcome is not None)
    valid = sum(row.run_outcome in {RunOutcome.PASSED, RunOutcome.TEST_FAILED} for row in runs)
    e2e = {
        "bug_recall": ratio(sum(bugs(row) and alert(row) for row in rows), sum(map(bugs, rows))),
        "false_alert_rate": ratio(
            sum(alert(row) and not bugs(row) for row in rows), sum(not bugs(row) for row in rows)
        ),
        "applicable_clean_pass_rate": ratio(
            sum(clean(row) and row.verdict == "pass" for row in rows), sum(map(clean, rows))
        ),
        "execution_validity": ratio(valid, len(runs)),
        "infrastructure_failure_rate": ratio(len(runs) - valid, len(runs)),
    }
    verdicts = (
        "pass",
        "violation",
        "skipped_inapplicable",
        "skipped_unknown",
        "collection_error",
        "execution_error",
        "timeout",
        "stale",
    )
    return SliceMetrics(
        sample_count=n,
        confusion=ConfusionCounts(**counts),
        unknown_count=unknown,
        execution_count=len(runs),
        verdict_counts={key: sum(r.verdict == key for r in rows) for key in verdicts},
        scope=scope,
        end_to_end=e2e,
    )


def _macro(guards: dict[str, SliceMetrics], section: str) -> dict[str, Metric]:
    names = getattr(next(iter(guards.values())), section)
    result = {}
    for name in names:
        components = {guard: getattr(item, section)[name] for guard, item in sorted(guards.items())}
        included = tuple(guard for guard, metric in components.items() if metric.value is not None)
        numerator = sum(components[guard].value for guard in included)
        base = ratio(numerator, len(included))
        result[name] = Metric(
            **base.model_dump(exclude={"included_guards", "components"}),
            included_guards=included,
            components=components,
        )
    return result


def compute_metrics(rows: tuple[Prediction, ...]) -> EvaluationMetrics:
    identities = {(r.method, r.guard_id, r.sample_id) for r in rows}
    if len(identities) != len(rows):
        raise ValueError("Duplicate evaluation row")
    members = [
        {(r.guard_id, r.sample_id) for r in rows if r.method == method} for method in METHOD_ORDER
    ]
    if not members[0] or any(group != members[0] for group in members):
        raise ValueError("Every method must cover exactly the same nonempty sample set")
    if any(
        len({canonical_json_bytes(r.labels) for r in rows if (r.guard_id, r.sample_id) == identity})
        != 1
        for identity in members[0]
    ):
        raise ValueError("Methods cannot use different labels for the same sample")
    methods = {}
    for method in METHOD_ORDER:
        selected = tuple(row for row in rows if row.method == method)
        guards = {
            guard: slice_metrics(tuple(r for r in selected if r.guard_id == guard))
            for guard in sorted({r.guard_id for r in selected})
        }
        methods[method] = MethodMetrics(
            micro=slice_metrics(selected),
            per_guard=guards,
            macro_scope=_macro(guards, "scope"),
            macro_end_to_end=_macro(guards, "end_to_end"),
        )
    draft = EvaluationMetrics(methods=methods, artifact_digest="sha256:" + "0" * 64)
    return draft.model_copy(update={"artifact_digest": digest_json_artifact(draft)})


def paired_refinement(rows: tuple[Prediction, ...], metrics: EvaluationMetrics) -> dict:
    initial = {(r.guard_id, r.sample_id): r for r in rows if r.method == "learned_initial"}
    refined = {(r.guard_id, r.sample_id): r for r in rows if r.method == "learned_refined"}
    if initial.keys() != refined.keys():
        raise ValueError("Paired refinement requires identical sample membership")
    entries = []
    for identity, before in sorted(initial.items()):
        after = refined[identity]
        positive = before.labels.guard_applicable
        first, second = before.scope_decision == "applicable", after.scope_decision == "applicable"
        entries.append(
            {
                "guard_id": identity[0],
                "sample_id": identity[1],
                "initial_decision": before.scope_decision,
                "refined_decision": after.scope_decision,
                "corrected_false_application": not positive
                and first
                and after.scope_decision == "inapplicable",
                "retained_applicable_case": positive and first and second,
                "new_false_rejection": positive and first and not second,
                "new_false_application": not positive and not first and second,
            }
        )
    totals = {
        plural: sum(entry[singular] for entry in entries)
        for plural, singular in (
            ("corrected_false_applications", "corrected_false_application"),
            ("retained_applicable_cases", "retained_applicable_case"),
            ("new_false_rejections", "new_false_rejection"),
            ("new_false_applications", "new_false_application"),
        )
    }
    for name in ("false_application_rate", "recall"):
        a = metrics.methods["learned_initial"].micro.scope[name].value
        b = metrics.methods["learned_refined"].micro.scope[name].value
        totals[f"delta_{name}"] = b - a if a is not None and b is not None else None
    return {"schema_version": "paired-refinement.v1", "totals": totals, "rows": entries}
