"""Independent six-row arithmetic, abstentions, failures and deterministic reports."""

import json
import random

import pytest
from pydantic import ValidationError

from counterguard.digests import canonical_json_bytes
from counterguard.evaluation_metrics import (
    METHOD_ORDER,
    EvaluationMetrics,
    Metric,
    Prediction,
    compute_metrics,
    paired_refinement,
)
from counterguard.models import RunOutcome
from counterguard.protocol import SampleLabels
from counterguard.report import render_evaluation


def predictions():
    result = []
    for method in METHOD_ORDER:
        for guard in ("discount", "query"):
            for kind in ("positive", "interface", "version"):
                applicable = kind == "positive"
                predicted = (
                    applicable
                    or method == "b1_always"
                    or (method == "b2_interface" and kind == "version")
                    or (method == "learned_initial" and kind == "interface")
                )
                bug = guard == "discount" and applicable
                violation = predicted and (bug or not applicable)
                outcome = RunOutcome.TEST_FAILED if violation else RunOutcome.PASSED
                result.append(
                    Prediction(
                        method=method,
                        guard_id=guard,
                        sample_id=f"{guard}-{kind}",
                        labels=SampleLabels(
                            guard_id=guard,
                            guard_applicable=applicable,
                            guard_violation=bug if applicable else None,
                            contract_compliant=not bug,
                            basis="Independent arithmetic fixture",
                        ),
                        scope_decision="applicable" if predicted else "inapplicable",
                        decision_trace=(),
                        verdict=("violation" if violation else "pass")
                        if predicted
                        else "skipped_inapplicable",
                        violated_case_ids=("regression",) if violation else (),
                        run_outcome=outcome if predicted else None,
                    )
                )
    return tuple(result)


def test_four_methods_and_independent_metric_denominators():
    metrics = compute_metrics(predictions())
    expected = ((2, 4, 0, 0), (2, 2, 2, 0), (2, 2, 2, 0), (2, 0, 4, 0))
    for method, counts, false_alerts, executions in zip(
        METHOD_ORDER, expected, (4, 2, 2, 0), (6, 4, 4, 2), strict=True
    ):
        data = metrics.methods[method]
        assert tuple(data.micro.confusion.model_dump().values()) == counts
        assert data.micro.end_to_end["bug_recall"].value == 1
        false_alert = data.micro.end_to_end["false_alert_rate"]
        assert (false_alert.numerator, false_alert.denominator) == (false_alerts, 5)
        assert data.micro.execution_count == executions
        query = data.per_guard["query"].end_to_end["bug_recall"]
        assert query.value is None and query.denominator == 0 and query.reason == "zero_denominator"
        macro = data.macro_end_to_end["bug_recall"]
        assert macro.included_guards == ("discount",) and macro.value == 1
    # Mean per-Guard FAR for alerts differs from pooled FAR because denominators differ.
    first = metrics.methods["b1_always"]
    assert first.micro.end_to_end["false_alert_rate"].value == 4 / 5
    assert first.macro_end_to_end["false_alert_rate"].value == (1 + 2 / 3) / 2


def test_unknown_is_explicit_negative_prediction_and_never_executed_pass():
    rows = list(predictions())
    index = next(
        i
        for i, r in enumerate(rows)
        if r.method == "learned_refined" and r.sample_id == "query-positive"
    )
    rows[index] = rows[index].model_copy(
        update={
            "scope_decision": "unknown",
            "verdict": "skipped_unknown",
            "run_outcome": None,
        }
    )
    data = compute_metrics(tuple(rows)).methods["learned_refined"].micro
    assert data.confusion.fn == 1 and data.unknown_count == 1
    assert data.scope["unknown_rate"].value == 1 / 6
    assert data.scope["decision_coverage"].value == 5 / 6
    assert data.end_to_end["applicable_clean_pass_rate"].value == 0
    assert rows[index].scope_decision == "unknown"


def test_infrastructure_failure_cannot_be_a_bug_detection():
    rows = list(predictions())
    index = next(
        i
        for i, r in enumerate(rows)
        if r.method == "learned_refined" and r.sample_id == "discount-positive"
    )
    rows[index] = rows[index].model_copy(
        update={
            "verdict": "timeout",
            "run_outcome": RunOutcome.TIMEOUT,
            "violated_case_ids": (),
        }
    )
    data = compute_metrics(tuple(rows)).methods["learned_refined"].micro
    assert data.end_to_end["bug_recall"].value == 0
    assert data.end_to_end["execution_validity"].value == 1 / 2
    assert data.end_to_end["infrastructure_failure_rate"].value == 1 / 2


def test_empty_class_denominators_and_undefined_balanced_accuracy_stay_null():
    rows = tuple(row for row in predictions() if row.sample_id.endswith("version"))
    metrics = compute_metrics(rows)
    data = metrics.methods["learned_refined"]
    assert data.micro.scope["recall"].value is None
    assert data.micro.scope["balanced_accuracy"].value is None
    assert data.micro.scope["balanced_accuracy"].reason == "undefined_component"
    assert data.micro.end_to_end["execution_validity"].value is None
    assert data.macro_end_to_end["bug_recall"].included_guards == ()


def test_paired_refinement_and_twenty_input_permutations_are_identical():
    rows = list(predictions())
    metrics = compute_metrics(tuple(rows))
    pair = paired_refinement(tuple(rows), metrics)
    assert pair["totals"] == {
        "corrected_false_applications": 2,
        "retained_applicable_cases": 2,
        "new_false_rejections": 0,
        "new_false_applications": 0,
        "delta_false_application_rate": -0.5,
        "delta_recall": 0.0,
    }
    for seed in range(20):
        random.Random(seed).shuffle(rows)
        actual = compute_metrics(tuple(rows))
        assert canonical_json_bytes(actual) == canonical_json_bytes(metrics)
        assert paired_refinement(tuple(rows), actual) == pair


@pytest.mark.parametrize("damage", ["duplicate", "missing", "label"])
def test_methods_must_have_identical_unique_members_and_labels(damage):
    rows = list(predictions())
    if damage == "duplicate":
        rows.append(rows[0])
    elif damage == "missing":
        rows.pop()
    else:
        rows[0] = rows[0].model_copy(
            update={"labels": rows[0].labels.model_copy(update={"basis": "changed"})}
        )
    with pytest.raises(ValueError):
        compute_metrics(tuple(rows))


def test_report_can_be_rebuilt_from_sorted_json_without_changing_column_order():
    rows = predictions()
    metrics = compute_metrics(rows)
    pair = paired_refinement(rows, metrics)
    loaded = EvaluationMetrics.model_validate_json(canonical_json_bytes(metrics))
    loaded_pair = json.loads(canonical_json_bytes(pair))
    assert render_evaluation(loaded, loaded_pair, True) == render_evaluation(metrics, pair, True)
    assert "null（zero_denominator；分母 0）" in render_evaluation(loaded, loaded_pair, True)


def test_metric_cannot_claim_a_value_for_zero_denominator():
    with pytest.raises(ValidationError, match="Undefined"):
        Metric(numerator=0.0, denominator=0.0, value=1.0, reason=None)
