"""Exercise the public verify entry without starting Git or Docker processes."""

import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.change_analysis import InspectionReport, TargetImpact
from counterguard.cli import app
from counterguard.digests import digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.execution import _execute_with_adapter
from counterguard.lifecycle import GuardState
from counterguard.models import RunOutcome
from counterguard.registry import Registry
from counterguard.repository import FilePin
from counterguard.runners.base import RawExecution
from counterguard.runners.docker import DockerExecutor
from counterguard.verify import VerifyReportV2 as VerifyReport
from counterguard.verify import VerifyRequest, verify_repository
from tests.unit.test_integrity import captured  # noqa: F401
from tests.unit.test_registry import GUARD_ID, registered_inputs  # noqa: F401

verify_module = importlib.import_module("counterguard.verify")
IMAGE = "sha256:" + "1" * 64


@pytest.fixture
def setup_verify(registered_inputs, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    monkeypatch.setattr(
        verify_module,
        "resolve_runner",
        lambda **kwargs: SimpleNamespace(
            runner_id="test-runner",
            profile="root-pytest8.v1",
            image_digest=IMAGE,
            artifact_digest="sha256:" + "2" * 64,
        ),
    )
    workspace, path, guard = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    evidence = registry.resolve_for_execution(GUARD_ID).evidence
    files = {
        "target.py": (workspace / evidence.fixed_target.source_ref).read_bytes(),
        "contract.json": (workspace / evidence.contract_ref).read_bytes(),
        "pyproject.toml": b'[project]\nname="fixture"\nversion="0.1"\ndependencies=[]\n',
    }
    config = workspace / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "project-config.v1",
                "project_id": "verify-fixture",
                "targets": [
                    {
                        "target_id": "price",
                        "guard_id": GUARD_ID,
                        "source_ref": "target.py",
                        "module": "target",
                        "symbol": evidence.fixed_target.symbol,
                        "contract_ref": "contract.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    pins = tuple(
        FilePin(revision="head", path=ref, object_id="c" * 40, content_digest=digest_bytes(body))
        for ref, body in sorted(files.items())
    )
    report = InspectionReport(
        project_id="verify-fixture",
        status="ready",
        reason_codes=(),
        requested_base="BASE",
        requested_head="HEAD",
        base_commit="a" * 40,
        head_commit="b" * 40,
        shallow=False,
        git_version="git fixture",
        config_digest=digest_bytes(config.read_bytes()),
        implementation_digests=verify_module.inspection_implementation_digests(),
        changes=(),
        files=pins,
        unmapped_paths=(),
        targets=(
            TargetImpact(
                target_id="price",
                guard_id=GUARD_ID,
                source_ref="target.py",
                symbol=evidence.fixed_target.symbol,
                impact="affected",
                changed_inputs=("target.py",),
            ),
        ),
        artifact_digest="sha256:" + "0" * 64,
    )
    report = report.model_copy(update={"artifact_digest": digest_json_artifact(report)})
    monkeypatch.setattr(verify_module, "inspect_repository", lambda *args: report)
    monkeypatch.setattr(
        verify_module, "read_committed_files", lambda *args: ("b" * 40, files, pins)
    )
    calls = []
    outcome = ["passed"]

    def execute(self, request):
        calls.append(request)

        class Adapter:
            def execute_process(self, request, prepared):
                xml = (
                    "<testsuite>"
                    + "".join(
                        f'<testcase name="test_guard_case[{case}]" time="0">'
                        + ('<failure message="assertion" />' if outcome[0] == "test_failed" else "")
                        + "</testcase>"
                        for case in request.known_case_ids
                    )
                    + "</testsuite>"
                )
                return RawExecution(
                    argv=("docker", "run"),
                    stdout=b"",
                    stderr=b"",
                    junit=xml.encode(),
                    pytest_exit_code=None
                    if outcome[0] == "timeout"
                    else int(outcome[0] == "test_failed"),
                    junit_produced=True,
                    python_version="3.13.16",
                    pytest_version="8.4.2",
                    terminal_outcome=RunOutcome.TIMEOUT if outcome[0] == "timeout" else None,
                    error_detail="timeout" if outcome[0] == "timeout" else None,
                )

        return _execute_with_adapter(request, Adapter())

    monkeypatch.setattr(DockerExecutor, "execute", execute)
    request = VerifyRequest(
        workspace / "repo", "BASE", "HEAD", config, registry.root, Path("result"), IMAGE, workspace
    )
    return request, registry, guard, files, calls, outcome, report


@pytest.mark.parametrize(
    "state,outcome,code",
    [
        ("shadow", "test_failed", 0),
        ("active", "test_failed", 1),
        ("active", "passed", 0),
        ("active", "timeout", 3),
    ],
)
def test_state_and_execution_policy_writes_report_before_nonzero(
    setup_verify, state, outcome, code
):
    request, registry, _, _, calls, result, _ = setup_verify
    registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="review")
    if state == "active":
        registry.transition(GUARD_ID, to=GuardState.ACTIVE, reason="review")
    result[0] = outcome
    report = verify_repository(request)
    assert report.exit_code == code
    assert len(calls) == 1
    assert report.rows[0].run is not None
    assert (request.cwd / "result/report.md").is_file()
    saved = VerifyReport.model_validate_json((request.cwd / "result/report.json").read_bytes())
    assert saved == report
    assert report.counts["shadow_violations"] == int(state == "shadow")


@pytest.mark.parametrize("state", ["candidate", "retired", "disabled"])
def test_unscheduled_states_never_start_docker(setup_verify, state):
    request, registry, _, _, calls, _, _ = setup_verify
    if state == "retired":
        registry.transition(GUARD_ID, to=GuardState.RETIRED, reason="review")
    elif state == "disabled":
        registry.disable(GUARD_ID, reason="review")
    report = verify_repository(request)
    assert report.exit_code == 0
    assert report.counts["skipped"] == 1
    assert report.rows[0].run is None
    assert not calls


def test_unreviewed_source_stays_unknown_without_execution(setup_verify):
    request, registry, _, files, calls, _, _ = setup_verify
    registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="review")
    files["target.py"] += b"\n# unreviewed revision\n"
    report = verify_repository(request)
    assert report.exit_code == 4
    assert report.rows[0].scope_decision == "unknown"
    assert report.rows[0].run is None
    assert not calls


