"""Exercise the complete training replay through the CLI and actual subprocesses."""

import json

from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.replay import verify_replay


def test_refined_training_replay_runs_four_and_skips_five(replay_workspace, monkeypatch):
    import counterguard.execution as execution

    real_subprocess = execution.subprocess.run
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[0])
        return real_subprocess(*args, **kwargs)

    monkeypatch.setattr(execution.subprocess, "run", counted)
    result = CliRunner().invoke(
        app,
        [
            "benchmark",
            "replay",
            "--protocol",
            "experiments/scope_v1.json",
            "--phase",
            "refined",
            "--split",
            "train",
            "--fitted",
            "artifacts/fitted/refined",
            "--cwd",
            str(replay_workspace),
        ],
    )
    assert result.exit_code == 1, result.output
    report = json.loads(result.stdout)
    assert report["sample_count"] == 9 and report["execution_count"] == len(calls) == 4
    assert report["counts"] == {
        "pass": 2,
        "violation": 2,
        "skipped_inapplicable": 5,
        "skipped_unknown": 0,
        "collection_error": 0,
        "execution_error": 0,
        "timeout": 0,
        "stale": 0,
    }
    for row in report["results"]:
        data = row["result"]
        if data["scope_decision"] != "applicable":
            assert data["run"] is None and data["verdict"] == "skipped_inapplicable"
        path = replay_workspace / "artifacts/replays" / data["replay_id"] / "result.json"
        assert verify_replay(path, cwd=replay_workspace).artifact_digest == data["artifact_digest"]
    markdown = (
        replay_workspace / "artifacts/experiments/scope-v1/train-replays/refined/report.md"
    ).read_text(encoding="utf-8")
    skipped_lines = [line for line in markdown.splitlines() if "inapplicable" in line]
    assert len(skipped_lines) == 5
    assert all("不适用，未运行" in line and "通过" not in line for line in skipped_lines)


def test_d8_holdout_replay_is_rejected_before_any_process(monkeypatch):
    import counterguard.execution as execution

    def forbidden(*args, **kwargs):
        raise AssertionError("Holdout cannot run during D8")

    monkeypatch.setattr(execution.subprocess, "run", forbidden)
    result = CliRunner().invoke(
        app,
        [
            "benchmark",
            "replay",
            "--protocol",
            "missing.json",
            "--phase",
            "refined",
            "--split",
            "holdout",
        ],
    )
    assert result.exit_code == 2
