"""Hand-counted fixture metrics, closed inputs and no execution authority."""

import json
import random
import subprocess

import pytest
from pydantic import ValidationError

from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.models import RunOutcome
from counterguard.protocol import SampleLabels
from counterguard.study_metrics import (
    StudyMetricInput,
    StudyMetricRow,
    summarize_study_metrics,
    verify_study_metrics,
)
from scripts.summarize_study_metrics import main
from tests.unit.test_evaluation import predictions


def matrix(rows=None):
    return StudyMetricInput(
        rows=tuple(
            StudyMetricRow(
                project_group="alpha" if p.guard_id == "discount" else "beta", prediction=p
            )
            for p in (predictions() if rows is None else rows)
        )
    )


def test_four_methods_project_slices_and_paired_changes_follow_hand_counts():
    result = summarize_study_metrics(matrix())
    assert result.row_count == 24 and result.evaluation_pair_count == 6
    assert set(result.per_project) == {"alpha", "beta"}
    initial = result.metrics.methods["learned_initial"].micro
    refined = result.metrics.methods["learned_refined"].micro
    # Six pairs: two applicable, four inapplicable; only discount-positive is a true bug.
    assert initial.confusion.model_dump() == {"tp": 2, "fp": 2, "tn": 2, "fn": 0}
    assert refined.confusion.model_dump() == {"tp": 2, "fp": 0, "tn": 4, "fn": 0}
    assert initial.end_to_end["false_alert_rate"].numerator == 2
    assert initial.end_to_end["false_alert_rate"].denominator == 5
    assert refined.end_to_end["false_alert_rate"].value == 0
    assert result.deltas.false_alert_rate == -2 / 5
    assert result.deltas.bug_recall == 0
    assert result.paired.totals.corrected_false_applications == 2
    assert result.paired.totals.new_false_applications == 0
    assert result.paired.totals.new_false_rejections == 0
    assert result.paired.totals.delta_false_application_rate == -1 / 2
    assert result.per_project["alpha"].methods["learned_initial"].micro.sample_count == 3
    assert (
        result.per_project["beta"].methods["learned_initial"].micro.end_to_end["bug_recall"].value
        is None
    )
    assert result.metrics.methods["learned_initial"].macro_end_to_end[
        "bug_recall"
    ].included_guards == ("discount",)
    assert result.execution_allowed is False and result.formal_protocol_frozen is False
    assert verify_study_metrics(matrix(), result) == result


def test_twenty_permutations_have_same_normalized_rows_and_full_summary():
    rows = list(matrix().rows)
    expected = summarize_study_metrics(StudyMetricInput(rows=tuple(rows)))
    for seed in range(20):
        random.Random(seed).shuffle(rows)
        actual = summarize_study_metrics(StudyMetricInput(rows=tuple(rows)))
        assert canonical_json_bytes(actual) == canonical_json_bytes(expected)
    assert "created_at" not in expected.model_dump()


def test_unknown_is_negative_but_not_an_explicitly_corrected_application():
    rows = list(predictions())
    index = next(
        n
        for n, r in enumerate(rows)
        if r.method == "learned_refined" and r.sample_id == "discount-interface"
    )
    rows[index] = rows[index].model_copy(
        update={
            "scope_decision": "unknown",
            "verdict": "skipped_unknown",
            "run_outcome": None,
            "violated_case_ids": (),
        }
    )
    result = summarize_study_metrics(matrix(rows))
    current = result.metrics.methods["learned_refined"].micro
    assert current.confusion.tn == 4 and current.unknown_count == 1
    assert current.verdict_counts["skipped_unknown"] == 1 and current.execution_count == 2
    assert result.paired.totals.corrected_false_applications == 1
    assert result.deltas.unknown_rate == 1 / 6
    assert result.deltas.decision_coverage == 5 / 6 - 1


@pytest.mark.parametrize(
    "outcome",
    [
        RunOutcome.INTERRUPTED,
        RunOutcome.PYTEST_INTERNAL_ERROR,
        RunOutcome.PYTEST_USAGE_ERROR,
        RunOutcome.NO_TESTS_COLLECTED,
        RunOutcome.TIMEOUT,
        RunOutcome.LAUNCH_ERROR,
        RunOutcome.PROCESS_ERROR,
    ],
)
def test_infrastructure_outcomes_never_become_bug_detection(outcome):
    rows = list(predictions())
    index = next(
        n
        for n, r in enumerate(rows)
        if r.method == "learned_refined" and r.sample_id == "discount-positive"
    )
    verdict = {
        RunOutcome.NO_TESTS_COLLECTED: "collection_error",
        RunOutcome.TIMEOUT: "timeout",
    }.get(outcome, "execution_error")
    rows[index] = rows[index].model_copy(
        update={
            "verdict": verdict,
            "run_outcome": outcome,
            "violated_case_ids": (),
        }
    )
    result = summarize_study_metrics(matrix(rows))
    current = result.metrics.methods["learned_refined"].micro
    assert current.verdict_counts[verdict] == 1
    assert current.end_to_end["bug_recall"].value == 0
    assert current.end_to_end["infrastructure_failure_rate"].numerator == 1
    assert result.deltas.bug_recall == -1


def test_zero_bug_denominator_is_null_in_both_metric_and_delta():
    rows = tuple(r for r in predictions() if r.guard_id == "query")
    result = summarize_study_metrics(matrix(rows))
    assert result.metrics.methods["learned_initial"].micro.end_to_end["bug_recall"].value is None
    assert result.deltas.bug_recall is None


