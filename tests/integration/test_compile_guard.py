"""Exercise the real Evidence -> minimal Guard -> direct replay chain."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.compiler import (
    CompileRequest,
    compile_guard,
    load_guard,
    run_guard,
    verify_guard,
)
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError, GuardSelfCheckError, InvalidEvidenceError
from counterguard.evidence import CaptureRequest, capture_evidence
from counterguard.models import RunOutcome

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KINDS = {
    "discount": {
        "guard_id": "grd_discount_member_rate_regression",
        "contract": "examples/discount/contracts/membership_discount_final_price_v1.json",
        "test": "tests/contract_tests/test_membership_discount_v1.py",
        "buggy": "examples.discount.implementations.final_price_v1_buggy:calculate_price",
        "fixed": "examples.discount.implementations.final_price_v1_fixed:calculate_price",
        "new": "examples.discount.implementations.final_price_v1_alternate_buggy:calculate_price",
        "new_outcome": RunOutcome.TEST_FAILED,
        "case_ids": ("member-price", "member-rounding"),
    },
    "query": {
        "guard_id": "grd_query_limit_zero_regression",
        "contract": "examples/validation/contracts/input_limit_query_v1.json",
        "test": "tests/contract_tests/test_query_limit_v1.py",
        "buggy": "examples.validation.implementations.query_limit_v1_buggy:parse_limit",
        "fixed": "examples.validation.implementations.query_limit_v1_fixed:parse_limit",
        "new": "examples.validation.implementations.query_limit_v1_alternate_correct:parse_limit",
        "new_outcome": RunOutcome.PASSED,
        "case_ids": ("below-minimum",),
    },
}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    shutil.copytree(
        PROJECT_ROOT / "examples",
        tmp_path / "examples",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copytree(
        PROJECT_ROOT / "tests/contract_tests",
        tmp_path / "tests/contract_tests",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return tmp_path


def capture_request(workspace: Path, kind: str = "discount") -> CaptureRequest:
    spec = KINDS[kind]
    return CaptureRequest(
        evidence_id=f"evd_{kind}_fix",
        contract_path=Path(spec["contract"]),
        test_path=Path(spec["test"]),
        buggy_target=spec["buggy"],
        fixed_target=spec["fixed"],
        cwd=workspace,
        artifact_root=Path("artifacts"),
    )


def compile_request(workspace: Path, kind: str = "discount") -> CompileRequest:
    return CompileRequest(
        guard_id=KINDS[kind]["guard_id"],
        evidence_path=Path(f"artifacts/evidence/evd_{kind}_fix/evidence.json"),
        cwd=workspace,
        artifact_root=Path("artifacts"),
    )


def make_guard(workspace: Path, kind: str = "discount"):
    evidence = capture_evidence(capture_request(workspace, kind))
    guard = compile_guard(compile_request(workspace, kind))
    return evidence, guard, workspace / "artifacts/guards" / guard.guard_id / "guard.json"


@pytest.mark.parametrize("kind", KINDS)
def test_minimal_guard_is_verified_and_replays_on_new_target(workspace: Path, kind: str) -> None:
    evidence, guard, path = make_guard(workspace, kind)
    assert tuple(case.case_id for case in guard.cases) == KINDS[kind]["case_ids"]
    assert guard.source_evidence_id == evidence.evidence_id
    assert guard.guard_id != guard.contract_id
    assert guard.validation_run.outcome is RunOutcome.PASSED
    assert verify_guard(path, cwd=workspace) == guard
    assert run_guard(path, KINDS[kind]["buggy"], cwd=workspace).outcome is RunOutcome.TEST_FAILED
    assert run_guard(path, KINDS[kind]["fixed"], cwd=workspace).outcome is RunOutcome.PASSED
    assert run_guard(path, KINDS[kind]["new"], cwd=workspace).outcome is KINDS[kind]["new_outcome"]


def test_guard_is_portable_without_source_contract_or_evidence(workspace: Path) -> None:
    evidence, guard, path = make_guard(workspace)
    portable = workspace / "portable"
    shutil.copytree(workspace / "examples", portable / "examples")
    portable_guard = portable / guard.test_ref
    portable_guard.parent.mkdir(parents=True)
    shutil.copyfile(workspace / guard.test_ref, portable_guard)
    portable_json = portable_guard.parent / "guard.json"
    shutil.copyfile(path, portable_json)
    (portable / evidence.contract_ref).unlink()
    assert load_guard(portable_json, cwd=portable) == guard
    assert (
        run_guard(portable_json, KINDS["discount"]["fixed"], cwd=portable).outcome
        is RunOutcome.PASSED
    )
    with pytest.raises(ArtifactIntegrityError, match="does not exist"):
        verify_guard(portable_json, cwd=portable)


def test_compilation_is_idempotent_and_test_bytes_are_deterministic(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, first, path = make_guard(workspace)
    second = compile_guard(replace(compile_request(workspace), guard_id="grd_second_price_rule"))
    assert first.test_digest == second.test_digest
    assert (workspace / first.test_ref).read_bytes() == (workspace / second.test_ref).read_bytes()

    def unexpected_run(*args, **kwargs):
        raise AssertionError("idempotent compilation must not rerun pytest")

    monkeypatch.setattr("counterguard.compiler.run_pytest", unexpected_run)
    assert compile_guard(compile_request(workspace)) == first
    assert load_guard(path, cwd=workspace) == first


def test_compiler_rejects_unreproduced_evidence(workspace: Path) -> None:
    request = capture_request(workspace)
    capture_evidence(replace(request, buggy_target=request.fixed_target))
    with pytest.raises(InvalidEvidenceError, match="reproduced Evidence"):
        compile_guard(compile_request(workspace))
    assert not (workspace / "artifacts/guards").exists()


def test_compiler_rejects_corrupt_source_digest(workspace: Path) -> None:
    capture_evidence(capture_request(workspace))
    evidence_path = workspace / compile_request(workspace).evidence_path
    payload = json.loads(evidence_path.read_bytes())
    payload["tool_version"] = "corrupt"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError, match="digest mismatch"):
        compile_guard(compile_request(workspace))
    assert not (workspace / "artifacts/guards").exists()


def test_same_guard_id_cannot_change_source_evidence(workspace: Path) -> None:
    _, guard, path = make_guard(workspace)
    request = replace(capture_request(workspace), evidence_id="evd_second_capture")
    capture_evidence(request)
    conflicting = replace(
        compile_request(workspace),
        evidence_path=Path("artifacts/evidence/evd_second_capture/evidence.json"),
    )
    with pytest.raises(ArtifactIntegrityError, match="different source Evidence"):
        compile_guard(conflicting)
    assert load_guard(path, cwd=workspace) == guard


@pytest.mark.parametrize(
    "bad_test, outcome",
    [
        (
            b"import pytest\n"
            b"@pytest.mark.parametrize('case', [pytest.param(1, id='member-price'), "
            b"pytest.param(2, id='member-rounding')])\n"
            b"def test_bad(case):\n    assert False\n",
            RunOutcome.TEST_FAILED,
        ),
        (b"def invalid(:\n", RunOutcome.INTERRUPTED),
    ],
)
def test_no_guard_json_is_published_when_self_check_fails(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, bad_test: bytes, outcome: RunOutcome
) -> None:
    capture_evidence(capture_request(workspace))
    monkeypatch.setattr("counterguard.compiler._render_test", lambda payload: bad_test)
    with pytest.raises(GuardSelfCheckError) as caught:
        compile_guard(compile_request(workspace))
    assert caught.value.run.outcome is outcome
    assert not (
        workspace / "artifacts/guards" / KINDS["discount"]["guard_id"] / "guard.json"
    ).exists()


def test_guard_rejects_test_tampering_and_wrong_source_reference(workspace: Path) -> None:
    _, guard, path = make_guard(workspace)
    payload = guard.model_dump(mode="json")
    payload["source_evidence_digest"] = "sha256:" + "0" * 64
    payload["artifact_digest"] = digest_json_artifact(payload)
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="provenance mismatch"):
        verify_guard(path, cwd=workspace)
    path.write_bytes(canonical_json_bytes(guard))
    (workspace / guard.test_ref).write_bytes(b"def test_always_passes(): pass\n")
    with pytest.raises(ArtifactIntegrityError, match="test digest"):
        run_guard(path, KINDS["discount"]["fixed"], cwd=workspace)


def test_compiler_rejects_unknown_case_ids_even_with_rehashed_evidence(workspace: Path) -> None:
    evidence = capture_evidence(capture_request(workspace))
    payload = evidence.model_dump(mode="json")
    for name in ("buggy_run", "fixed_run"):
        for case in payload[name]["case_results"]:
            if case["case_id"] == "member-price":
                case["case_id"] = "unknown-case"
        payload[name]["case_results"].sort(key=lambda case: case["case_id"])
    payload["failing_case_ids"] = ["member-rounding", "unknown-case"]
    payload["artifact_digest"] = digest_json_artifact(payload)
    (workspace / compile_request(workspace).evidence_path).write_bytes(
        canonical_json_bytes(payload)
    )
    with pytest.raises(ArtifactIntegrityError, match="unknown contract case"):
        compile_guard(compile_request(workspace))


def test_cli_compile_audit_and_direct_replay(workspace: Path) -> None:
    capture_evidence(capture_request(workspace))
    request = compile_request(workspace)
    runner = CliRunner()
    compiled = runner.invoke(
        app,
        [
            "compile",
            "--guard-id",
            request.guard_id,
            "--evidence",
            str(request.evidence_path),
            "--cwd",
            str(workspace),
        ],
    )
    assert compiled.exit_code == 0, compiled.output
    payload = json.loads(compiled.stdout)
    path = Path(payload["test_ref"]).parent / "guard.json"
    audited = runner.invoke(app, ["guard", "verify", str(path), "--cwd", str(workspace)])
    assert audited.exit_code == 0, audited.output
    failed = runner.invoke(
        app,
        [
            "guard",
            "run",
            str(path),
            "--target",
            KINDS["discount"]["buggy"],
            "--cwd",
            str(workspace),
        ],
    )
    assert failed.exit_code == 1, failed.output
    assert json.loads(failed.stdout)["outcome"] == "test_failed"


def test_manual_guard_run_without_env_has_actionable_error(workspace: Path) -> None:
    _, guard, _ = make_guard(workspace)
    environment = os.environ.copy()
    environment.pop("COUNTERGUARD_TARGET", None)
    environment.pop("COUNTERGUARD_SYMBOL", None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", guard.test_ref, "--noconftest", "-q"],
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Missing Guard target" in result.stdout
    assert "--target module:symbol" in result.stdout
    assert "KeyError" not in result.stdout
