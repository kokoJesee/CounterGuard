"""D13 audits one real offline flow and isolated copies of its published records."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.demo import run_demo
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.replay import ReplayRequest, replay_guard, verify_replay
from counterguard.report import CommandReport, OutputFormat, render_report

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def full_flow(tmp_path_factory):
    root = tmp_path_factory.mktemp("fm")
    for name in ("examples", "benchmarks", "experiments", "tests/fixtures/agent_responses"):
        shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    return root, run_demo("examples/demo/mvp.yaml", cwd=root, workspace="out")


@pytest.fixture
def mutable_full(full_flow, tmp_path_factory):
    root = tmp_path_factory.mktemp("fc")
    shutil.copytree(
        full_flow[0],
        root,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    return root


def test_standalone_replay_verifier_rejects_resigned_execution_claim(mutable_full):
    root = mutable_full
    manifest = json.loads((root / "out/run_manifest.json").read_bytes())
    ref = next(r["replay"]["ref"] for r in manifest["replays"] if r["verdict"] == "pass")
    path = root / ref
    result = json.loads(path.read_bytes())
    result["run"]["case_results"][0]["duration_ms"] += 1000
    result["artifact_digest"] = digest_json_artifact(result)
    path.write_bytes(canonical_json_bytes(result))
    with pytest.raises(ArtifactIntegrityError, match="JUnit|execution"):
        verify_replay(path, cwd=root / "out/w")


def missing_contract(root):
    return ReplayRequest(
        Path("artifacts/guards/grd_discount_member_rate_regression_v2/guard.json"),
        Path("artifacts/fitted/refined/grd_discount_member_rate_regression_v2.json"),
        "examples.discount.implementations.final_price_v1_fixed:calculate_price",
        None,
        root / "out/w",
        Path("artifacts/unknown-example"),
    )


@pytest.mark.parametrize("kind", ["known", "unknown"])
def test_standalone_replay_verifier_rejects_resigned_decision_trace(mutable_full, kind):
    root = mutable_full
    runtime = root / "out/w"
    if kind == "known":
        manifest = json.loads((root / "out/run_manifest.json").read_bytes())
        path = root / next(
            r["replay"]["ref"] for r in manifest["replays"] if r["verdict"] == "pass"
        )
    else:
        result = replay_guard(missing_contract(root))
        path = runtime / f"artifacts/unknown-example/replays/{result.replay_id}/result.json"
    payload = json.loads(path.read_bytes())
    payload["decision_trace"][0]["expected"] = "invented-version"
    payload["artifact_digest"] = digest_json_artifact(payload)
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="trace"):
        verify_replay(path, cwd=runtime)


def test_real_unknown_has_no_execution_and_three_formats_keep_its_reason(full_flow, monkeypatch):
    root, _ = full_flow
    spec = missing_contract(root)

    def forbidden(*args, **kwargs):
        pytest.fail("A real unknown replay must not launch a process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = CliRunner().invoke(
        app,
        [
            "replay",
            "run",
            "--guard",
            str(spec.guard_path),
            "--scope",
            str(spec.scope_path),
            "--target",
            spec.target,
            "--cwd",
            str(spec.cwd),
            "--artifact-root",
            str(spec.artifact_root),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 4, result.output
    report = CommandReport.model_validate_json(result.stdout)
    assert report.payload["scope_decision"] == "unknown"
    assert report.payload["verdict"] == "skipped_unknown" and report.payload["run"] is None
    row = report.replays[0]
    assert (row.scope_decision, row.execution_outcome, row.final_verdict) == (
        "unknown",
        "not_run",
        "skipped",
    )
    assert row.reason == "Target contract metadata was not provided"
    path = spec.cwd / spec.artifact_root / f"replays/{report.payload['replay_id']}/result.json"
    assert verify_replay(path, cwd=spec.cwd).artifact_digest == report.payload["artifact_digest"]
    assert not (path.parent / "runs").exists()
    for format in (OutputFormat.TEXT, OutputFormat.MARKDOWN):
        rendered = render_report(report, format)
        assert "unknown | not_run | skipped" in rendered and row.reason in rendered


@pytest.mark.parametrize(
    "field",
    [
        "guard_id",
        "scope_id",
        "protocol_digest",
        "run_contract_id",
        "run_contract_digest",
        "target_module",
    ],
)
def test_standalone_replay_identity_fields_are_bound_to_verified_inputs(mutable_full, field):
    root = mutable_full
    if field == "target_module":
        result = replay_guard(missing_contract(root))
        path = root / "out/w/artifacts/unknown-example/replays" / result.replay_id / "result.json"
    else:
        manifest = json.loads((root / "out/run_manifest.json").read_bytes())
        path = root / next(
            row["replay"]["ref"] for row in manifest["replays"] if row["verdict"] == "pass"
        )
    payload = json.loads(path.read_bytes())
    if field == "target_module":
        payload["target"]["module"] = "examples.invented_target"
    elif field.startswith("run_"):
        payload["run"][field.removeprefix("run_")] = (
            "sha256:" + "0" * 64 if field.endswith("digest") else "invented-contract"
        )
    else:
        payload[field] = "sha256:" + "0" * 64 if field.endswith("digest") else "invented-identity"
    payload["artifact_digest"] = digest_json_artifact(payload)
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="bind|target"):
        verify_replay(path, cwd=root / "out/w")


def test_missing_target_is_a_configuration_error_without_execution(full_flow, monkeypatch):
    root, _ = full_flow
    spec = missing_contract(root)

    def forbidden(*a, **k):
        pytest.fail("A missing target must be rejected before execution")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = CliRunner().invoke(
        app,
        [
            "replay",
            "run",
            "--guard",
            str(spec.guard_path),
            "--scope",
            str(spec.scope_path),
            "--target",
            "examples.no_such_target:calculate_price",
            "--cwd",
            str(spec.cwd),
            "--artifact-root",
            "artifacts/missing-target",
        ],
    )
    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output
    assert not (spec.cwd / "artifacts/missing-target").exists()
