"""Actual B/F Docker capture, independently verified from Git and raw JUnit."""

import importlib
import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.registry import Registry
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.standalone_capture import (
    capture_standalone,
    standalone_capture_exit_code,
    verify_standalone_evidence,
)
from counterguard.standalone_guard import compile_standalone_guard, verify_standalone_guard
from counterguard.target_inspection import inspect_static_target
from tests.standalone_support import standalone_history

pytestmark = [pytest.mark.slow, pytest.mark.docker]


@pytest.mark.parametrize(
    "reexport,export_v2",
    [(False, False), (True, False), (True, True)],
    ids=["direct", "root-reexport", "static-reexport-v2"],
)
def test_real_docker_message_only_regression_preserves_minimal_oracle_and_registry(
    tmp_path, monkeypatch, runner_and_no_local_execution, reexport, export_v2
):
    monkeypatch.chdir(tmp_path)
    repo = standalone_history(
        tmp_path,
        import_root="src" if reexport else ".",
        message_match=True,
        reexport=reexport,
        export_v2=export_v2,
    )
    if reexport:
        binding = json.loads(Path("bind/binding.json").read_bytes())
        assert binding["schema_version"] == (
            "bootstrap-binding.v4" if export_v2 else "bootstrap-binding.v3"
        )
        assert binding["contract"]["schema_version"] == (
            "contract.v6" if export_v2 else "contract.v5"
        )
        assert binding["contract"]["target_module"] == "sample"
        if export_v2:
            for role in ("buggy", "fixed", "head"):
                assessment = binding["runtime_assessments"][role]
                assert len(assessment["files"]) == 4
                assert assessment["hook_observations"][0]["recognition"] == "finite_raise"
            inspection = inspect_static_target(
                repo,
                binding["head_commit"],
                target="sample:price",
                import_root="src",
                profile="static-reexport-v2",
                output=Path("comparison-inspection"),
            )
            assert inspection["runtime_assessment"]["status"] == "review_required"
            assert not inspection["execution_allowed"]
    evidence = capture_standalone(
        repo,
        Path("bind/binding.json"),
        runner_id="root-pytest8",
        evidence_id="evd_literal_message_v1",
        review_reason="tool-owned message-only regression",
        output=Path("matched-capture"),
    )
    assert evidence["reproduced"] and len(evidence["failing_case_ids"]) == 1
    assert evidence["buggy"]["run"]["pytest_exit_code"] == 1
    assert evidence["fixed"]["run"]["pytest_exit_code"] == 0
    assert verify_standalone_evidence(repo, Path("matched-capture/evidence.json")).reproduced
    assert (
        json.loads(Path("matched-capture/capture.json").read_bytes())["generator_version"]
        == "standalone-test.v2"
    )
    guard = compile_standalone_guard(
        repo,
        Path("matched-capture/evidence.json"),
        guard_id="grd_literal_message_v1",
        review_reason="retain only the actually failing message oracle",
        output=Path("matched-guard"),
    )
    assert guard.schema_version == "guard.v4"
    assert guard.generator_version == "standalone-guard-test.v2"
    assert guard.case_ids == tuple(evidence["failing_case_ids"])
    if reexport:
        assert (
            b"MODULE = 'sample'\nSYMBOL = 'price'"
            in Path("matched-guard/test_guard.py").read_bytes()
        )
    assert b"exception_match" in Path("matched-guard/test_guard.py").read_bytes()
    assert verify_standalone_guard(repo, Path("matched-guard/guard.json")) == guard
    registry = Registry(tmp_path / "matched-registry")
    entry = registry.add(Path("matched-guard/guard.json"), cwd=tmp_path, repo=repo)
    assert entry.schema_version == "registry-entry.v4"
    assert registry.add(Path("matched-guard/guard.json"), cwd=tmp_path, repo=repo) == entry
    assert not registry.show(guard.guard_id)["verification_schedulable"]


@pytest.fixture
def runner_and_no_local_execution(monkeypatch):
    review = resolve_runner(runner_id="root-pytest8", image_digest=None)
    value = os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST")
    if not value:
        pytest.skip("set COUNTERGUARD_RUNNER_IMAGE_DIGEST to run the actual Docker capture")
    assert value == review.image_digest

    def forbidden_local(*args, **kwargs):
        pytest.fail("candidate code reached a local executor")

    monkeypatch.setattr(LocalTrustedExecutor, "execute", forbidden_local)
    original = importlib.import_module

    def guarded_import(name, *args, **kwargs):
        if name == "sample" or name.startswith("sample."):
            pytest.fail("candidate package was imported on the host")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", guarded_import)
    return review


