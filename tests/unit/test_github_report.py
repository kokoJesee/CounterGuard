"""The CI projection preserves policy and exposes no repository-controlled text."""

import json
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.github_report import export_github_report, project_github_report
from counterguard.lifecycle import GuardState
from counterguard.verify import verify_repository
from tests.unit.test_verify import captured, registered_inputs, setup_verify  # noqa: F401


@pytest.mark.parametrize(
    "state,outcome,code",
    [
        ("shadow", "test_failed", 0),
        ("active", "test_failed", 1),
        ("active", "passed", 0),
        ("active", "timeout", 3),
    ],
)
def test_counts_exit_policy_and_public_files_share_one_json(  # noqa: F811
    setup_verify, state, outcome, code  # noqa: F811
):
    request, registry, guard, _, _, result, _ = setup_verify
    registry.transition(guard.guard_id, to=GuardState.SHADOW, reason="fixture review")
    if state == "active":
        registry.transition(guard.guard_id, to=GuardState.ACTIVE, reason="fixture acceptance")
    result[0] = outcome
    report = verify_repository(request)
    output = request.cwd / "ci"
    assert export_github_report(request.cwd / "result/report.json", output) == code
    projection = json.loads((output / "summary.json").read_bytes())
    markdown = (output / "summary.md").read_text()
    assert projection["counts"] == report.counts
    assert projection["source_report_digest"] == report.artifact_digest
    assert projection["source_decision_digest"] == report.decision_digest
    assert projection["exit_code"] == code
    assert projection["artifact_digest"] == digest_json_artifact(projection)
    for key, value in report.counts.items():
        assert f"| {key} | {value} |" in markdown
    assert "stdout" not in projection and "run" not in projection["rows"][0]
    assert guard.guard_id not in markdown and str(request.cwd) not in markdown


def test_unknown_and_arbitrary_secret_text_are_not_converted_to_green(setup_verify):  # noqa: F811
    request, registry, guard, _, _, _, inspection = setup_verify
    registry.transition(guard.guard_id, to=GuardState.SHADOW, reason="review")
    report = verify_repository(replace(request, base="missing"))
    # Produce a coherent unjudged row with adversarial identifying/reason text.
    row = report.rows[0].model_copy(
        update={
            "guard_id": "SECRET_TOKEN_<script>\n::error::bad|",
            "target_id": "private/path",
            "verdict": "unknown",
            "scope_decision": "unknown",
            "run": None,
            "execution_outcome": "not_run",
            "reason_codes": ("secret_token_123",),
        }
    )
    from counterguard.verify import ZERO, _decision_digest, summarize

    code, counts = summarize([row], [])
    report = report.model_copy(
        update={
            "rows": (row,),
            "issues": (),
            "exit_code": code,
            "counts": counts,
            "decision_digest": _decision_digest([row], [], counts, code),
            "artifact_digest": ZERO,
        }
    )
    value = report.model_dump(mode="json")
    value["artifact_digest"] = digest_json_artifact(value)
    projection = project_github_report(value)
    assert projection["exit_code"] == 4 and projection["counts"]["pass"] == 0
    encoded = canonical_json_bytes(projection).decode()
    assert all(
        secret not in encoded for secret in ("SECRET_TOKEN", "private/path", "secret_token_123")
    )
    assert projection["rows"][0]["reason_codes"] == ["other_reason_redacted"]


@pytest.mark.parametrize("damage", ["missing", "truncated", "wrong_digest", "rehashed_counts"])
def test_invalid_or_absent_report_writes_failure_and_exits_five(setup_verify, damage):  # noqa: F811
    request, _, _, _, _, _, _ = setup_verify
    report = verify_repository(request)
    path = request.cwd / "broken.json"
    if damage == "truncated":
        path.write_bytes(b'{"schema_version":')
    elif damage != "missing":
        value = report.model_dump(mode="json")
        value["counts"]["pass"] = 999
        if damage == "rehashed_counts":
            value["artifact_digest"] = digest_json_artifact(value)
        path.write_bytes(canonical_json_bytes(value))
    result = CliRunner().invoke(
        app, ["ci-report", "--report", str(path), "--output", str(request.cwd / "safe")]
    )
    assert result.exit_code == 5
    assert json.loads((request.cwd / "safe/summary.json").read_bytes())["exit_code"] == 5
    assert "Exit code: 5" in (request.cwd / "safe/summary.md").read_text()


def test_cli_preserves_preexisting_output_without_overwrite(tmp_path):
    output = tmp_path / "safe"
    output.mkdir()
    (output / "summary.md").write_text("history")
    result = CliRunner().invoke(
        app, ["ci-report", "--report", "missing.json", "--output", str(output)]
    )
    assert result.exit_code == 5 and (output / "summary.md").read_text() == "history"


def test_non_regular_or_oversize_input_is_not_read(tmp_path, monkeypatch):
    from counterguard import github_report

    path = tmp_path / "oversize.json"
    path.write_bytes(b"{}")
    monkeypatch.setattr(github_report, "REPORT_LIMIT", 1)
    assert export_github_report(path, tmp_path / "large") == 5
    assert export_github_report(tmp_path, tmp_path / "directory") == 5
