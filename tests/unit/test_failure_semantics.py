"""Execution errors remain errors through the public report and CLI boundaries."""

import subprocess

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.diagnostics import public_diagnostic
from counterguard.execution import run_pytest, verify_run_record
from counterguard.report import OutputFormat, command_report, render_report
from tests.unit.test_execution import _request


def test_cli_integrity_error_does_not_disclose_absolute_private_paths(tmp_path):
    private = tmp_path / "private-needle"
    private.mkdir()
    result = CliRunner().invoke(
        app,
        [
            "replay",
            "run",
            "--guard",
            "missing.json",
            "--scope",
            "scope.json",
            "--target",
            "package:target",
            "--cwd",
            str(private),
        ],
    )
    assert result.exit_code == 5, result.output
    assert "private-needle" not in result.stderr
    assert str(private) not in result.stderr
    assert "Guard" in result.stderr


def test_launch_error_summary_hides_credentials_but_raw_evidence_is_preserved(
    tmp_path, monkeypatch
):
    sensitive = "password=secret-needle C:/private/credentials.json"

    def missing(*a, **k):
        raise FileNotFoundError(sensitive)

    monkeypatch.setattr(subprocess, "run", missing)
    record = run_pytest(_request(tmp_path))
    assert record.outcome.value == "launch_error"
    assert record.pytest_exit_code is None
    assert "secret-needle" not in record.error_detail
    assert "C:/private" not in record.error_detail
    assert sensitive.encode() in (tmp_path / record.stderr_ref).read_bytes()
    verify_run_record(record, cwd=tmp_path, known_case_ids=("member-price", "non-member-price"))


@pytest.mark.parametrize(
    "code,body,outcome,verdict,execution,final",
    [
        (0, '<testcase name="test_case[member-price]"/>', "passed", "pass", "pass", "pass"),
        (
            1,
            '<testcase name="test_case[member-price]"><failure message="bad"/></testcase>',
            "test_failed",
            "violation",
            "fail",
            "violation",
        ),
        (2, None, "interrupted", "execution_error", "error", "inconclusive"),
        (3, None, "pytest_internal_error", "execution_error", "error", "inconclusive"),
        (4, None, "pytest_usage_error", "execution_error", "error", "inconclusive"),
        (5, None, "no_tests_collected", "collection_error", "error", "inconclusive"),
        (0, None, "process_error", "execution_error", "error", "inconclusive"),
        (
            1,
            '<testcase name="test_case[unknown-case]"><failure/></testcase>',
            "process_error",
            "execution_error",
            "error",
            "inconclusive",
        ),
        (
            0,
            '<testcase name="test_case[member-price]"><skipped/></testcase>',
            "process_error",
            "execution_error",
            "error",
            "inconclusive",
        ),
    ],
)
def test_process_results_remain_distinct_in_verified_records_and_formats(
    tmp_path,
    monkeypatch,
    code,
    body,
    outcome,
    verdict,
    execution,
    final,
):
    def completed(argv, **kwargs):
        if body is not None:
            (tmp_path / argv[argv.index("--junitxml") + 1]).write_text(
                "<testsuite>" + body + "</testsuite>", encoding="utf-8"
            )
        return subprocess.CompletedProcess(argv, code, b"raw stdout", b"raw stderr")

    monkeypatch.setattr(subprocess, "run", completed)
    record = run_pytest(_request(tmp_path, known_case_ids=("member-price",)))
    assert record.outcome.value == outcome and record.pytest_exit_code == code
    verify_run_record(record, cwd=tmp_path, known_case_ids=("member-price",))
    report = command_report(
        "replay",
        {
            "guard_id": "grd_process_probe",
            "scope_decision": "applicable",
            "verdict": verdict,
            "run": record.model_dump(mode="json"),
            "error_detail": record.error_detail,
            "violated_case_ids": ["member-price"] if verdict == "violation" else [],
            "decision_trace": [],
        },
    )
    row = report.replays[0]
    assert (row.execution_outcome, row.final_verdict) == (execution, final)
    for format in (OutputFormat.TEXT, OutputFormat.MARKDOWN):
        assert f"applicable | {execution} | {final}" in render_report(report, format)


@pytest.mark.parametrize(
    "message",
    [
        "token=secret-needle",
        'API_KEY = "secret-needle"',
        "Authorization: Bearer secret-needle",
        "password='secret-needle'",
        "Cannot read C:/secret-needle/private.json",
        "Cannot read /home/secret-needle/private.json",
        r"Cannot read \\server\secret-needle\private.json",
    ],
)
def test_bounded_public_diagnostics_remove_credentials_and_absolute_paths(message):
    assert "secret-needle" not in public_diagnostic(message)


def test_public_diagnostics_keep_actionable_relative_refs_and_json_format_hint():
    message = "Guard artifacts/guards/grd_test/guard.json: use JSON-compatible YAML"
    assert public_diagnostic(message) == message


@pytest.mark.parametrize(
    "syntax",
    [
        "scenario_id: scope_v1_offline_v1\n",
        '# YAML comment\n{"schema_version":"pipeline-scenario.v1"}',
    ],
)
def test_cli_rejects_general_yaml_with_actionable_json_hint_before_output(tmp_path, syntax):
    (tmp_path / "scenario.yaml").write_text(syntax, encoding="utf-8")
    result = CliRunner().invoke(
        app, ["demo", "--scenario", "scenario.yaml", "--workspace", "out", "--cwd", str(tmp_path)]
    )
    assert result.exit_code == 2, result.output
    assert "JSON-compatible YAML" in result.stderr
    assert not (tmp_path / "out").exists()


def test_api_keys_are_not_forwarded_to_pytest_or_copied_into_run_metadata(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COUNTERGUARD_SECRET"):
        monkeypatch.setenv(name, "environment-secret-needle")

    def completed(argv, **kwargs):
        assert not any(
            name in kwargs["env"]
            for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COUNTERGUARD_SECRET")
        )
        (tmp_path / argv[argv.index("--junitxml") + 1]).write_text(
            '<testsuite><testcase name="test_case[member-price]"/></testsuite>', encoding="utf-8"
        )
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", completed)
    result = run_pytest(_request(tmp_path, known_case_ids=("member-price",)))
    assert result.outcome.value == "passed"
    assert "environment-secret-needle" not in result.model_dump_json()
