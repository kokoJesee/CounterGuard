"""Public artifact verification must reconstruct claims from raw execution evidence."""

import shutil
import subprocess
from pathlib import Path

import pytest

from evidenceguard.compiler import CompileRequest, compile_guard, verify_guard
from evidenceguard.digests import canonical_json_bytes, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.evidence import CaptureRequest, capture_evidence, verify_evidence

ROOT = Path(__file__).resolve().parents[2]
GUARD = "grd_integrity_v1"
CASES = ("member-price", "member-rounding", "negative-amount", "non-member-price")


@pytest.fixture
def captured(tmp_path, monkeypatch):
    shutil.copytree(
        ROOT / "examples", tmp_path / "examples", ignore=shutil.ignore_patterns("__pycache__")
    )
    test = tmp_path / "test_contract.py"
    test.write_bytes(b"# Controlled external pytest response in this unit fixture\n")

    def completed(argv, **kwargs):
        selected = CASES[:2] if argv[3].endswith("test_guard.py") else CASES
        buggy = kwargs["env"]["EVIDENCEGUARD_TARGET"].endswith("_buggy")
        nodes = []
        for name in selected:
            body = '<failure message="assertion failed" />' if buggy and name in CASES[:2] else ""
            nodes.append(f'<testcase name="test_contract[{name}]" time="0">{body}</testcase>')
        junit = tmp_path / argv[argv.index("--junitxml") + 1]
        junit.write_text("<testsuite>" + "".join(nodes) + "</testsuite>", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 1 if buggy else 0, b"stdout", b"stderr")

    monkeypatch.setattr(subprocess, "run", completed)
    result = capture_evidence(
        CaptureRequest(
            "evd_integrity_v1",
            Path("examples/discount/contracts/membership_discount_final_price_v1.json"),
            Path("test_contract.py"),
            "examples.discount.implementations.final_price_v1_buggy:calculate_price",
            "examples.discount.implementations.final_price_v1_fixed:calculate_price",
            tmp_path,
            Path("artifacts"),
        )
    )
    return tmp_path, result


def resign(path, payload):
    payload["artifact_digest"] = digest_json_artifact(payload)
    path.write_bytes(canonical_json_bytes(payload))


def test_resigned_evidence_cannot_invent_a_different_failed_case_set(captured):
    root, evidence = captured
    path = root / "artifacts/evidence/evd_integrity_v1/evidence.json"
    payload = evidence.model_dump(mode="json")
    payload["buggy_run"]["case_results"][0]["outcome"] = "passed"
    payload["failing_case_ids"] = ["member-rounding"]
    resign(path, payload)
    with pytest.raises(ArtifactIntegrityError, match="JUnit|execution"):
        verify_evidence(path, cwd=root)


def test_guard_self_check_must_agree_with_raw_junit(captured):
    root, _ = captured
    guard = compile_guard(
        CompileRequest(
            GUARD,
            Path("artifacts/evidence/evd_integrity_v1/evidence.json"),
            root,
            Path("artifacts"),
        )
    )
    path = root / f"artifacts/guards/{GUARD}/guard.json"
    payload = guard.model_dump(mode="json")
    payload["validation_run"]["case_results"][0]["duration_ms"] = 123
    resign(path, payload)
    with pytest.raises(ArtifactIntegrityError, match="JUnit|execution"):
        verify_guard(path, cwd=root)


@pytest.mark.parametrize("log", ["stdout", "stderr", "junit"])
def test_raw_log_tampering_cannot_be_hidden_by_resigning_evidence(captured, log):
    root, evidence = captured
    ref = getattr(evidence.buggy_run, log + "_ref")
    path = root / ref
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ArtifactIntegrityError, match="digest mismatch"):
        verify_evidence(root / "artifacts/evidence/evd_integrity_v1/evidence.json", cwd=root)


def test_resigned_contract_identity_must_still_match_the_actual_contract(captured):
    root, evidence = captured
    path = root / "artifacts/evidence/evd_integrity_v1/evidence.json"
    payload = evidence.model_dump(mode="json")
    for record in (payload, payload["buggy_run"], payload["fixed_run"]):
        record["contract_id"] = "invented-but-internally-consistent-contract"
    resign(path, payload)
    with pytest.raises(ArtifactIntegrityError, match="contract identity"):
        verify_evidence(path, cwd=root)


@pytest.mark.parametrize("role", ["buggy", "fixed"])
def test_evidence_target_identity_must_resolve_to_its_declared_source(captured, role):
    root, evidence = captured
    path = root / "artifacts/evidence/evd_integrity_v1/evidence.json"
    payload = evidence.model_dump(mode="json")
    payload[role + "_target"]["module"] = "examples.invented_target"
    payload[role + "_run"]["target"]["module"] = "examples.invented_target"
    resign(path, payload)
    with pytest.raises(ArtifactIntegrityError, match="target"):
        verify_evidence(path, cwd=root)