def test_source_damage_is_not_hidden_by_candidate_skip(setup_verify):
    request, registry, _, _, calls, _, _ = setup_verify
    entry = registry.resolve_for_execution(GUARD_ID).entry
    (Path(entry.source_workspace) / entry.guard_ref).write_bytes(b"damaged")
    report = verify_repository(request)
    assert report.exit_code == 5
    assert report.rows[0].verdict == "integrity_error"
    assert not calls


def test_repeated_checks_have_same_decision_digest_and_never_overwrite(setup_verify):
    request, registry, _, _, _, _, _ = setup_verify
    registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="review")
    first = verify_repository(request)
    second = verify_repository(replace(request, output=Path("result2")))
    assert first.decision_digest == second.decision_digest
    assert first.rows[0].run.run_id != second.rows[0].run.run_id
    assert first.artifact_digest != second.artifact_digest
    with pytest.raises(ArtifactIntegrityError, match="already exists"):
        verify_repository(request)


def test_cli_uses_saved_exit_code_and_rejects_local_fallback(setup_verify, monkeypatch):
    request, registry, _, _, calls, result, _ = setup_verify
    registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="review")
    registry.transition(GUARD_ID, to=GuardState.ACTIVE, reason="review")
    result[0] = "test_failed"
    monkeypatch.chdir(request.cwd)
    args = [
        "verify",
        "--repo",
        str(request.repo),
        "--base",
        request.base,
        "--head",
        request.head,
        "--config",
        str(request.config),
        "--registry",
        str(request.registry),
        "--output",
        "cli-result",
        "--image",
        IMAGE,
        "--format",
        "json",
    ]
    runner = CliRunner()
    value = runner.invoke(app, args)
    assert value.exit_code == 1, value.output
    assert json.loads(value.output)["exit_code"] == 1
    assert (request.cwd / "cli-result/report.md").is_file()
    before = len(calls)
    rejected = runner.invoke(app, [*args, "--runner", "local"])
    assert rejected.exit_code == 2
    assert len(calls) == before


def test_execution_failure_is_three_and_report_is_preserved(setup_verify, monkeypatch):
    request, registry, _, _, calls, _, _ = setup_verify
    registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="review")

    def unavailable(*args):
        raise OSError("Docker unavailable")

    monkeypatch.setattr(DockerExecutor, "execute", unavailable)
    report = verify_repository(request)
    assert report.exit_code == 3
    assert report.rows[0].verdict == "execution_error"
    assert report.rows[0].run is None
    assert not calls
    assert (request.cwd / "result/report.md").is_file()


