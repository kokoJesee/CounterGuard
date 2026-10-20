"""Pure four-method fixture projections, never provenance or execution authority."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.evaluation_metrics import (
    METHOD_ORDER,
    EvaluationMetrics,
    Prediction,
    compute_metrics,
    paired_refinement,
)
from counterguard.models import Digest, FrozenModel, RunOutcome
from counterguard.project_config import Identifier
from counterguard.protocol import SampleLabels

Purpose = Literal["tool_owned_research_fixture_only"]
FiniteDelta = Annotated[float, Field(allow_inf_nan=False)] | None
Count = Annotated[int, Field(ge=0)]
Decision = Literal["applicable", "inapplicable", "unknown"]


class StudyMetricRow(FrozenModel):
    project_group: Identifier
    prediction: Prediction

    @model_validator(mode="after")
    def actual_outcome(self):
        row = self.prediction
        if row.scope_decision == "applicable":
            if row.run_outcome is None:
                raise ValueError("An executed prediction requires its actual outcome")
            expected = {
                RunOutcome.PASSED: "pass",
                RunOutcome.TEST_FAILED: "violation",
                RunOutcome.NO_TESTS_COLLECTED: "collection_error",
                RunOutcome.TIMEOUT: "timeout",
            }.get(row.run_outcome, "execution_error")
            if row.verdict not in {expected, "stale"}:
                raise ValueError("Prediction verdict contradicts its actual outcome")
        return self


class StudyMetricInput(FrozenModel):
    schema_version: Literal["study-metric-input.v1"] = "study-metric-input.v1"
    purpose: Purpose = "tool_owned_research_fixture_only"
    label_authority: Literal["trusted_manual_fixture_labels_not_semantic_proof"] = (
        "trusted_manual_fixture_labels_not_semantic_proof"
    )
    rows: tuple[StudyMetricRow, ...] = Field(min_length=4, max_length=512)


class StudyPairRow(FrozenModel):
    guard_id: str
    sample_id: str
    initial_decision: Decision
    refined_decision: Decision
    corrected_false_application: bool
    retained_applicable_case: bool
    new_false_rejection: bool
    new_false_application: bool


class StudyPairTotals(FrozenModel):
    corrected_false_applications: Count
    retained_applicable_cases: Count
    new_false_rejections: Count
    new_false_applications: Count
    delta_false_application_rate: FiniteDelta
    delta_recall: FiniteDelta


class StudyPairComparison(FrozenModel):
    schema_version: Literal["paired-refinement.v1"] = "paired-refinement.v1"
    totals: StudyPairTotals
    rows: tuple[StudyPairRow, ...]


class StudyMetricDeltas(FrozenModel):
    bug_recall: FiniteDelta
    false_alert_rate: FiniteDelta
    unknown_rate: FiniteDelta
    decision_coverage: FiniteDelta


class StudyMetricSummary(FrozenModel):
    schema_version: Literal["study-metric-summary.v1"] = "study-metric-summary.v1"
    purpose: Purpose = "tool_owned_research_fixture_only"
    assurance: Literal["pure_metrics_not_provenance_verification_or_scientific_support"] = (
        "pure_metrics_not_provenance_verification_or_scientific_support"
    )
    execution_allowed: Literal[False] = False
    formal_protocol_frozen: Literal[False] = False
    normalized_rows_digest: Digest
    row_count: Count
    evaluation_pair_count: Count
    metrics: EvaluationMetrics
    per_project: dict[Identifier, EvaluationMetrics]
    paired: StudyPairComparison
    deltas: StudyMetricDeltas
    implementation_digests: dict[str, Digest]
    artifact_digest: Digest


def summarize_study_metrics(inputs: StudyMetricInput) -> StudyMetricSummary:
    """Require a complete N x 4 fixture matrix and reuse the frozen arithmetic."""
    if type(inputs) is not StudyMetricInput or any(
        type(row) is not StudyMetricRow
        or type(row.prediction) is not Prediction
        or type(row.prediction.labels) is not SampleLabels
        for row in inputs.rows
    ):
        raise ValueError("Metrics accept only exact closed input types")
    # Revalidate model_copy/model_construct callers rather than trusting construction history.
    checked = StudyMetricInput.model_validate_json(canonical_json_bytes(inputs))
    rows = tuple(
        sorted(
            checked.rows,
            key=lambda r: (
                METHOD_ORDER.index(r.prediction.method),
                r.prediction.guard_id,
                r.prediction.sample_id,
            ),
        )
    )
    groups = {}
    for row in rows:
        sample = row.prediction.sample_id
        if sample in groups and groups[sample] != row.project_group:
            raise ValueError("The same sample cannot change project across methods or Guards")
        groups[sample] = row.project_group
    predictions = tuple(r.prediction for r in rows)
    metrics = compute_metrics(predictions)
    projects = {
        group: compute_metrics(tuple(r.prediction for r in rows if r.project_group == group))
        for group in sorted(set(groups.values()))
    }
    before = metrics.methods["learned_initial"].micro
    after = metrics.methods["learned_refined"].micro

    def delta(section, name):
        initial = getattr(before, section)[name].value
        refined = getattr(after, section)[name].value
        return refined - initial if initial is not None and refined is not None else None

    draft = StudyMetricSummary(
        normalized_rows_digest=digest_json_artifact({"rows": rows}),
        row_count=len(rows),
        evaluation_pair_count=len(rows) // len(METHOD_ORDER),
        metrics=metrics,
        per_project=projects,
        paired=StudyPairComparison.model_validate_json(
            canonical_json_bytes(paired_refinement(predictions, metrics))
        ),
        deltas=StudyMetricDeltas(
            bug_recall=delta("end_to_end", "bug_recall"),
            false_alert_rate=delta("end_to_end", "false_alert_rate"),
            unknown_rate=delta("scope", "unknown_rate"),
            decision_coverage=delta("scope", "decision_coverage"),
        ),
        implementation_digests=inspection_implementation_digests(),
        artifact_digest="sha256:" + "0" * 64,
    )
    return draft.model_copy(update={"artifact_digest": digest_json_artifact(draft)})


def verify_study_metrics(
    inputs: StudyMetricInput, result: StudyMetricSummary
) -> StudyMetricSummary:
    """Recompute the entire arithmetic projection; this does not verify source chains."""
    if type(result) is not StudyMetricSummary:
        raise ValueError("Metrics require an exact result type")
    checked = StudyMetricSummary.model_validate_json(canonical_json_bytes(result))
    actual = summarize_study_metrics(inputs)
    if checked != actual:
        raise ValueError(
            "Metrics do not follow the complete input matrix and current implementation"
        )
    return actual