@pytest.mark.parametrize("damage", ["missing_method", "duplicate", "different_label", "project"])
def test_four_method_membership_labels_and_project_assignment_are_fixed(damage):
    rows = list(matrix().rows)
    if damage == "missing_method":
        rows = [r for r in rows if r.prediction.method != "b2_interface"]
    elif damage == "duplicate":
        rows[-1] = rows[0]
    elif damage == "project":
        rows[-1] = rows[-1].model_copy(update={"project_group": "another-project"})
    else:
        label = rows[-1].prediction.labels.model_copy(update={"basis": "Different review"})
        rows[-1] = rows[-1].model_copy(
            update={"prediction": rows[-1].prediction.model_copy(update={"labels": label})}
        )
    with pytest.raises(ValueError):
        summarize_study_metrics(StudyMetricInput(rows=tuple(rows)))


@pytest.mark.parametrize("damage", ["count", "implementation", "nested_metric"])
def test_resigning_cannot_replace_complete_arithmetic_reconstruction(damage):
    inputs = matrix()
    result = summarize_study_metrics(inputs)
    raw = result.model_dump(mode="json")
    if damage == "count":
        raw["row_count"] = 25
    elif damage == "implementation":
        raw["implementation_digests"]["study_metrics.py"] = "sha256:" + "0" * 64
    else:
        raw["metrics"]["methods"]["learned_initial"]["micro"]["confusion"]["fp"] = 0
        raw["metrics"]["artifact_digest"] = digest_json_artifact(raw["metrics"])
    raw["artifact_digest"] = digest_json_artifact(raw)
    forged = type(result).model_validate_json(json.dumps(raw))
    with pytest.raises(ValueError, match="do not follow"):
        verify_study_metrics(inputs, forged)


def test_exact_types_and_roundtrip_validation_reject_hidden_fields_and_copied_invalid_rows():
    class LabelExtension(SampleLabels):
        hidden: str

    inputs = matrix()
    first = inputs.rows[0]
    label = LabelExtension(**first.prediction.labels.model_dump(), hidden="not learner input")
    poisoned = first.model_copy(
        update={"prediction": first.prediction.model_copy(update={"labels": label})}
    )
    with pytest.raises(ValueError, match="exact closed"):
        summarize_study_metrics(inputs.model_copy(update={"rows": (poisoned, *inputs.rows[1:])}))
    missing = first.model_copy(
        update={"prediction": first.prediction.model_copy(update={"run_outcome": None})}
    )
    with pytest.raises(ValueError):
        summarize_study_metrics(inputs.model_copy(update={"rows": (missing, *inputs.rows[1:])}))
    contradiction = first.prediction.model_copy(update={"verdict": "execution_error"})
    with pytest.raises(ValidationError):
        StudyMetricRow(project_group="alpha", prediction=contradiction)


@pytest.mark.parametrize(
    "patch",
    [
        {"purpose": "external_snapshot_observation_only"},
        {"holdout_ref": "do-not-read.json"},
        {"approved": True},
        {"execution_allowed": True},
    ],
)
def test_metrics_do_not_admit_external_observations_or_new_authority(patch):
    raw = matrix().model_dump(mode="json") | patch
    with pytest.raises(ValidationError):
        StudyMetricInput.model_validate_json(json.dumps(raw))


def test_pure_summary_never_starts_process_or_fit(monkeypatch):
    import counterguard.scope as scope
    from counterguard.runners.docker import DockerExecutor
    from counterguard.runners.local import LocalTrustedExecutor

    def forbidden(*args, **kwargs):
        pytest.fail("pure metrics reached execution or learning")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(DockerExecutor, "execute", forbidden)
    monkeypatch.setattr(LocalTrustedExecutor, "execute", forbidden)
    monkeypatch.setattr(scope, "learn_scope", forbidden)
    assert summarize_study_metrics(matrix()).row_count == 24


def test_cli_verifies_recomputed_result_and_preserves_existing_output(tmp_path, capsys):
    inputs, output = tmp_path / "input.json", tmp_path / "result.json"
    inputs.write_bytes(canonical_json_bytes(matrix()))
    args = ["summarize", "--input", str(inputs), "--output", str(output)]
    assert main(args) == 0
    original = output.read_bytes()
    assert main(["verify", "--input", str(inputs), "--result", str(output)]) == 0
    assert main(args) == 0 and output.read_bytes() == original  # Same bytes are idempotent.
    changed = matrix().model_dump(mode="json")
    for row in changed["rows"]:
        if row["project_group"] == "alpha":
            row["project_group"] = "another-project"
    inputs.write_text(json.dumps(changed))
    assert main(args) == 5 and output.read_bytes() == original
    capsys.readouterr()


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":"study-metric-input.v1","schema_version":"private-value"}',
        b'{"rows":NaN}',
        b'{"rows":Infinity}',
        b"not-json-private-value",
        b" " * (4 * 1024 * 1024 + 1),
    ],
    ids=["duplicate-key", "nan", "infinity", "invalid-json", "oversize"],
)
def test_cli_rejects_ambiguous_nonfinite_or_oversize_input_without_echo(tmp_path, capsys, raw):
    inputs, output = tmp_path / "input.json", tmp_path / "result.json"
    inputs.write_bytes(raw)
    assert main(["summarize", "--input", str(inputs), "--output", str(output)]) == 5
    assert not output.exists()
    assert "private-value" not in capsys.readouterr().out
