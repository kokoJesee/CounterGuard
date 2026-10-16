"""Freeze standards before learning, then audit and execute the actual baseline chain."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.protocol import verify_protocol
from scripts.prepare_scope_v1 import prepare

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_DIGEST = "sha256:1f401186a3f51c17e582dbbdc96f9324e47e128f90fcb91f29594690bc8daa3a"
PROTOCOL = "experiments/scope_v1.json"


@pytest.fixture(scope="module")
def prepared_workspace(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("scope-protocol")
    for directory in ("examples", "tests/contract_tests", "benchmarks", "experiments"):
        shutil.copytree(
            PROJECT_ROOT / directory,
            workspace / directory,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    prepare(workspace)
    return workspace


@pytest.fixture
def mutable_workspace(prepared_workspace, tmp_path):
    shutil.copytree(
        prepared_workspace,
        tmp_path,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return tmp_path


def rewrite(path, payload):
    payload["artifact_digest"] = digest_json_artifact(payload)
    path.write_bytes(canonical_json_bytes(payload))


def test_protocol_digest_is_pinned_and_clean_assets_verify(prepared_workspace):
    protocol, manifest, guards = verify_protocol(PROTOCOL, cwd=prepared_workspace)
    assert protocol.artifact_digest == PROTOCOL_DIGEST
    assert (
        digest_json_artifact(json.loads((PROJECT_ROOT / PROTOCOL).read_bytes())) == PROTOCOL_DIGEST
    )
    assert len(guards) == 2
    assert sum(len(p.initial + p.refinement_additions) for p in manifest.phases.values()) == 9
    assert sum(len(p.holdout) for p in manifest.phases.values()) == 6
    for phase in manifest.phases.values():
        assert not set(phase.initial + phase.refinement_additions) & set(phase.holdout)
    audited = CliRunner().invoke(
        app, ["experiment", "verify", "--protocol", PROTOCOL, "--cwd", str(prepared_workspace)]
    )
    assert audited.exit_code == 0, audited.output


def test_rehashed_method_change_is_rejected(mutable_workspace):
    path = mutable_workspace / PROTOCOL
    payload = json.loads(path.read_bytes())
    payload["methods"]["b2_interface"] = "version_and_interface"
    rewrite(path, payload)
    with pytest.raises(ArtifactIntegrityError, match="Invalid ExperimentProtocol"):
        verify_protocol(PROTOCOL, cwd=mutable_workspace)


def test_rehashed_holdout_contamination_is_rejected(mutable_workspace):
    path = mutable_workspace / "benchmarks/splits/scope_v1.json"
    payload = json.loads(path.read_bytes())
    phase = next(iter(payload["phases"].values()))
    phase["initial"].append(phase["holdout"][0])
    rewrite(path, payload)
    protocol_path = mutable_workspace / PROTOCOL
    protocol = json.loads(protocol_path.read_bytes())
    protocol["split_digest"] = payload["artifact_digest"]
    rewrite(protocol_path, protocol)
    with pytest.raises(ArtifactIntegrityError, match="Invalid SplitManifest"):
        verify_protocol(PROTOCOL, cwd=mutable_workspace)


@pytest.mark.parametrize(
    "reference",
    [
        "benchmarks/train/discount_scope_samples.json",
        "examples/discount/implementations/discount_amount_v1_correct.py",
        "artifacts/guards/grd_discount_member_rate_regression_v2/test_guard.py",
    ],
)
def test_data_or_code_drift_is_rejected(mutable_workspace, reference):
    path = mutable_workspace / reference
    path.write_bytes(path.read_bytes() + b"\n ")
    if reference.endswith(".json"):
        payload = json.loads(path.read_bytes())
        payload[0]["labels"]["guard_applicable"] = False
        path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError):
        verify_protocol(PROTOCOL, cwd=mutable_workspace)


def test_baselines_execute_only_applicable_training_rows(prepared_workspace):
    result = CliRunner().invoke(
        app,
        [
            "benchmark",
            "baselines",
            "--protocol",
            PROTOCOL,
            "--cwd",
            str(prepared_workspace),
            "--split",
            "train",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["counts"] == {
        "b1_always": {"tp": 4, "fp": 5, "tn": 0, "fn": 0},
        "b2_interface": {"tp": 4, "fp": 3, "tn": 2, "fn": 0},
    }
    assert report["sample_count"] == 9
    assert report["execution_count"] == 16
    assert report["infrastructure_errors"] == 0
    skipped = [row for row in report["predictions"] if row["scope_decision"] == "inapplicable"]
    assert len(skipped) == 2
    assert all(row["execution_outcome"] == "not_run" for row in skipped)
    assert all(row["sample_id"].startswith("train-") for row in report["predictions"])
    output = prepared_workspace / "artifacts/experiments/scope-v1/train-baselines"
    replays = [json.loads(line) for line in (output / "replays.jsonl").read_bytes().splitlines()]
    assert len(replays) == 16
    assert all(row["run"]["pytest_exit_code"] in (0, 1) for row in replays)
    assert len(list((prepared_workspace / "artifacts/scopes/scope-v1").glob("*/*.json"))) == 4


def test_holdout_execution_is_rejected_before_reading_protocol():
    result = CliRunner().invoke(
        app, ["benchmark", "baselines", "--protocol", "missing.json", "--split", "holdout"]
    )
    assert result.exit_code == 2
    assert "This command accepts only the training split" in result.output
