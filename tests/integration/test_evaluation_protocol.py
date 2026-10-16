"""Run all four methods and audit evidence, without altering the frozen pipeline."""

import json
import shutil

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.digests import (
    canonical_json_bytes,
    digest_bytes,
    digest_file,
    digest_json_artifact,
)
from counterguard.errors import ArtifactIntegrityError
from counterguard.evaluation import evaluate_methods, verify_evaluation


@pytest.fixture(scope="module")
def evaluation_workspace(replay_workspace, tmp_path_factory):
    # Evaluation has deeper runtime/report trees. Keep them out of the shared fixture seed
    # that later mutation tests copy, and do not copy disposable pytest caches.
    workspace = tmp_path_factory.mktemp("ev")
    shutil.copytree(
        replay_workspace,
        workspace,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    return workspace


@pytest.fixture(scope="module")
def evaluated(evaluation_workspace):
    report = evaluate_methods(
        "experiments/scope_v1.json",
        fitted="artifacts/fitted",
        output="evaluations/first",
        cwd=evaluation_workspace,
    )
    assert (
        report.accepted
        and report.execution_count == 16
        and report.source_check_execution_count == 4
    )
    return evaluation_workspace, report


def test_all_methods_have_real_replays_and_source_probes(evaluated, monkeypatch):
    workspace, report = evaluated

    def forbidden(*args, **kwargs):
        pytest.fail("Audit and idempotent evaluation must not execute or refit")

    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("counterguard.scope.fit_scopes", forbidden)
    actual = verify_evaluation("evaluations/first", cwd=workspace)
    assert actual == report
    repeated = evaluate_methods(
        "experiments/scope_v1.json",
        fitted="artifacts/fitted",
        output="evaluations/first",
        cwd=workspace,
    )
    assert repeated == report
    rows = [
        json.loads(line)
        for line in (workspace / "evaluations/first/replays.jsonl").read_bytes().splitlines()
    ]
    assert len(rows) == 24
    assert len({row["result"]["replay_id"] for row in rows}) == 24
    assert sum(row["result"]["run"] is not None for row in rows) == 16
    assert all(
        row["result"]["run"] is None
        for row in rows
        if row["result"]["scope_decision"] != "applicable"
    )


def test_fresh_repeat_has_identical_predictions_metrics_and_distinct_real_times(
    evaluated, monkeypatch
):
    workspace, first = evaluated
    import counterguard.execution as execution

    original = execution.subprocess.run
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(execution.subprocess, "run", counted)
    second = evaluate_methods(
        "experiments/scope_v1.json",
        fitted="artifacts/fitted",
        output="evaluations/second",
        cwd=workspace,
    )
    assert len(calls) == 20
    assert second.evaluation_id != first.evaluation_id and second.started_at > first.completed_at
    for name in ("predictions.jsonl", "metrics.json", "paired-refinement.json", "report.md"):
        assert (workspace / "evaluations/first" / name).read_bytes() == (
            workspace / "evaluations/second" / name
        ).read_bytes()
    assert (workspace / "evaluations/first/replays.jsonl").read_bytes() != (
        workspace / "evaluations/second/replays.jsonl"
    ).read_bytes()


@pytest.mark.parametrize("name", ["metrics.json", "predictions.jsonl", "source-checks.jsonl"])
def test_rehashed_fake_facts_are_rejected(evaluated, tmp_path, name):
    workspace, _ = evaluated
    destination = (
        workspace
        / "evaluations"
        / {
            "metrics.json": "t0",
            "predictions.jsonl": "t1",
            "source-checks.jsonl": "t2",
        }[name]
    )
    shutil.copytree(
        workspace / "evaluations/first",
        destination,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    path = destination / name
    if name == "metrics.json":
        data = json.loads(path.read_bytes())
        data["methods"]["learned_refined"]["micro"]["scope"]["recall"]["value"] = 0.5
        data["artifact_digest"] = digest_json_artifact(data)
        content = canonical_json_bytes(data)
    else:
        lines = path.read_bytes().splitlines()
        data = json.loads(lines[0])
        data["sample_id"] = "fabricated-sample"
        lines[0] = canonical_json_bytes(data)
        content = b"\n".join(lines) + b"\n"
    path.write_bytes(content)
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"][name] = digest_bytes(content)
    manifest["artifact_digest"] = digest_json_artifact(manifest)
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ArtifactIntegrityError):
        verify_evaluation(destination, cwd=workspace)


def test_wrong_phase_and_nonempty_directory_refused_before_any_execution(
    evaluation_workspace, monkeypatch
):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid evaluation cannot execute")

    monkeypatch.setattr("subprocess.run", forbidden)
    with pytest.raises(ValueError, match="holdout"):
        evaluate_methods(
            "missing.json",
            fitted="missing",
            output="unused",
            cwd=evaluation_workspace,
            split="train",
        )
    with pytest.raises(ArtifactIntegrityError, match="not empty"):
        evaluate_methods(
            "missing.json", fitted="missing", output="artifacts/fitted", cwd=evaluation_workspace
        )


def test_cli_verify_run_and_protocol_remain_distinct(evaluated):
    workspace, _ = evaluated
    for arguments in (
        ["--run", "evaluations/first"],
        ["--protocol", "experiments/scope_v1.json"],
    ):
        result = CliRunner().invoke(
            app, ["experiment", "verify", *arguments, "--cwd", str(workspace)]
        )
        assert result.exit_code == 0, result.output
    invalid = CliRunner().invoke(
        app, ["experiment", "verify", "--run", "missing", "--protocol", "missing"]
    )
    assert invalid.exit_code == 2


def test_all_prior_workspace_artifacts_survive_new_evaluation(evaluated):
    workspace, _ = evaluated
    before = {path: digest_file(path) for path in (workspace / "artifacts/fitted").rglob("*.json")}
    verify_evaluation("evaluations/first", cwd=workspace)
    assert before == {path: digest_file(path) for path in before}


def test_mid_evaluation_failure_is_retained_and_cannot_be_overwritten(
    evaluation_workspace, monkeypatch
):
    def fail(*args, **kwargs):
        raise ArtifactIntegrityError("Injected stale binding")

    monkeypatch.setattr("counterguard.evaluation.replay_guard", fail)
    output = evaluation_workspace / "evaluations/failed"
    with pytest.raises(ArtifactIntegrityError, match="Injected"):
        evaluate_methods(
            "experiments/scope_v1.json",
            fitted="artifacts/fitted",
            output=output,
            cwd=evaluation_workspace,
        )
    failure = (output / "failure.json").read_bytes()
    assert json.loads(failure)["completed_replays"] == []
    assert not (output / "manifest.json").exists()
    with pytest.raises(ArtifactIntegrityError, match="not empty"):
        evaluate_methods(
            "experiments/scope_v1.json",
            fitted="artifacts/fitted",
            output=output,
            cwd=evaluation_workspace,
        )
    assert (output / "failure.json").read_bytes() == failure
