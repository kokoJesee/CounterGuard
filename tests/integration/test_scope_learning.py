"""The fit wrapper enforces provenance while the solver only receives safe projections."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.baselines import ScopePredicate, count_predictions, decide_scope
from counterguard.cli import app
from counterguard.errors import InsufficientScopeEvidence
from counterguard.scope import fit_scopes
from scripts.prepare_scope_v1 import prepare

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = "experiments/scope_v1.json"


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("scope-fit")
    for directory in ("examples", "benchmarks", "experiments", "tests/contract_tests"):
        shutil.copytree(
            ROOT / directory, workspace / directory, ignore=shutil.ignore_patterns("__pycache__")
        )
    prepare(workspace)
    return workspace


def test_initial_refined_fit_is_reproducible_and_has_no_holdout_members(prepared):
    manifests = {}
    for phase in ("initial", "refined"):
        output = f"artifacts/fitted/{phase}"
        result = CliRunner().invoke(
            app,
            [
                "scope",
                "learn",
                "--protocol",
                PROTOCOL,
                "--phase",
                phase,
                "--output",
                output,
                "--cwd",
                str(prepared),
            ],
        )
        assert result.exit_code == 0, result.output
        manifest = json.loads(result.stdout)
        manifests[phase] = manifest
        before = {path.name: path.read_bytes() for path in (prepared / output).glob("*.json")}
        repeated = fit_scopes(PROTOCOL, phase=phase, output=output, cwd=prepared)
        assert repeated.model_dump(mode="json") == manifest
        assert before == {
            path.name: path.read_bytes() for path in (prepared / output).glob("*.json")
        }
        assert "holdout-" not in json.dumps(manifest)
        assert all(ref.startswith("benchmarks/train/") for ref in manifest["train_file_digests"])
        assert sum(len(group["training_sample_ids"]) for group in manifest["groups"]) == (
            7 if phase == "initial" else 9
        )
        for group in manifest["groups"]:
            scope = ScopePredicate.model_validate_json((prepared / group["scope_ref"]).read_bytes())
            assert [clause.field for clause in scope.clauses] == (
                ["contract_version"]
                if phase == "initial"
                else ["contract_version", "interface_kind"]
            )
            assert scope.training_confusion.fp == scope.training_confusion.fn == 0
    samples = [
        sample
        for path in (prepared / "benchmarks/train").glob("*_scope_samples.json")
        for sample in json.loads(path.read_bytes())
    ]
    decisions = []
    for sample in samples:
        group = next(
            group
            for group in manifests["refined"]["groups"]
            if group["guard_id"] == sample["labels"]["guard_id"]
        )
        scope = ScopePredicate.model_validate_json((prepared / group["scope_ref"]).read_bytes())
        decision = decide_scope(scope, sample["features"])
        decisions.append((sample["labels"]["guard_applicable"], decision.decision))
    assert count_predictions(decisions).model_dump() == {"tp": 4, "fp": 0, "tn": 5, "fn": 0}


def test_failed_audit_blocks_fit_without_publishing_scopes(prepared, tmp_path, monkeypatch):
    import counterguard.scope as module

    real_audit = module.audit_features

    def failed_audit(**kwargs):
        report = real_audit(**kwargs)
        report["matched"] -= 1
        report["mismatched"] += 1
        return report

    monkeypatch.setattr(module, "audit_features", failed_audit)
    with pytest.raises(InsufficientScopeEvidence, match="audit must pass"):
        fit_scopes(PROTOCOL, phase="initial", output="artifacts/refused", cwd=prepared)
    assert not (prepared / "artifacts/refused").exists()


def test_holdout_fit_phase_is_rejected():
    result = CliRunner().invoke(
        app,
        [
            "scope",
            "learn",
            "--protocol",
            "missing.json",
            "--phase",
            "holdout",
            "--output",
            "artifacts/refused",
        ],
    )
    assert result.exit_code == 2


def test_holdout_id_injected_into_training_membership_is_refused(prepared, monkeypatch):
    import counterguard.scope as module

    real_verify = module.verify_protocol

    def contaminated_protocol(*args, **kwargs):
        protocol, manifest, guards = real_verify(*args, **kwargs)
        phases = dict(manifest.phases)
        guard_id = next(iter(phases))
        original = phases[guard_id]
        phases[guard_id] = original.model_copy(
            update={"initial": original.initial + original.holdout[:1]}
        )
        return protocol, manifest.model_copy(update={"phases": phases}), guards

    monkeypatch.setattr(module, "verify_protocol", contaminated_protocol)
    with pytest.raises(InsufficientScopeEvidence) as error:
        fit_scopes(PROTOCOL, phase="initial", output="artifacts/contaminated", cwd=prepared)
    assert error.value.reason_code == "holdout_leakage"
    assert not (prepared / "artifacts/contaminated").exists()


def test_missing_source_pair_and_legal_counterexample_are_refused(prepared, monkeypatch):
    import counterguard.scope as module

    real_reader = module._read_samples

    def altered_samples(path):
        samples = real_reader(path)
        return [
            sample.model_copy(
                update={"target": sample.target.model_copy(update={"module": "examples.unrelated"})}
            )
            if sample.labels.guard_applicable
            else sample
            for sample in samples
        ]

    monkeypatch.setattr(module, "_read_samples", altered_samples)
    with pytest.raises(InsufficientScopeEvidence) as error:
        fit_scopes(PROTOCOL, phase="initial", output="artifacts/missing-source", cwd=prepared)
    assert error.value.reason_code == "missing_source_pair"

    def no_legal_samples(path):
        return [
            sample.model_copy(
                update={"labels": sample.labels.model_copy(update={"contract_compliant": False})}
            )
            if not sample.labels.guard_applicable
            else sample
            for sample in real_reader(path)
        ]

    monkeypatch.setattr(module, "_read_samples", no_legal_samples)
    with pytest.raises(InsufficientScopeEvidence) as error:
        fit_scopes(PROTOCOL, phase="initial", output="artifacts/no-legal", cwd=prepared)
    assert error.value.reason_code == "no_legal_counterexample"
