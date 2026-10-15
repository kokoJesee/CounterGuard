"""Fast presentation contracts: formatting cannot turn a skip/error into a pass."""

import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from evidenceguard.cli import app
from evidenceguard.demo import run_demo
from evidenceguard.digests import canonical_json_bytes
from evidenceguard.errors import ArtifactIntegrityError, InsufficientScopeEvidence
from evidenceguard.models import RunOutcome
from evidenceguard.report import (
    CommandReport,
    OutputFormat,
    ReplayPresentation,
    command_report,
    present_replay,
    render_report,
)

RUNNER = CliRunner()


def replay(scope="applicable", outcome="passed", verdict="pass"):
    return {
        "guard_id": "grd_test",
        "scope_decision": scope,
        "run": {"outcome": outcome} if outcome else None,
        "verdict": verdict,
        "error_detail": "missing contract" if scope == "unknown" else None,
        "violated_case_ids": ["case1"] if verdict == "violation" else [],
        "decision_trace": [],
    }


@pytest.mark.parametrize(
    "scope,outcome,verdict,execution,final",
    [
        ("inapplicable", None, "skipped_inapplicable", "not_run", "skipped"),
        ("unknown", None, "skipped_unknown", "not_run", "skipped"),
        ("applicable", "passed", "pass", "pass", "pass"),
        ("applicable", "test_failed", "violation", "fail", "violation"),
        ("applicable", "timeout", "timeout", "timeout", "inconclusive"),
        ("applicable", None, "stale", "not_run", "inconclusive"),
        ("applicable", "passed", "stale", "pass", "inconclusive"),
        *[
            ("applicable", value.value, "execution_error", "error", "inconclusive")
            for value in RunOutcome
            if value not in {RunOutcome.PASSED, RunOutcome.TEST_FAILED, RunOutcome.TIMEOUT}
        ],
    ],
)
def test_replay_states_in_all_formats(scope, outcome, verdict, execution, final):
    report = command_report("replay", replay(scope, outcome, verdict))
    row = report.replays[0]
    assert (row.scope_decision, row.execution_outcome, row.final_verdict) == (
        scope,
        execution,
        final,
    )
    payload = json.loads(render_report(report, OutputFormat.JSON))
    assert payload["replays"][0]["final_verdict"] == final
    for format in (OutputFormat.TEXT, OutputFormat.MARKDOWN):
        assert f"{scope} | {execution} | {final}" in render_report(report, format)
        if scope == "unknown":
            assert "missing contract" in render_report(report, format)


@pytest.mark.parametrize(
    "scope,outcome,verdict",
    [
        ("unknown", None, "pass"),
        ("inapplicable", "passed", "skipped_inapplicable"),
        ("unknown", None, "skipped_inapplicable"),
        ("applicable", None, "pass"),
        ("applicable", "pytest_internal_error", "violation"),
        ("applicable", "passed", "execution_error"),
        ("bad", None, "stale"),
    ],
)
def test_inconsistent_raw_states_are_rejected(scope, outcome, verdict):
    with pytest.raises(ValueError):
        present_replay(replay(scope, outcome, verdict))


def test_normalized_json_cannot_be_resigned_as_pass():
    row = present_replay(replay("unknown", None, "skipped_unknown"))
    payload = row.model_dump(mode="json")
    payload["final_verdict"] = "pass"
    with pytest.raises(ValueError, match="contradicts"):
        ReplayPresentation.model_validate_json(json.dumps(payload))


def test_renderers_are_deterministic_and_escape_markdown_without_changing_json():
    payload = {"detail": "```\n<script>x</script>|danger", "answer": 42}
    report = command_report("capture", payload)
    for format in OutputFormat:
        assert render_report(report, format) == render_report(report, format)
    assert json.loads(render_report(report, OutputFormat.JSON))["payload"] == payload
    markdown = render_report(report, OutputFormat.MARKDOWN)
    assert markdown.count("```") == 2
    assert "<script>" not in markdown
    assert not report.replays  # No fictitious replay decision for capture/compile/learn.


def test_demo_rendering_survives_canonical_json_key_reordering():
    rule = {"clauses": [{"field": "contract_version", "op": "eq", "value": "v1"}]}
    report = command_report(
        "demo",
        {
            "scenario_id": "scenario",
            "run_id": "run",
            "accepted": True,
            "replay_execution_count": 0,
            "verdict_counts": {},
            "groups": [
                {
                    "guard_id": "grd_test",
                    "failed_case_ids": ["c1"],
                    "rules": {"initial": rule, "refined": rule},
                    "provenance": {"guard": {"ref": "g.json"}, "evidence": {"ref": "e.json"}},
                }
            ],
        },
    )
    loaded = CommandReport.model_validate_json(canonical_json_bytes(report))
    for format in OutputFormat:
        assert render_report(report, format) == render_report(loaded, format)


@pytest.mark.parametrize(
    "command",
    [
        ["capture"],
        ["compile"],
        ["learn"],
        ["scope", "learn"],
        ["replay", "run"],
        ["evaluate"],
        ["experiment", "evaluate"],
        ["demo"],
    ],
)
def test_public_command_help_exposes_three_formats(command):
    result = RUNNER.invoke(app, [*command, "--help"], env={"COLUMNS": "160"})
    assert result.exit_code == 0, result.output
    assert all(word in result.stdout for word in ("--format", "text", "json", "markdown"))