@pytest.mark.parametrize("import_root", [".", "src"], ids=["root", "src"])
def test_real_docker_capture_and_reproducible_counts(
    tmp_path,
    monkeypatch,
    import_root,
    runner_and_no_local_execution,
):
    monkeypatch.chdir(tmp_path)
    repo = standalone_history(tmp_path, import_root=import_root)
    result = CliRunner().invoke(
        app,
        [
            "bootstrap",
            "capture",
            "--repo",
            str(repo),
            "--binding",
            "bind/binding.json",
            "--runner-id",
            "root-pytest8",
            "--evidence-id",
            "evd_live_v1",
            "--review-reason",
            "reviewed tool-owned target, independent oracles and excluded bootstrap",
            "--output",
            "c1",
        ],
    )
    assert result.exit_code == 0, result.output[-1500:]
    evidence = json.loads(result.stdout)
    assert evidence["reproduced"] and len(evidence["failing_case_ids"]) == 1
    assert evidence["buggy"]["run"]["pytest_exit_code"] == 1
    assert evidence["fixed"]["run"]["pytest_exit_code"] == 0
    assert len(evidence["buggy"]["run"]["case_results"]) == 2
    assert verify_standalone_evidence(repo, Path("c1/evidence.json")).reproduced
    for role in ("b", "f"):
        sandbox = next((tmp_path / "c1" / role / "r/runs").glob("*/sandbox-input"))
        files = sorted(
            path.relative_to(sandbox).as_posix() for path in sandbox.rglob("*") if path.is_file()
        )
        prefix = "" if import_root == "." else "src/"
        assert files == sorted(
            [
                "cg_control/contract.json",
                "cg_control/test_capture.py",
                prefix + "sample/__init__.py",
                prefix + "sample/core.py",
            ]
        )
    if import_root == ".":
        repeat = capture_standalone(
            repo,
            Path("bind/binding.json"),
            runner_id="root-pytest8",
            evidence_id="evd_live_v2",
            review_reason="repeat same audited commits",
            output=Path("c2"),
        )
        assert repeat["reproduced"] and repeat["failing_case_ids"] == evidence["failing_case_ids"]
        assert repeat["buggy"]["run"]["run_id"] != evidence["buggy"]["run"]["run_id"]
        assert [c["outcome"] for c in repeat["buggy"]["run"]["case_results"]] == [
            c["outcome"] for c in evidence["buggy"]["run"]["case_results"]
        ]
        assert verify_standalone_evidence(repo, Path("c2/evidence.json")).reproduced
    # Re-signing an actual evidence file cannot remove a known failed case.
    evidence["failing_case_ids"] = []
    evidence["artifact_digest"] = digest_json_artifact(evidence)
    Path("c1/evidence.json").write_bytes(canonical_json_bytes(evidence))
    with pytest.raises(ArtifactIntegrityError, match="claims_mismatch"):
        verify_standalone_evidence(repo, Path("c1/evidence.json"))


def test_actual_import_failure_is_retained_as_infrastructure_not_reproduced(
    tmp_path,
    monkeypatch,
    runner_and_no_local_execution,
):
    monkeypatch.chdir(tmp_path)
    repo = standalone_history(tmp_path, import_failure=True)
    evidence = capture_standalone(
        repo,
        Path("bind/binding.json"),
        runner_id="root-pytest8",
        evidence_id="evd_import_error",
        review_reason="test known fixture import failure classification",
        output=Path("c1"),
    )
    assert evidence["schema_version"] == "evidence.v4", evidence.get("reason_code")
    assert not evidence["reproduced"] and evidence["buggy"]["run"]["pytest_exit_code"] == 2
    assert evidence["fixed"]["run"]["pytest_exit_code"] == 0
    assert evidence["failing_case_ids"] == [] and standalone_capture_exit_code(evidence) == 3
    assert not verify_standalone_evidence(repo, Path("c1/evidence.json")).reproduced