def test_post_run_disable_keeps_the_run_and_reports_integrity_failure(setup_verify, monkeypatch):
    request, registry, _, _, _, _, _ = setup_verify
    registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="review")
    execute = DockerExecutor.execute

    def changed(self, run_request):
        run = execute(self, run_request)
        registry.disable(GUARD_ID, reason="disabled while running")
        return run

    monkeypatch.setattr(DockerExecutor, "execute", changed)
    report = verify_repository(request)
    assert report.exit_code == 5
    assert report.rows[0].verdict == "integrity_error"
    assert report.rows[0].run is not None


def test_unknown_impact_does_not_become_unaffected_or_start_a_runner(setup_verify, monkeypatch):
    request, registry, _, _, calls, _, inspection = setup_verify
    registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="review")
    impact = inspection.targets[0].model_copy(
        update={
            "impact": "unknown",
            "reason_codes": ("unmapped_changed_paths",),
        }
    )
    inspection = inspection.model_copy(
        update={
            "status": "unknown",
            "reason_codes": ("unmapped_changed_paths",),
            "targets": (impact,),
        }
    )
    monkeypatch.setattr(verify_module, "inspect_repository", lambda *args: inspection)
    report = verify_repository(request)
    assert report.exit_code == 4
    assert report.counts["unknown"] == 1
    assert "unmapped_changed_paths" in report.rows[0].reason_codes
    assert report.counts["skipped"] == 0
    assert not calls


def test_broken_index_and_invalid_config_still_leave_machine_reports(setup_verify):
    request, registry, _, _, calls, _, _ = setup_verify
    (registry.root / "registry.sqlite3").unlink()
    report = verify_repository(request)
    assert report.exit_code == 5
    assert (request.cwd / "result/report.json").is_file()
    request.config.write_bytes(b"invalid JSON")
    invalid = verify_repository(replace(request, output=Path("invalid")))
    assert invalid.exit_code == 2
    assert (request.cwd / "invalid/report.md").is_file()
    assert not calls


def test_saved_summary_and_decision_digest_cannot_claim_different_results(setup_verify):
    request, _, _, _, _, _, _ = setup_verify
    report = verify_repository(request)
    payload = report.model_dump(mode="json")
    payload["counts"]["pass"] = 1
    with pytest.raises(ValueError, match="summary"):
        VerifyReport.model_validate_json(json.dumps(payload))
    payload = report.model_dump(mode="json")
    payload["decision_digest"] = IMAGE
    with pytest.raises(ValueError, match="decision digest"):
        VerifyReport.model_validate_json(json.dumps(payload))


def test_post_run_junit_damage_preserves_actual_record(setup_verify, monkeypatch):
    request, registry, _, _, _, _, _ = setup_verify
    registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="review")
    execute = DockerExecutor.execute

    def damaged(self, run_request):
        run = execute(self, run_request)
        (run_request.cwd / run.junit_ref).write_bytes(b"damaged")
        return run

    monkeypatch.setattr(DockerExecutor, "execute", damaged)
    report = verify_repository(request)
    assert report.exit_code == 5
    assert report.rows[0].run is not None
    assert report.rows[0].verdict == "integrity_error"


def test_unsupported_project_profile_is_unknown_without_docker(setup_verify):
    request, registry, _, _, calls, _, _ = setup_verify
    registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="review")
    config = json.loads(request.config.read_bytes())
    config["schema_version"] = "project-config.v2"
    request.config.write_text(json.dumps(config), encoding="utf-8")
    report = verify_repository(request)
    assert report.exit_code == 4
    assert report.rows[0].reason_codes == ("project_profile_requires_review",)
    assert not calls


def test_unknown_raw_image_is_rejected_with_a_report_before_selection(setup_verify, monkeypatch):
    from counterguard.runner_catalog import resolve_runner

    request, _, _, _, calls, _, _ = setup_verify
    monkeypatch.setattr(verify_module, "resolve_runner", resolve_runner)
    report = verify_repository(request)
    assert report.exit_code == 5
    assert report.runner_review_digest is None
    assert not report.rows and not calls
    assert (request.cwd / "result/report.json").is_file()