@pytest.mark.parametrize("format", list(OutputFormat))
@pytest.mark.parametrize(
    "command,patch,payload,args",
    [
        (
            "capture",
            "capture_evidence",
            {"reproduced": True},
            [
                "--evidence-id",
                "evd_test",
                "--contract",
                "c.json",
                "--test",
                "t.py",
                "--buggy-target",
                "m:bug",
                "--fixed-target",
                "m:fix",
            ],
        ),
        (
            "compile",
            "compile_guard",
            {"guard_id": "grd_test"},
            ["--guard-id", "grd_test", "--evidence", "e.json"],
        ),
        (
            "learn",
            "fit_scopes",
            {"phase": "refined"},
            ["--protocol", "p.json", "--phase", "refined", "--output", "out"],
        ),
        (
            "evaluate",
            "evaluate_methods",
            {"accepted": False},
            ["--protocol", "p.json", "--fitted", "fit", "--output", "out"],
        ),
    ],
)
def test_commands_share_formatting_and_preserve_exit_codes(
    monkeypatch, format, command, patch, payload, args
):
    record = SimpleNamespace(model_dump=lambda **kwargs: payload, accepted=False)
    monkeypatch.setattr(f"evidenceguard.cli.{patch}", lambda *a, **k: record)
    monkeypatch.setattr("evidenceguard.cli.evidence_exit_code", lambda value: 0)
    result = RUNNER.invoke(app, [command, *args, "--format", format.value])
    assert result.exit_code == (1 if command == "evaluate" else 0), result.output
    if format is OutputFormat.JSON:
        report = CommandReport.model_validate_json(result.stdout)
        assert report.operation == command and report.payload == payload
    else:
        assert f"EvidenceGuard {command}" in result.stdout


@pytest.mark.parametrize(
    "scope,verdict,code",
    [
        ("inapplicable", "skipped_inapplicable", 0),
        ("unknown", "skipped_unknown", 4),
    ],
)
@pytest.mark.parametrize("format", [None, *OutputFormat])
def test_replay_skip_cli_preserves_raw_state_and_exit(monkeypatch, scope, verdict, code, format):
    payload = replay(scope, None, verdict)
    record = SimpleNamespace(model_dump=lambda **kwargs: payload, verdict=verdict)
    monkeypatch.setattr("evidenceguard.cli.replay_guard", lambda *a, **k: record)
    args = ["replay", "run", "--guard", "g.json", "--scope", "s.json", "--target", "m:t"]
    if format is not None:
        args += ["--format", format.value]
    result = RUNNER.invoke(app, args)
    assert result.exit_code == code, result.output
    if format is None:
        assert json.loads(result.stdout) == payload
    elif format is OutputFormat.JSON:
        assert json.loads(result.stdout)["replays"][0]["final_verdict"] == "skipped"
    else:
        assert f"{scope} | not_run | skipped" in result.stdout


def test_unknown_output_format_fails_before_execution(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("Invalid format must not launch Demo")

    monkeypatch.setattr("evidenceguard.cli.run_demo", forbidden)
    assert RUNNER.invoke(app, ["demo", "--format", "html"]).exit_code == 2


def test_learning_refusal_retains_reason_and_code(monkeypatch):
    def refuse(*a, **k):
        raise InsufficientScopeEvidence("test_reason", "not enough evidence")

    monkeypatch.setattr("evidenceguard.cli.fit_scopes", refuse)
    result = RUNNER.invoke(
        app,
        [
            "learn",
            "--protocol",
            "p.json",
            "--phase",
            "initial",
            "--output",
            "out",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 4, result.output
    assert json.loads(result.stdout)["payload"]["reason_code"] == "test_reason"


def test_demo_integrity_failure_retains_exit_five(monkeypatch):
    def stale(*a, **k):
        raise ArtifactIntegrityError("stale Demo")

    monkeypatch.setattr("evidenceguard.cli.run_demo", stale)
    result = RUNNER.invoke(app, ["demo"])
    assert result.exit_code == 5 and "stale Demo" in result.stderr


def test_demo_preflights_paths_before_pipeline_or_directory(tmp_path, monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("Demo path preflight must happen before Pipeline execution")

    monkeypatch.setattr("evidenceguard.demo.run_pipeline", forbidden)
    output = tmp_path / ("x" * 80) / ("y" * 80)
    with pytest.raises(ValueError, match="Artifact path"):
        run_demo("not-read.yaml", cwd=tmp_path, workspace=output)
    assert not output.exists()


def test_demo_refuses_partial_directory_without_pipeline_or_rewrites(tmp_path, monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("Partial Demo must not restart the Pipeline")

    monkeypatch.setattr("evidenceguard.demo.run_pipeline", forbidden)
    output = tmp_path / "partial"
    output.mkdir()
    (output / "report.md").write_bytes(b"partial history")
    with pytest.raises(ArtifactIntegrityError, match="new version"):
        run_demo("not-read.yaml", cwd=tmp_path, workspace=output)
    assert (output / "report.md").read_bytes() == b"partial history"
    assert not (output / "report.json").exists()
