"""Integration coverage for bidirectional Evidence capture and storage."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evidenceguard.cli import app
from evidenceguard.digests import canonical_json_bytes, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.evidence import (
    CaptureRequest,
    capture_evidence,
    inventory_evidence,
    load_evidence,
    verify_evidence,
)
from evidenceguard.models import RunOutcome

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    files = (
        "examples/__init__.py",
        "examples/discount/__init__.py",
        "examples/discount/contracts/membership_discount_final_price_v1.json",
        "examples/discount/implementations/__init__.py",
        "examples/discount/implementations/final_price_v1_buggy.py",
        "examples/discount/implementations/final_price_v1_fixed.py",
        "examples/validation/__init__.py",
        "examples/validation/contracts/input_limit_query_v1.json",
        "examples/validation/implementations/__init__.py",
        "examples/validation/implementations/query_limit_v1_buggy.py",
        "examples/validation/implementations/query_limit_v1_fixed.py",
        "tests/contract_tests/test_membership_discount_v1.py",
        "tests/contract_tests/test_query_limit_v1.py",
    )
    for relative in files:
        source = PROJECT_ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return tmp_path


def _discount_request(
    workspace: Path,
    *,
    evidence_id: str = "evd_discount_v1_member_rate_fix",
    buggy_target: str = ("examples.discount.implementations.final_price_v1_buggy:calculate_price"),
) -> CaptureRequest:
    return CaptureRequest(
        evidence_id=evidence_id,
        contract_path=Path("examples/discount/contracts/membership_discount_final_price_v1.json"),
        test_path=Path("tests/contract_tests/test_membership_discount_v1.py"),
        buggy_target=buggy_target,
        fixed_target="examples.discount.implementations.final_price_v1_fixed:calculate_price",
        cwd=workspace,
        artifact_root=Path("artifacts"),
        tool_version="test-version",
    )


def _query_request(workspace: Path) -> CaptureRequest:
    return CaptureRequest(
        evidence_id="evd_query_limit_v1_zero_fix",
        contract_path=Path("examples/validation/contracts/input_limit_query_v1.json"),
        test_path=Path("tests/contract_tests/test_query_limit_v1.py"),
        buggy_target="examples.validation.implementations.query_limit_v1_buggy:parse_limit",
        fixed_target="examples.validation.implementations.query_limit_v1_fixed:parse_limit",
        cwd=workspace,
        artifact_root=Path("artifacts"),
        tool_version="test-version",
    )


@pytest.mark.parametrize(
    ("request_factory", "expected_failures"),
    [
        (_discount_request, ("member-price", "member-rounding")),
        (_query_request, ("below-minimum",)),
    ],
)
def test_captures_real_buggy_and_fixed_fixtures(
    workspace: Path,
    request_factory: object,
    expected_failures: tuple[str, ...],
) -> None:
    request = request_factory(workspace)  # type: ignore[operator]

    evidence = capture_evidence(request)

    assert evidence.reproduced is True
    assert evidence.failing_case_ids == expected_failures
    assert evidence.buggy_run.outcome is RunOutcome.TEST_FAILED
    assert evidence.fixed_run.outcome is RunOutcome.PASSED
    evidence_path = workspace / "artifacts" / "evidence" / request.evidence_id / "evidence.json"
    assert verify_evidence(evidence_path, cwd=workspace) == evidence
    assert evidence_path.read_bytes().startswith(b'{"artifact_digest":"sha256:')


def test_unreproduced_capture_is_saved_with_machine_reasons(workspace: Path) -> None:
    request = _discount_request(
        workspace,
        evidence_id="evd_discount_no_reproduction",
        buggy_target="examples.discount.implementations.final_price_v1_fixed:calculate_price",
    )

    evidence = capture_evidence(request)

    assert evidence.reproduced is False
    assert evidence.failing_case_ids == ()
    assert evidence.rejection_reasons == (
        "buggy-outcome:passed",
        "no-buggy-failure-fixed-by-candidate",
    )


def test_execution_error_cannot_become_reproduced_evidence(workspace: Path) -> None:
    test_path = workspace / "tests/contract_tests/test_membership_discount_v1.py"
    test_path.write_text("def this_is_not_valid_python(:\n", encoding="utf-8")

    evidence = capture_evidence(
        _discount_request(workspace, evidence_id="evd_discount_collection_error")
    )

    assert evidence.reproduced is False
    assert evidence.failing_case_ids == ()
    assert evidence.buggy_run.outcome is not RunOutcome.TEST_FAILED
    assert evidence.fixed_run.outcome is not RunOutcome.PASSED
    assert any(reason.startswith("buggy-outcome:") for reason in evidence.rejection_reasons)
    assert any(reason.startswith("fixed-outcome:") for reason in evidence.rejection_reasons)


def test_import_error_inside_test_body_is_an_execution_error(workspace: Path) -> None:
    source = workspace / "examples/discount/implementations/final_price_v1_buggy.py"
    source.write_text(
        "import evidenceguard_missing_dependency_for_test\n" + source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    evidence = capture_evidence(_discount_request(workspace))
    assert not evidence.reproduced
    assert evidence.buggy_run.pytest_exit_code == 1
    assert evidence.buggy_run.outcome is RunOutcome.PROCESS_ERROR
    assert evidence.fixed_run.outcome is RunOutcome.PASSED


def test_load_and_verify_reject_digest_tampering(workspace: Path) -> None:
    request = _discount_request(workspace)
    evidence = capture_evidence(request)
    evidence_path = workspace / "artifacts" / "evidence" / request.evidence_id / "evidence.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["tool_version"] = "tampered"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError, match="artifact digest mismatch"):
        load_evidence(evidence_path)

    evidence_path.write_bytes(
        json.dumps(
            evidence.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    source_path = workspace / evidence.buggy_target.source_ref
    source_path.write_text(source_path.read_text(encoding="utf-8") + "\n# tampered\n")
    with pytest.raises(ArtifactIntegrityError, match="buggy target digest mismatch"):
        verify_evidence(evidence_path, cwd=workspace)


def test_capture_is_idempotent_and_rejects_same_id_with_different_inputs(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _discount_request(workspace)
    first = capture_evidence(request)

    def unexpected_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("an idempotent capture must not rerun pytest")

    monkeypatch.setattr("evidenceguard.evidence.run_pytest", unexpected_run)
    assert capture_evidence(request) == first

    conflicting = _discount_request(
        workspace,
        buggy_target="examples.discount.implementations.final_price_v1_fixed:calculate_price",
    )
    with pytest.raises(ArtifactIntegrityError, match="different immutable inputs"):
        capture_evidence(conflicting)


def test_contract_loader_rejects_duplicate_unstable_case_ids(workspace: Path) -> None:
    contract_path = (
        workspace / "examples/discount/contracts/membership_discount_final_price_v1.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["cases"][0]["case_id"] = "case-1"
    contract["cases"][1]["case_id"] = "case-1"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(ValueError, match="unstable positional ID"):
        capture_evidence(_discount_request(workspace, evidence_id="evd_bad_contract"))


def test_capture_uses_the_selected_contract_oracle(workspace: Path) -> None:
    request = _discount_request(workspace)
    original = workspace / request.contract_path
    changed = json.loads(original.read_text(encoding="utf-8"))
    changed["cases"][0]["expected"] = "90.00"
    selected = original.with_name("changed_contract.json")
    selected.write_text(json.dumps(changed), encoding="utf-8")

    evidence = capture_evidence(replace(request, contract_path=selected))

    assert not evidence.reproduced
    assert evidence.fixed_run.outcome is RunOutcome.TEST_FAILED
    fixed_failures = [
        case.case_id for case in evidence.fixed_run.case_results if case.outcome == "failed"
    ]
    assert fixed_failures == ["member-price"]


def test_inputs_changed_during_capture_are_not_published(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _discount_request(workspace)
    from evidenceguard.evidence import run_pytest

    def mutate_after_run(run_request: object) -> object:
        result = run_pytest(run_request)  # type: ignore[arg-type]
        source = workspace / "examples/discount/implementations/final_price_v1_buggy.py"
        source.write_bytes(source.read_bytes() + b"\n# changed during capture\n")
        return result

    monkeypatch.setattr("evidenceguard.evidence.run_pytest", mutate_after_run)
    with pytest.raises(ArtifactIntegrityError, match="changed during capture"):
        capture_evidence(request)
    assert not (workspace / "artifacts/evidence" / request.evidence_id / "evidence.json").exists()


@pytest.mark.parametrize("bad_type", [["decimal"], True, None])
def test_malformed_contract_types_are_input_errors(workspace: Path, bad_type: object) -> None:
    request = _discount_request(workspace)
    path = workspace / request.contract_path
    contract = json.loads(path.read_text(encoding="utf-8"))
    contract["argument_types"]["amount"] = bad_type
    path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported argument type"):
        capture_evidence(request)


def _cli_args(request: CaptureRequest) -> list[str]:
    return [
        "capture",
        "--evidence-id",
        request.evidence_id,
        "--contract",
        str(request.contract_path),
        "--test",
        str(request.test_path),
        "--buggy-target",
        request.buggy_target,
        "--fixed-target",
        request.fixed_target,
        "--cwd",
        str(request.cwd),
        "--artifact-root",
        str(request.artifact_root),
    ]


@pytest.mark.parametrize(
    "scenario, expected_exit", [("reproduced", 0), ("no-bug", 1), ("error", 3)]
)
def test_capture_cli_preserves_domain_and_execution_outcomes(
    workspace: Path,
    scenario: str,
    expected_exit: int,
) -> None:
    request = _discount_request(workspace)
    if scenario == "no-bug":
        request = replace(request, buggy_target=request.fixed_target)
    elif scenario == "error":
        (workspace / request.test_path).write_text("def invalid(:\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, _cli_args(request))
    assert result.exit_code == expected_exit, result.output
    payload = json.loads(result.stdout)
    assert payload["reproduced"] is (scenario == "reproduced")
    evidence_path = Path("artifacts/evidence") / request.evidence_id / "evidence.json"
    verified = runner.invoke(
        app, ["evidence", "verify", str(evidence_path), "--cwd", str(workspace)]
    )
    assert verified.exit_code == expected_exit, verified.output
    repeated = runner.invoke(app, _cli_args(request))
    assert repeated.stdout == result.stdout
    assert repeated.exit_code == expected_exit
    evidence_file = workspace / evidence_path
    altered = json.loads(evidence_file.read_text(encoding="utf-8"))
    altered["tool_version"] = "tampered"
    evidence_file.write_text(json.dumps(altered), encoding="utf-8")
    rejected = runner.invoke(
        app, ["evidence", "verify", str(evidence_path), "--cwd", str(workspace)]
    )
    assert rejected.exit_code == 5
    assert "digest mismatch" in rejected.stderr


def test_timeout_change_cannot_reuse_existing_capture(workspace: Path) -> None:
    request = _discount_request(workspace)
    capture_evidence(request)
    with pytest.raises(ArtifactIntegrityError, match="different immutable inputs"):
        capture_evidence(replace(request, timeout_seconds=5.0))


def test_recapture_links_a_stale_predecessor_without_admitting_it(workspace: Path) -> None:
    request = _discount_request(workspace, evidence_id="evd_discount_v1")
    first = capture_evidence(request)
    first_path = Path("artifacts/evidence") / first.evidence_id / "evidence.json"
    test_path = workspace / request.test_path
    test_path.write_bytes(test_path.read_bytes() + b"\n# revised test harness\n")
    second = capture_evidence(
        replace(
            request,
            evidence_id="evd_discount_v2",
            supersedes_path=first_path,
            recapture_reason="Test harness revised; recapture with current source digests.",
        )
    )
    assert second.capture_revision == 2
    assert second.supersedes.evidence_id == first.evidence_id
    assert second.supersedes.artifact_digest == first.artifact_digest
    assert (
        verify_evidence(Path("artifacts/evidence/evd_discount_v2/evidence.json"), cwd=workspace)
        == second
    )
    report = inventory_evidence(cwd=workspace, artifact_root="artifacts")
    assert report["counts"] == {
        "total": 2,
        "verified": 1,
        "invalid": 1,
        "diagnostic": 0,
        "eligible": 1,
    }
    assert report["entries"][0]["usable"] is False


def test_verified_supersession_is_separate_from_validity(workspace: Path) -> None:
    request = _discount_request(workspace, evidence_id="evd_discount_v1")
    capture_evidence(request)
    capture_evidence(
        replace(
            request,
            evidence_id="evd_discount_v2",
            supersedes_path=Path("artifacts/evidence/evd_discount_v1/evidence.json"),
            recapture_reason="Replace the capture with an explicit revision.",
        )
    )
    report = inventory_evidence(cwd=workspace, artifact_root="artifacts")
    assert report["counts"]["verified"] == 2
    assert report["counts"]["eligible"] == 1
    older = report["entries"][0]
    assert older["usable"] is True and older["eligible"] is False
    assert older["superseded_by"] == ["evd_discount_v2"]


def test_capture_rejects_calendar_names_and_revision_without_reason(workspace: Path) -> None:
    request = _discount_request(workspace, evidence_id="evd_discount_d5")
    with pytest.raises(ValueError, match="Calendar-suffixed"):
        capture_evidence(request)
    request = replace(request, evidence_id="evd_discount_v1")
    capture_evidence(request)
    with pytest.raises(ValueError, match="explicit reason"):
        capture_evidence(
            replace(
                request,
                evidence_id="evd_discount_v2",
                supersedes_path=Path("artifacts/evidence/evd_discount_v1/evidence.json"),
            )
        )


def test_diagnostic_successor_does_not_retire_verified_predecessor(workspace: Path) -> None:
    request = _discount_request(workspace, evidence_id="evd_discount_v1")
    capture_evidence(request)
    capture_evidence(
        replace(
            request,
            evidence_id="evd_discount_v2",
            buggy_target=request.fixed_target,
            supersedes_path=Path("artifacts/evidence/evd_discount_v1/evidence.json"),
            recapture_reason="Attempted recapture without a reproduced bug.",
        )
    )
    report = inventory_evidence(cwd=workspace, artifact_root="artifacts")
    assert report["counts"]["diagnostic"] == 1
    assert report["counts"]["eligible"] == 1
    assert report["entries"][0]["eligible"] is True
    assert report["entries"][0]["superseded_by"] == []


def test_tampered_predecessor_invalidates_revision_chain(workspace: Path) -> None:
    request = _discount_request(workspace, evidence_id="evd_discount_v1")
    capture_evidence(request)
    predecessor = Path("artifacts/evidence/evd_discount_v1/evidence.json")
    capture_evidence(
        replace(
            request,
            evidence_id="evd_discount_v2",
            supersedes_path=predecessor,
            recapture_reason="Record explicit revision provenance.",
        )
    )
    path = workspace / predecessor
    payload = json.loads(path.read_bytes())
    payload["tool_version"] = "altered"
    payload["artifact_digest"] = digest_json_artifact(payload)
    path.write_bytes(canonical_json_bytes(payload))
    report = inventory_evidence(cwd=workspace, artifact_root="artifacts")
    assert report["entries"][1]["usable"] is False
    assert "predecessor identity/digest mismatch" in report["entries"][1]["reason"]
