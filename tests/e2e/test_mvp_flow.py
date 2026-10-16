"""Exercise the public Pipeline without seeding any prebuilt Evidence or Guard."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import Guard
from counterguard.pipeline import (
    PipelineExecutionError,
    PipelineFailure,
    run_pipeline,
    verify_pipeline,
)
from counterguard.replay import ReplayResult
from counterguard.scope import FitManifest, ScopeLearningResult
from counterguard.workspace import (
    WorkspaceManifest,
    verify_workspace,
)

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = "examples/demo/mvp.yaml"


def seed(root):
    for directory in ("examples", "benchmarks", "experiments", "tests/fixtures/agent_responses"):
        shutil.copytree(
            ROOT / directory,
            root / directory,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
        )
    return root


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    root = seed(tmp_path_factory.mktemp("pf"))
    poison = root / "artifacts/guards/grd_discount_member_rate_regression_v2/guard.json"
    poison.parent.mkdir(parents=True)
    poison.write_bytes(b"OLD_ARTIFACT_MUST_NOT_BE_CONSUMED_OR_REPLACED")
    result = run_pipeline(SCENARIO, cwd=root, workspace="out")
    assert poison.read_bytes() == b"OLD_ARTIFACT_MUST_NOT_BE_CONSUMED_OR_REPLACED"
    return root, result


@pytest.fixture
def fresh(tmp_path_factory):
    return seed(tmp_path_factory.mktemp("ps"))


@pytest.fixture
def mutable_flow(flow, tmp_path_factory):
    destination = tmp_path_factory.mktemp("pm")
    shutil.copytree(
        flow[0],
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    return destination


def save_scenario(root, payload):
    path = root / SCENARIO
    path.write_bytes(canonical_json_bytes(payload) + b"\n")


def test_end_to_end_two_guards_three_outcomes_each(flow):
    root, manifest = flow
    assert manifest.accepted and manifest.execution_count == 4
    assert manifest.verdict_counts == {"violation": 2, "pass": 2, "skipped_inapplicable": 2}
    for group in manifest.groups:
        rows = [row for row in manifest.replays if row.guard_id == group.guard_id]
        assert {(row.scope_decision, row.execution_outcome, row.verdict) for row in rows} == {
            ("applicable", "test_failed", "violation"),
            ("applicable", "passed", "pass"),
            ("inapplicable", "not_run", "skipped_inapplicable"),
        }
        guard = Guard.model_validate_json((root / group.guard.ref).read_bytes())
        assert len(guard.cases) == (2 if "discount" in group.guard_id else 1)
        assert guard.source_evidence_ref.endswith("/evidence.json")
    for row in manifest.replays:
        replay = ReplayResult.model_validate_json((root / row.replay.ref).read_bytes())
        if row.scope_decision == "inapplicable":
            assert replay.run is None
            assert not (root / row.replay.ref).parent.joinpath("runs").exists()


def test_learning_refines_one_clause_to_two_without_holdout(flow):
    root, manifest = flow
    for phase, link, size in (
        ("initial", manifest.initial_fit, 7),
        ("refined", manifest.refined_fit, 9),
    ):
        fit = FitManifest.model_validate_json((root / link.ref).read_bytes())
        assert fit.phase == phase
        assert sum(len(group.training_sample_ids) for group in fit.groups) == size
        assert all(
            "holdout" not in sample for group in fit.groups for sample in group.training_sample_ids
        )
    for group in manifest.groups:
        initial = ScopeLearningResult.model_validate_json(
            (root / group.initial_learning.ref).read_bytes()
        )
        refined = ScopeLearningResult.model_validate_json(
            (root / group.refined_learning.ref).read_bytes()
        )
        assert [clause.field for clause in initial.clauses] == ["contract_version"]
        assert [clause.field for clause in refined.clauses] == [
            "contract_version",
            "interface_kind",
        ]
        assert refined.training_confusion.fp == refined.training_confusion.fn == 0


def test_input_mirror_is_exact_and_has_no_artifact_inputs(flow):
    root, manifest = flow
    ledger = WorkspaceManifest.model_validate_json((root / manifest.workspace.ref).read_bytes())
    runtime = verify_workspace(ledger, cwd=root)
    assert runtime == root / manifest.runtime_ref
    assert all(not pin.ref.startswith("artifacts/") for pin in ledger.files)
    assert all(
        (root / pin.ref).read_bytes() == (runtime / pin.ref).read_bytes() for pin in ledger.files
    )


def test_repeat_and_verify_are_read_only(flow, monkeypatch):
    root, manifest = flow
    before = {p: p.read_bytes() for p in (root / "out").rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail("Completed Pipeline must not execute, call provider or refit")

    for target in (
        "subprocess.run",
        "counterguard.pipeline.capture_candidate",
        "counterguard.pipeline.compile_guard",
        "counterguard.pipeline.fit_scopes",
        "counterguard.pipeline.replay_guard",
    ):
        monkeypatch.setattr(target, forbidden)
    assert verify_pipeline(root / "out/run_manifest.json", cwd=root) == manifest
    assert run_pipeline(SCENARIO, cwd=root, workspace="out") == manifest
    assert before == {p: p.read_bytes() for p in (root / "out").rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "file_kind", ["source", "snapshot", "guard_test", "learning", "junit", "missing_replay"]
)
def test_dangling_refs_and_tampered_inputs_are_rejected(mutable_flow, file_kind):
    root = mutable_flow
    manifest = json.loads((root / "out/run_manifest.json").read_bytes())
    replay_row = next(row for row in manifest["replays"] if row["scope_decision"] == "applicable")
    replay = json.loads((root / replay_row["replay"]["ref"]).read_bytes())
    files = {
        "source": root / "examples/discount/implementations/final_price_v1_buggy.py",
        "snapshot": root
        / manifest["runtime_ref"]
        / "examples/discount/implementations/final_price_v1_buggy.py",
        "guard_test": root
        / manifest["runtime_ref"]
        / "artifacts/guards/grd_discount_member_rate_regression_v2/test_guard.py",
        "learning": root / manifest["groups"][0]["refined_learning"]["ref"],
        "junit": root / manifest["runtime_ref"] / replay["run"]["junit_ref"],
        "missing_replay": root / replay_row["replay"]["ref"],
    }
    path = files[file_kind]
    if file_kind == "missing_replay":
        path.unlink()
    elif file_kind == "learning":
        payload = json.loads(path.read_bytes())
        payload["clauses"][0]["value"] = "v2"
        payload["artifact_digest"] = digest_json_artifact(payload)
        path.write_bytes(canonical_json_bytes(payload))
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ArtifactIntegrityError):
        verify_pipeline(root / "out/run_manifest.json", cwd=root)


def test_resigned_manifest_cannot_claim_another_acceptance(mutable_flow):
    path = mutable_flow / "out/run_manifest.json"
    payload = json.loads(path.read_bytes())
    payload["accepted"] = False
    payload["artifact_digest"] = digest_json_artifact(payload)
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="acceptance"):
        verify_pipeline(path, cwd=mutable_flow)


def test_candidate_rejection_stops_before_compiler_and_keeps_failure(fresh, monkeypatch):
    payload = json.loads((fresh / SCENARIO).read_bytes())
    payload["guards"][0]["request_ref"] = "examples/demo/requests/discount_empty.json"
    save_scenario(fresh, payload)

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected candidate must not reach Compiler")

    monkeypatch.setattr("counterguard.pipeline.compile_guard", forbidden)
    with pytest.raises(PipelineExecutionError) as error:
        run_pipeline(SCENARIO, cwd=fresh, workspace="out")
    assert error.value.exit_code == 2
    failure = PipelineFailure.model_validate_json((fresh / "out/failure.json").read_bytes())
    assert failure.failed_stage == "capture" and failure.reason_code == "candidate_not_verified"
    assert digest_json_artifact(failure) == failure.artifact_digest
    assert not (fresh / "out/run_manifest.json").exists()
    before = (fresh / "out/failure.json").read_bytes()
    with pytest.raises(ArtifactIntegrityError, match="empty"):
        run_pipeline(SCENARIO, cwd=fresh, workspace="out")
    assert (fresh / "out/failure.json").read_bytes() == before


def test_changed_gate_test_stops_before_next_capture_or_compile(fresh, monkeypatch):
    from counterguard.pipeline import capture_candidate

    calls = []

    def corrupt(*args, **kwargs):
        result = capture_candidate(*args, **kwargs)
        calls.append(result)
        test = kwargs["cwd"] / result.test_ref
        test.write_bytes(test.read_bytes() + b"\n")
        return result

    monkeypatch.setattr("counterguard.pipeline.capture_candidate", corrupt)
    with pytest.raises(PipelineExecutionError) as error:
        run_pipeline(SCENARIO, cwd=fresh, workspace="out")
    assert error.value.exit_code == 5 and len(calls) == 1
    failure = json.loads((fresh / "out/failure.json").read_bytes())
    assert failure["failed_stage"] == "capture"
    assert not (fresh / "out/w/artifacts/guards").exists()


def test_changed_learning_stops_before_refinement_or_replay(fresh, monkeypatch):
    from counterguard.pipeline import fit_scopes

    phases = []

    def corrupt(*args, **kwargs):
        result = fit_scopes(*args, **kwargs)
        phases.append(kwargs["phase"])
        path = kwargs["cwd"] / result.groups[0].learning_ref
        payload = json.loads(path.read_bytes())
        payload["clauses"][0]["value"] = "v2"
        payload["artifact_digest"] = digest_json_artifact(payload)
        path.write_bytes(canonical_json_bytes(payload))
        return result

    monkeypatch.setattr("counterguard.pipeline.fit_scopes", corrupt)
    with pytest.raises(PipelineExecutionError) as error:
        run_pipeline(SCENARIO, cwd=fresh, workspace="out")
    assert error.value.exit_code == 5 and phases == ["initial"]
    assert not (fresh / "out/w/artifacts/replays").exists()
    assert json.loads((fresh / "out/failure.json").read_bytes())["failed_stage"] == "learn"


@pytest.mark.parametrize("mutation", ["holdout", "missing_response", "context", "long_path"])
def test_invalid_inputs_fail_before_any_execution_or_directory(fresh, monkeypatch, mutation):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid inputs must fail before execution")

    monkeypatch.setattr("subprocess.run", forbidden)
    payload = json.loads((fresh / SCENARIO).read_bytes())
    output = fresh / "out"
    if mutation == "holdout":
        payload["guards"][0]["replay_sample_ids"][0] = "holdout-v1-alternate-bug"
        save_scenario(fresh, payload)
    elif mutation == "missing_response":
        (fresh / "tests/fixtures/agent_responses/discount_v1.json").unlink()
    elif mutation == "context":
        path = fresh / "benchmarks/context/scope_v1.json"
        path.write_bytes(path.read_bytes() + b"garbage")
    else:
        output = fresh / ("x" * 100) / ("y" * 60)
    with pytest.raises((ArtifactIntegrityError, ValueError, OSError)):
        run_pipeline(SCENARIO, cwd=fresh, workspace=output)
    assert not output.exists()


def test_completed_workspace_does_not_accept_another_scenario_path(flow):
    root, _ = flow
    alternate = root / "other-scenario.yaml"
    alternate.write_bytes((root / SCENARIO).read_bytes())
    with pytest.raises(ArtifactIntegrityError, match="another scenario"):
        run_pipeline(alternate, cwd=root, workspace="out")


def test_unexpected_fault_keeps_diagnostic_without_echoing_error_payload(fresh, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("SECRET_FAULT_PAYLOAD_MUST_NOT_BE_SAVED")

    monkeypatch.setattr("counterguard.pipeline.capture_candidate", broken)
    with pytest.raises(PipelineExecutionError):
        run_pipeline(SCENARIO, cwd=fresh, workspace="out")
    raw = (fresh / "out/failure.json").read_bytes()
    assert b"SECRET_FAULT_PAYLOAD_MUST_NOT_BE_SAVED" not in raw
    assert json.loads(raw)["reason_code"] == "RuntimeError"


def test_cli_reuses_manifest_and_preserves_violation_and_skip(flow):
    root, manifest = flow
    runner = CliRunner()
    completed = runner.invoke(
        app, ["pipeline", "run", "--scenario", SCENARIO, "--workspace", "out", "--cwd", str(root)]
    )
    assert completed.exit_code == 0, completed.output
    assert json.loads(completed.stdout)["verdict_counts"] == manifest.verdict_counts
    verified = runner.invoke(
        app, ["pipeline", "verify", "out/run_manifest.json", "--cwd", str(root)]
    )
    assert verified.exit_code == 0, verified.output


def test_capture_timeout_does_not_become_a_successful_pipeline(fresh):
    request = fresh / "examples/demo/requests/discount_agent.json"
    payload = json.loads(request.read_bytes())
    payload["timeout_seconds"] = 0.001
    request.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(PipelineExecutionError) as error:
        run_pipeline(SCENARIO, cwd=fresh, workspace="out")
    assert error.value.exit_code == 3
    failure = json.loads((fresh / "out/failure.json").read_bytes())
    assert failure["failed_stage"] == "capture"
    assert not (fresh / "out/run_manifest.json").exists()


def test_missing_completed_replay_stops_before_another_replay(fresh, monkeypatch):
    from counterguard.pipeline import replay_guard

    calls = []

    def remove(*args, **kwargs):
        result = replay_guard(*args, **kwargs)
        calls.append(result)
        (args[0].cwd / f"artifacts/replays/{result.replay_id}/result.json").unlink()
        return result

    monkeypatch.setattr("counterguard.pipeline.replay_guard", remove)
    with pytest.raises(PipelineExecutionError) as error:
        run_pipeline(SCENARIO, cwd=fresh, workspace="out")
    assert error.value.exit_code == 5 and len(calls) == 1
    assert json.loads((fresh / "out/failure.json").read_bytes())["failed_stage"] == "replay"


def test_changed_source_stops_before_second_capture(fresh, monkeypatch):
    from counterguard.pipeline import capture_candidate

    calls = []

    def change(*args, **kwargs):
        result = capture_candidate(*args, **kwargs)
        calls.append(result)
        path = fresh / "examples/discount/implementations/final_price_v1_buggy.py"
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr("counterguard.pipeline.capture_candidate", change)
    with pytest.raises(PipelineExecutionError) as error:
        run_pipeline(SCENARIO, cwd=fresh, workspace="out")
    assert error.value.exit_code == 5 and len(calls) == 1
    assert not (fresh / "out/w/artifacts/guards").exists()


def test_workspace_does_not_copy_credentials_or_git(fresh):
    from counterguard.workspace import prepare_workspace

    for ref in (".env", ".git/config", ".venv/secret.txt", "unlisted.txt"):
        path = fresh / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("SECRET_FILE_MUST_NOT_BE_COPIED", encoding="utf-8")
    ledger = prepare_workspace(Path(SCENARIO), cwd=fresh, output=fresh / "out")
    assert all(
        pin.ref not in {".env", ".git/config", ".venv/secret.txt", "unlisted.txt"}
        for pin in ledger.files
    )
    assert not (fresh / "out/w/.env").exists()
    assert not (fresh / "out/w/.git").exists()


def test_general_yaml_and_extra_scenario_fields_are_not_silently_accepted(fresh):
    payload = json.loads((ROOT / SCENARIO).read_bytes())
    payload["expected_train"] = {"fp": 0}
    save_scenario(fresh, payload)
    with pytest.raises(ValueError, match="JSON-compatible YAML"):
        run_pipeline(SCENARIO, cwd=fresh, workspace="out")
    assert not (fresh / "out").exists()
    (fresh / SCENARIO).write_text("scenario_id: arbitrary\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON-compatible YAML"):
        run_pipeline(SCENARIO, cwd=fresh, workspace="out")
    assert not (fresh / "out").exists()
