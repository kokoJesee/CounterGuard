"""Real double runs and immutability checks across the independent Agent Gate."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.evidence import verify_evidence
from counterguard.models import RunOutcome
from counterguard.verification_gate import capture_candidate, gate_exit_code, verify_gate

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workspace(tmp_path_factory):
    root = tmp_path_factory.mktemp("vg")
    for directory in ("examples", "tests/fixtures/agent_responses"):
        shutil.copytree(
            ROOT / directory, root / directory, ignore=shutil.ignore_patterns("__pycache__")
        )
    return root


def request_file(workspace, *, scenario="discount", **changes):
    payload = json.loads((workspace / f"examples/demo/requests/{scenario}_agent.json").read_bytes())
    payload.update(changes)
    path = workspace / "request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def gate_path(workspace, scenario="discount"):
    return workspace / f"out/candidates/cnd_{scenario}_agent_v1/gate.json"


def capture(workspace, **changes):
    return capture_candidate(request_file(workspace, **changes), cwd=workspace, workspace="out")


@pytest.mark.parametrize(
    "scenario,failures",
    [
        ("discount", {"member-price", "member-rounding"}),
        ("query", {"below-minimum"}),
    ],
)
def test_recorded_candidate_becomes_genuine_evidence(workspace, scenario, failures):
    result = capture(workspace, scenario=scenario)
    assert result.status == "verified"
    assert gate_exit_code(result, cwd=workspace) == 0
    evidence = verify_evidence(result.evidence_ref, cwd=workspace)
    assert evidence.reproduced
    assert evidence.buggy_run.outcome == RunOutcome.TEST_FAILED
    assert evidence.fixed_run.outcome == RunOutcome.PASSED
    assert set(evidence.failing_case_ids) == failures
    assert result == verify_gate(gate_path(workspace, scenario), cwd=workspace)


def test_repeat_is_read_only_and_does_not_forge_time(workspace, monkeypatch):
    path = request_file(workspace)
    result = capture_candidate(path, cwd=workspace, workspace="out")
    before = {p: p.read_bytes() for p in (workspace / "out").rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail("Completed requests must not execute pytest or call the provider")

    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("counterguard.model_client.RecordedModelClient.generate", forbidden)
    repeated = capture_candidate(path, cwd=workspace, workspace="out")
    assert repeated == result
    assert repeated.created_at == result.created_at
    assert all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize("response_name", ["illegal_code", "empty_tests"])
def test_invalid_candidate_never_starts_pytest_or_publishes_evidence(
    workspace, monkeypatch, response_name
):
    def forbidden(*args, **kwargs):
        pytest.fail("Rejected candidates must never start pytest")

    monkeypatch.setattr("subprocess.run", forbidden)
    result = capture(workspace, response_ref=f"tests/fixtures/agent_responses/{response_name}.json")
    assert result.status == "rejected"
    assert result.reason_code == "candidate_rejected"
    assert result.evidence_ref is None
    assert result.test_ref is None
    assert result.diagnostic_evidence_ref is None
    assert not (workspace / "out/evidence").exists()
    assert gate_exit_code(result, cwd=workspace) == 2
    stored = b"".join(p.read_bytes() for p in (workspace / "out").rglob("*.json"))
    assert b"MODEL_PAYLOAD_MUST_NOT_RUN_OR_BE_LOGGED" not in stored


def test_timeout_is_rejected_and_not_published(workspace):
    result = capture(workspace, timeout_seconds=0.001)
    assert result.status == "rejected"
    assert result.evidence_ref is None
    evidence = verify_evidence(result.diagnostic_evidence_ref, cwd=workspace)
    assert evidence.buggy_run.outcome == RunOutcome.TIMEOUT
    assert not evidence.reproduced
    assert gate_exit_code(result, cwd=workspace) == 3
    assert not (workspace / "out/evidence").exists()


def test_target_import_error_cannot_become_verified_failure(workspace):
    source = workspace / "examples/discount/implementations/final_price_v1_buggy.py"
    source.write_text(
        "raise RuntimeError('broken import')\n" + source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = capture(workspace)
    assert result.status == "rejected"
    evidence = verify_evidence(result.diagnostic_evidence_ref, cwd=workspace)
    assert evidence.buggy_run.outcome == RunOutcome.PROCESS_ERROR
    assert result.evidence_ref is None
    assert gate_exit_code(result, cwd=workspace) == 3


def test_collection_error_cannot_be_promoted(workspace, monkeypatch):
    from counterguard.independent_verifier import render_candidate

    # Fault injection in the trusted renderer, never execution of model code.
    def broken_renderer(candidate, context):
        return b"import missing_collection_dependency_eg\n" + render_candidate(candidate, context)

    monkeypatch.setattr("counterguard.verification_gate.render_candidate", broken_renderer)
    result = capture(workspace)
    evidence = verify_evidence(result.diagnostic_evidence_ref, cwd=workspace)
    assert evidence.buggy_run.pytest_exit_code == 2
    assert evidence.buggy_run.outcome == RunOutcome.INTERRUPTED
    assert not evidence.reproduced
    assert result.evidence_ref is None
    assert gate_exit_code(result, cwd=workspace) == 3


@pytest.mark.parametrize("target_role", ["buggy_target", "fixed_target"])
def test_missing_bidirectional_behavior_is_rejected(workspace, target_role):
    replacement = (
        "examples.discount.implementations.final_price_v1_fixed:calculate_price"
        if target_role == "buggy_target"
        else "examples.discount.implementations.final_price_v1_buggy:calculate_price"
    )
    result = capture(workspace, **{target_role: replacement})
    assert result.status == "rejected"
    assert result.reason_code == "not_reproduced"
    assert result.evidence_ref is None
    assert gate_exit_code(result, cwd=workspace) == 1


def test_credentials_do_not_enter_pytest_logs_or_candidate_json(workspace, monkeypatch):
    secret = "API_KEY_MUST_NEVER_REACH_LOGS_0123"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    for name in ("buggy", "fixed"):
        source = workspace / f"examples/discount/implementations/final_price_v1_{name}.py"
        source.write_text(
            source.read_text(encoding="utf-8")
            + '\nimport os\nprint(os.environ.get("OPENAI_API_KEY", "no-key"))\n',
            encoding="utf-8",
        )
    result = capture(workspace)
    assert result.status == "verified"
    assert all(
        secret.encode() not in p.read_bytes() for p in (workspace / "out").rglob("*") if p.is_file()
    )


@pytest.mark.parametrize("tamper", ["request", "response", "fixed", "test", "gate_fact"])
def test_tamper_is_rejected_even_after_resigning_gate(workspace, tamper):
    result = capture(workspace)
    files = {
        "request": workspace / "request.json",
        "response": workspace / "tests/fixtures/agent_responses/discount_v1.json",
        "fixed": workspace / result.fixed_target.source_ref,
        "test": workspace / result.test_ref,
    }
    if tamper == "gate_fact":
        payload = json.loads(gate_path(workspace).read_bytes())
        payload["status"] = "rejected"
        payload["reason_code"] = "not_reproduced"
        payload["evidence_ref"] = payload["evidence_digest"] = None
        payload["artifact_digest"] = digest_json_artifact(payload)
        gate_path(workspace).write_bytes(canonical_json_bytes(payload))
    else:
        files[tamper].write_bytes(files[tamper].read_bytes() + b"\n")
    with pytest.raises(ArtifactIntegrityError):
        verify_gate(gate_path(workspace), cwd=workspace)


def test_long_gate_path_rejected_before_response_or_outputs(workspace, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Path preflight must run before calling the provider")

    monkeypatch.setattr("counterguard.model_client.RecordedModelClient.generate", forbidden)
    output = workspace / ("a" * 90) / ("b" * 60)
    with pytest.raises(ValueError, match="UTF-16"):
        capture_candidate(request_file(workspace), cwd=workspace, workspace=output)
    assert not output.exists()


def test_resigned_run_case_cannot_contradict_raw_junit(workspace):
    result = capture(workspace)
    diagnostic = workspace / result.diagnostic_evidence_ref
    payload = json.loads(diagnostic.read_bytes())
    payload["buggy_run"]["case_results"][0]["duration_ms"] += 999
    payload["artifact_digest"] = digest_json_artifact(payload)
    diagnostic.write_bytes(canonical_json_bytes(payload) + b"\n")
    (workspace / result.evidence_ref).write_bytes(diagnostic.read_bytes())
    gate = json.loads(gate_path(workspace).read_bytes())
    gate["evidence_digest"] = gate["diagnostic_evidence_digest"] = payload["artifact_digest"]
    gate["artifact_digest"] = digest_json_artifact(gate)
    gate_path(workspace).write_bytes(canonical_json_bytes(gate) + b"\n")
    with pytest.raises(ArtifactIntegrityError, match="raw JUnit"):
        verify_gate(gate_path(workspace), cwd=workspace)


def test_request_id_cannot_be_reused_for_another_file(workspace):
    result = capture(workspace)
    duplicate = workspace / "other-request.json"
    duplicate.write_bytes((workspace / "request.json").read_bytes())
    with pytest.raises(ArtifactIntegrityError, match="another request file"):
        capture_candidate(duplicate, cwd=workspace, workspace="out")
    assert verify_gate(gate_path(workspace), cwd=workspace) == result


def test_partial_candidate_directory_cannot_be_overwritten(workspace):
    partial = workspace / "out/candidates/cnd_discount_agent_v1"
    partial.mkdir(parents=True)
    marker = partial / "candidate.json"
    marker.write_bytes(b"interrupted execution")
    with pytest.raises(ArtifactIntegrityError, match="Incomplete"):
        capture(workspace)
    assert marker.read_bytes() == b"interrupted execution"


def test_request_cli_and_read_only_verify(workspace):
    runner = CliRunner()
    path = request_file(workspace)
    result = runner.invoke(
        app,
        [
            "capture",
            "--request",
            str(path),
            "--agent-source",
            "recorded",
            "--workspace",
            "out",
            "--cwd",
            str(workspace),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "verified"
    checked = runner.invoke(
        app, ["verification", "verify", str(gate_path(workspace)), "--cwd", str(workspace)]
    )
    assert checked.exit_code == 0, checked.output


@pytest.mark.parametrize(
    "flags",
    [
        [],
        ["--agent-source", "recorded"],
        ["--request", "request.json", "--workspace", "out"],
        [
            "--request",
            "request.json",
            "--agent-source",
            "recorded",
            "--workspace",
            "out",
            "--test",
            "unsafe.py",
        ],
    ],
)
def test_cli_rejects_missing_or_mixed_modes(flags):
    result = CliRunner().invoke(app, ["capture", *flags])
    assert result.exit_code == 2
