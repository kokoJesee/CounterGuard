"""Automatic extraction must agree with every frozen annotation before learning."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.digests import digest_json_artifact
from counterguard.features import FeatureRecord

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = "artifacts/audits/feature-parity.json"


@pytest.fixture
def workspace(tmp_path):
    for directory in ("examples", "benchmarks"):
        shutil.copytree(
            PROJECT_ROOT / directory,
            tmp_path / directory,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    return tmp_path


def audit(workspace):
    result = CliRunner().invoke(
        app,
        [
            "features",
            "audit",
            "--benchmark-root",
            "benchmarks",
            "--output",
            OUTPUT,
            "--cwd",
            str(workspace),
        ],
    )
    return result, json.loads((workspace / OUTPUT).read_bytes())


def test_all_fifteen_samples_match_and_repeated_artifacts_are_identical(workspace):
    result, report = audit(workspace)
    assert result.exit_code == 0, result.output
    assert (report["sample_count"], report["matched"], report["mismatched"], report["errors"]) == (
        15,
        15,
        0,
        0,
    )
    assert digest_json_artifact(report) == report["artifact_digest"]
    assert all(entry["missing"] == entry["unexpected"] == [] for entry in report["entries"])
    assert len(list((workspace / "artifacts/features/ast-features.v1").glob("*/*.json"))) == 15
    first = (workspace / OUTPUT).read_bytes()
    repeated, _ = audit(workspace)
    assert repeated.exit_code == 0, repeated.output
    assert (workspace / OUTPUT).read_bytes() == first
    for entry in report["entries"]:
        record = FeatureRecord.model_validate_json((workspace / entry["feature_ref"]).read_bytes())
        assert digest_json_artifact(record) == record.artifact_digest == entry["feature_digest"]
        assert set(record.features.model_dump()) == {
            "contract_family",
            "contract_version",
            "interface_kind",
            "symbol_signature",
            "module_group",
            "ast_features",
        }


def test_manual_annotation_drift_produces_missing_and_unexpected_diff(workspace):
    path = workspace / "benchmarks/train/discount_scope_samples.json"
    samples = json.loads(path.read_bytes())
    samples[0]["features"]["ast_features"] = ["decimal:subtract"]
    path.write_text(json.dumps(samples), encoding="utf-8")
    result, report = audit(workspace)
    assert result.exit_code == 1
    assert report["mismatched"] == 1 and report["matched"] == 14
    row = next(
        entry for entry in report["entries"] if entry["sample_id"] == samples[0]["sample_id"]
    )
    assert row["missing"] == ["decimal:subtract"]
    assert row["unexpected"] == ["branch:is_member", "decimal:multiply", "round:half_up"]


def test_scalar_metadata_is_derived_from_contract_and_compared_separately(workspace):
    path = workspace / "benchmarks/train/discount_scope_samples.json"
    samples = json.loads(path.read_bytes())
    samples[0]["features"]["contract_version"] = "v999"
    samples[0]["labels"] = {"never": "must not be consumed by extractor"}
    path.write_text(json.dumps(samples), encoding="utf-8")
    result, report = audit(workspace)
    assert result.exit_code == 1
    row = next(entry for entry in report["entries"] if entry["status"] == "mismatched")
    assert row["metadata_diff"] == {"contract_version": {"expected": "v999", "actual": "v1"}}


@pytest.mark.parametrize("problem", ["syntax", "missing", "unsupported"])
def test_bad_target_retains_error_report_without_publishing_empty_features(workspace, problem):
    source = workspace / "examples/discount/implementations/final_price_v1_buggy.py"
    if problem == "missing":
        source.unlink()
    elif problem == "syntax":
        source.write_text("def broken(:", encoding="utf-8")
    else:
        source.write_text(
            "def calculate_price(amount, is_member):\n return lambda: amount", encoding="utf-8"
        )
    result, report = audit(workspace)
    assert result.exit_code == 3
    assert report["errors"] == 1 and report["matched"] == 14
    row = next(entry for entry in report["entries"] if entry["status"] == "error")
    assert row["error"]
    assert "actual" not in row
    assert not list(
        (workspace / "artifacts/features/ast-features.v1").glob("*/train-v1-source-bug.json")
    )


def test_unknown_annotation_vocabulary_is_rejected(workspace):
    path = workspace / "benchmarks/train/discount_scope_samples.json"
    samples = json.loads(path.read_bytes())
    samples[0]["features"]["ast_features"].append("branch:no_branch")
    path.write_text(json.dumps(samples), encoding="utf-8")
    result, report = audit(workspace)
    assert result.exit_code == 2
    assert report["errors"] == 1


def test_source_drift_cannot_silently_overwrite_extracted_record(workspace):
    result, _ = audit(workspace)
    assert result.exit_code == 0
    source = workspace / "examples/discount/implementations/final_price_v1_buggy.py"
    source.write_bytes(source.read_bytes() + b"\n# changed source\n")
    result, report = audit(workspace)
    assert result.exit_code == 5
    assert report["errors"] == 1
    assert "Immutable artifact conflict" in next(
        row["error"] for row in report["entries"] if row["status"] == "error"
    )


def test_module_group_annotation_is_checked_against_independent_manifest(workspace):
    path = workspace / "benchmarks/train/discount_scope_samples.json"
    data = json.loads(path.read_bytes())
    data[0]["features"]["module_group"] = "inferred_from_bug_label"
    path.write_text(json.dumps(data), encoding="utf-8")
    result, report = audit(workspace)
    assert result.exit_code == 1
    row = next(row for row in report["entries"] if row["status"] == "mismatched")
    assert row["metadata_diff"]["module_group"] == {
        "expected": "inferred_from_bug_label",
        "actual": "retail",
    }
    assert report["module_context_digest"]
    snapshot = workspace / row["source_snapshots"]["target"]
    assert snapshot.exists()
    history = (
        workspace / "artifacts/audits/history" / f"{report['artifact_digest'].split(':')[1]}.json"
    )
    assert history.read_bytes() == (workspace / OUTPUT).read_bytes()
    # Re-running after an annotation change preserves the original dispute.
    data[0]["features"]["module_group"] = "retail"
    path.write_text(json.dumps(data), encoding="utf-8")
    repeated, _ = audit(workspace)
    assert repeated.exit_code == 0
    assert history.exists()


def test_context_corruption_retains_error_report(workspace):
    path = workspace / "benchmarks/context/scope_v1.json"
    data = json.loads(path.read_bytes())
    data["owner"] = "changed"
    path.write_text(json.dumps(data), encoding="utf-8")
    result, report = audit(workspace)
    assert result.exit_code == 5
    assert report["errors"] == 1


def test_historical_feature_record_keeps_original_digest_shape():
    path = PROJECT_ROOT / "docs/results/scope-v1/feature-parity.json"
    historic = json.loads(path.read_bytes())
    row = historic["entries"][0]
    # Build the v1 shape from recorded sources without adding context fields.
    payload = {
        "schema_version": "feature-extraction.v1",
        "extractor_version": historic["extractor_version"],
        "vocabulary_digest": historic["vocabulary_digest"],
        "target": {
            "module": "examples.discount.implementations.discount_amount_v1_alternate_correct",
            "symbol": "calculate_discount",
            "source_ref": "examples/discount/implementations/"
            "discount_amount_v1_alternate_correct.py",
        },
        "target_digest": "sha256:" + "a" * 64,
        "contract_ref": "examples/discount/contracts/membership_discount_amount_v1.json",
        "contract_digest": "sha256:" + "b" * 64,
        "features": row["actual"],
    }
    payload["artifact_digest"] = digest_json_artifact(payload)
    record = FeatureRecord.model_validate_json(json.dumps(payload))
    assert record.model_dump(mode="json") == payload
    assert digest_json_artifact(record) == payload["artifact_digest"]
