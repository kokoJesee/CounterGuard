"""An independent, non-executing recount of the published engineering benchmark."""

import json
import random
import shutil
from pathlib import Path

import pytest

from scripts.run_scope_study import (
    METHODS,
    InventoryError,
    canonical,
    decode,
    inventory,
    main,
    paired_counts,
    summarize,
)

ROOT = Path(__file__).resolve().parents[2]
PUBLISHED = "docs/results/scope-v1/evaluation"


def public_rows():
    return [
        decode(line) for line in (ROOT / PUBLISHED / "predictions.jsonl").read_bytes().splitlines()
    ]


def test_independent_recount_and_scope_boundary(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Inventory attempted to call the production evaluation/learner")

    monkeypatch.setattr("counterguard.evaluation.evaluate_methods", forbidden)
    monkeypatch.setattr("counterguard.scope.learn_scope", forbidden)
    value = inventory(ROOT)
    assert value["target_execution_count"] == 0
    assert value["execution_allowed"] is False
    assert value["scope_v2_status"] == "not_implemented_or_frozen"
    assert value["assurance"] == "published_fact_consistency_only_not_execution_provenance"
    assert value["train_counts"]["b1_always"] == {"tp": 4, "fp": 5, "tn": 0, "fn": 0}
    for method, alerts in zip(METHODS, (2, 1, 1, 0), strict=True):
        result = value["holdout_counts"][method]
        assert result["false_alert_rate"] == {"numerator": alerts, "denominator": 5}
        assert result["bug_recall"] == {"numerator": 1, "denominator": 1}
        assert (
            result["per_guard_bug_counts"]["grd_query_limit_zero_regression_v2"]["bug_count"] == 0
        )


def test_shuffle_twenty_times_keeps_inventory_and_arithmetic_stable():
    rows = public_rows()
    expected = {method: summarize([r for r in rows if r["method"] == method]) for method in METHODS}
    original = canonical(inventory(ROOT))
    for seed in range(20):
        random.Random(seed).shuffle(rows)
        for method in METHODS:
            assert summarize([r for r in rows if r["method"] == method]) == expected[method]
    assert canonical(inventory(ROOT)) == original


def test_unknown_is_neither_execution_nor_corrected_false_application():
    rows = [row for row in public_rows() if row["method"] == "learned_initial"]
    before = next(
        row
        for row in rows
        if not row["labels"]["guard_applicable"] and row["scope_decision"] == "applicable"
    )
    after = {
        **before,
        "scope_decision": "unknown",
        "verdict": "skipped_unknown",
        "run_outcome": None,
        "violated_case_ids": [],
    }
    observed = summarize([after])
    assert observed["unknown_count"] == 1
    assert observed["execution_count"] == 0
    assert paired_counts([before], [after])["corrected_false_applications"] == 0
    with pytest.raises(InventoryError, match="misleading verdict"):
        summarize([{**after, "verdict": "pass"}])


@pytest.fixture
def copied_publication(tmp_path):
    for name in (
        "benchmarks",
        "experiments",
        "docs/results/scope-v1/evaluation",
        "src/counterguard",
    ):
        shutil.copytree(ROOT / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path


@pytest.mark.parametrize("kind", ["duplicate", "missing", "wrong_label", "wrong_method"])
def test_changed_raw_predictions_rejected(copied_publication, kind):
    path = copied_publication / PUBLISHED / "predictions.jsonl"
    rows = public_rows()
    if kind == "duplicate":
        rows[-1] = rows[0]
    elif kind == "missing":
        rows.pop()
    elif kind == "wrong_label":
        rows[0]["labels"]["guard_applicable"] = False
    else:
        rows[0]["method"] = "other"
    path.write_bytes(b"\n".join(canonical(row) for row in rows) + b"\n")
    with pytest.raises(InventoryError, match="Publication pin"):
        inventory(copied_publication)


def test_resigned_manifest_is_not_a_new_frozen_publication(copied_publication):
    from scripts.run_scope_study import digest

    path = copied_publication / PUBLISHED / "manifest.json"
    value = decode(path.read_bytes())
    value["execution_count"] = 999
    value.pop("artifact_digest")
    value["artifact_digest"] = digest(canonical(value))
    path.write_bytes(canonical(value))
    with pytest.raises(InventoryError, match="Frozen identity"):
        inventory(copied_publication)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_ambiguous_json_is_rejected(raw):
    with pytest.raises(InventoryError):
        decode(raw)


def test_cli_failure_does_not_leak_root_path(tmp_path, capsys):
    assert main(["inventory", "--root", str(tmp_path)]) == 5
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "status": "rejected",
        "error_type": "InventoryError",
        "reason": "Missing/oversize input",
    }
    with pytest.raises(SystemExit) as error:
        main(["evaluate"])
    assert error.value.code == 2
