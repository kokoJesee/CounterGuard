"""Tests for frozen runtime evidence models and digest helpers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from evidenceguard.digests import (
    canonical_json_bytes,
    digest_bytes,
    digest_file,
    digest_json_artifact,
)
from evidenceguard.models import (
    CaseOutcome,
    CaseResult,
    Evidence,
    RunOutcome,
    RunRecord,
    RunRole,
    TargetRef,
)

SHA_A = f"sha256:{'a' * 64}"
SHA_B = f"sha256:{'b' * 64}"
SHA_C = f"sha256:{'c' * 64}"
NOW = datetime(2026, 10, 13, 12, tzinfo=UTC)


def case(case_id: str, outcome: CaseOutcome) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        node_id=f"tests/contract.py::test_contract[{case_id}]",
        outcome=outcome,
        duration_ms=1,
    )


def run(
    role: RunRole,
    outcome: RunOutcome,
    case_results: tuple[CaseResult, ...],
) -> RunRecord:
    exit_codes = {
        RunOutcome.PASSED: 0,
        RunOutcome.TEST_FAILED: 1,
        RunOutcome.INTERRUPTED: 2,
        RunOutcome.PYTEST_INTERNAL_ERROR: 3,
        RunOutcome.PYTEST_USAGE_ERROR: 4,
        RunOutcome.NO_TESTS_COLLECTED: 5,
        RunOutcome.TIMEOUT: None,
        RunOutcome.LAUNCH_ERROR: None,
        RunOutcome.PROCESS_ERROR: 1,
    }
    return RunRecord(
        run_id=f"run_{role.value}",
        role=role,
        contract_id="membership-discount-final-price-v1",
        contract_digest=SHA_A,
        target=TargetRef(
            module=f"examples.{role.value}",
            symbol="final_price",
            source_ref=f"examples/{role.value}.py",
        ),
        target_digest=SHA_B if role is RunRole.BUGGY else SHA_C,
        argv=("python", "-m", "pytest", "tests/contract.py"),
        cwd=".",
        started_at=NOW,
        duration_ms=4,
        pytest_exit_code=exit_codes[outcome],
        outcome=outcome,
        case_results=case_results,
        stdout_ref=f"artifacts/runs/{role.value}/stdout.txt",
        stdout_digest=SHA_A,
        stderr_ref=f"artifacts/runs/{role.value}/stderr.txt",
        stderr_digest=SHA_A,
        junit_ref=f"artifacts/runs/{role.value}/junit.xml",
        junit_digest=SHA_A,
        python_version="3.13.7",
        pytest_version="8.4.2",
        error_detail=None
        if outcome in {RunOutcome.PASSED, RunOutcome.TEST_FAILED}
        else "pytest execution failed",
    )


def evidence_payload() -> dict[str, object]:
    buggy = run(
        RunRole.BUGGY,
        RunOutcome.TEST_FAILED,
        (case("member", CaseOutcome.FAILED), case("non_member", CaseOutcome.PASSED)),
    )
    fixed = run(
        RunRole.FIXED,
        RunOutcome.PASSED,
        (case("member", CaseOutcome.PASSED), case("non_member", CaseOutcome.PASSED)),
    )
    return {
        "evidence_id": "evd_membership_discount",
        "created_at": NOW,
        "contract_id": "membership-discount-final-price-v1",
        "contract_ref": "examples/contracts/membership_discount_final_price_v1.json",
        "contract_digest": SHA_A,
        "test_ref": "tests/contract_tests/test_membership_discount_v1.py",
        "test_digest": SHA_C,
        "buggy_target": buggy.target,
        "fixed_target": fixed.target,
        "buggy_target_digest": buggy.target_digest,
        "fixed_target_digest": fixed.target_digest,
        "buggy_run": buggy,
        "fixed_run": fixed,
        "failing_case_ids": ("member",),
        "reproduced": True,
        "rejection_reasons": (),
        "tool_version": "0.1.0",
        "artifact_digest": SHA_B,
    }


def test_digest_file_hashes_original_bytes(tmp_path: Path) -> None:
    path = tmp_path / "input.txt"
    data = b"line one\r\nline two\n\xff"
    path.write_bytes(data)

    assert digest_file(path) == f"sha256:{hashlib.sha256(data).hexdigest()}"
    assert digest_bytes(data) == digest_file(path)


def test_json_artifact_digest_is_canonical_and_ignores_self_digest() -> None:
    left = {"z": "中文", "nested": {"b": 2, "a": 1}, "artifact_digest": SHA_A}
    right = {"artifact_digest": SHA_B, "nested": {"a": 1, "b": 2}, "z": "中文"}

    assert canonical_json_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    assert digest_json_artifact(left) == digest_json_artifact(right)


@pytest.mark.parametrize(
    "digest",
    [
        "a" * 64,
        f"sha256:{'A' * 64}",
        f"sha1:{'a' * 64}",
        f"sha256:{'a' * 63}",
    ],
)
def test_digest_fields_reject_noncanonical_values(digest: str) -> None:
    payload = evidence_payload()
    payload["contract_digest"] = digest

    with pytest.raises(ValidationError):
        Evidence.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        "/absolute/test.py",
        "C:/absolute/test.py",
        "../outside/test.py",
        "tests/../outside/test.py",
        r"tests\contract.py",
        "tests//contract.py",
    ],
)
def test_artifact_refs_must_be_canonical_relative_posix_paths(path: str) -> None:
    payload = evidence_payload()
    payload["test_ref"] = path

    with pytest.raises(ValidationError):
        Evidence.model_validate(payload)


def test_evidence_is_frozen_and_forbids_unknown_fields() -> None:
    evidence = Evidence.model_validate(evidence_payload())

    with pytest.raises(ValidationError):
        evidence.reproduced = False

    payload = evidence_payload()
    payload["unknown"] = "value"
    with pytest.raises(ValidationError):
        Evidence.model_validate(payload)


def test_reproduced_evidence_requires_buggy_failure_and_fixed_pass() -> None:
    evidence = Evidence.model_validate(evidence_payload())

    assert evidence.failing_case_ids == ("member",)
    assert evidence.buggy_run.outcome is RunOutcome.TEST_FAILED
    assert evidence.fixed_run.outcome is RunOutcome.PASSED


def test_reproduced_flag_cannot_disagree_with_runs() -> None:
    payload = evidence_payload()
    payload["reproduced"] = False
    payload["rejection_reasons"] = ("not-reproduced",)

    with pytest.raises(ValidationError, match="reproduced must exactly reflect"):
        Evidence.model_validate(payload)


def test_failing_cases_must_exactly_match_buggy_failures_fixed_by_candidate() -> None:
    payload = evidence_payload()
    payload["failing_case_ids"] = ("non_member",)

    with pytest.raises(ValidationError, match="failing_case_ids must exactly reflect"):
        Evidence.model_validate(payload)


def test_run_contract_and_target_must_match_evidence() -> None:
    payload = evidence_payload()
    fixed_run = payload["fixed_run"]
    assert isinstance(fixed_run, RunRecord)
    payload["fixed_run"] = fixed_run.model_copy(update={"contract_digest": SHA_B})

    with pytest.raises(ValidationError, match="fixed_run contract"):
        Evidence.model_validate(payload)


@pytest.mark.parametrize(
    ("outcome", "exit_code"),
    [
        (RunOutcome.PASSED, 1),
        (RunOutcome.TEST_FAILED, 0),
        (RunOutcome.INTERRUPTED, 1),
        (RunOutcome.PYTEST_INTERNAL_ERROR, 1),
        (RunOutcome.PYTEST_USAGE_ERROR, 1),
        (RunOutcome.NO_TESTS_COLLECTED, 1),
        (RunOutcome.TIMEOUT, 1),
        (RunOutcome.LAUNCH_ERROR, 1),
    ],
)
def test_run_outcome_has_exact_pytest_exit_semantics(
    outcome: RunOutcome,
    exit_code: int,
) -> None:
    base = run(
        RunRole.BUGGY,
        RunOutcome.TEST_FAILED,
        (case("member", CaseOutcome.FAILED),),
    )

    with pytest.raises(ValidationError):
        RunRecord.model_validate(
            {
                **base.model_dump(),
                "outcome": outcome,
                "pytest_exit_code": exit_code,
                "error_detail": "failed" if outcome is not RunOutcome.PASSED else None,
            }
        )


def test_exit_one_without_a_mapped_failed_case_is_not_test_failure() -> None:
    base = run(
        RunRole.BUGGY,
        RunOutcome.TEST_FAILED,
        (case("member", CaseOutcome.FAILED),),
    )

    with pytest.raises(ValidationError, match="mapped failed case"):
        RunRecord.model_validate(
            {
                **base.model_dump(),
                "case_results": (case("member", CaseOutcome.PASSED),),
            }
        )


def test_process_error_can_represent_invalid_output_from_successful_pytest() -> None:
    base = run(
        RunRole.BUGGY,
        RunOutcome.TEST_FAILED,
        (case("member", CaseOutcome.FAILED),),
    )

    record = RunRecord.model_validate(
        {
            **base.model_dump(),
            "outcome": RunOutcome.PROCESS_ERROR,
            "pytest_exit_code": 0,
            "case_results": (),
            "error_detail": "JUnit report is missing",
        }
    )

    assert record.outcome is RunOutcome.PROCESS_ERROR


@pytest.mark.parametrize("exit_code", [None, 2, 3, 4, 5])
def test_process_error_does_not_hide_a_dedicated_pytest_outcome(
    exit_code: int | None,
) -> None:
    base = run(
        RunRole.BUGGY,
        RunOutcome.TEST_FAILED,
        (case("member", CaseOutcome.FAILED),),
    )

    with pytest.raises(ValidationError, match="process_error requires"):
        RunRecord.model_validate(
            {
                **base.model_dump(),
                "outcome": RunOutcome.PROCESS_ERROR,
                "pytest_exit_code": exit_code,
                "case_results": (),
                "error_detail": "untrusted process output",
            }
        )


def test_non_utc_timestamps_are_rejected() -> None:
    payload = evidence_payload()
    payload["created_at"] = datetime(2026, 10, 13, 20, tzinfo=timezone(timedelta(hours=8)))

    with pytest.raises(ValidationError, match="UTC"):
        Evidence.model_validate(payload)


def test_strict_evidence_round_trips_through_json() -> None:
    evidence = Evidence.model_validate(evidence_payload())
    assert Evidence.model_validate_json(evidence.model_dump_json()) == evidence


def test_fixed_pass_cannot_hide_a_skipped_case() -> None:
    with pytest.raises(ValidationError, match="all collected cases to pass"):
        run(RunRole.FIXED, RunOutcome.PASSED, (case("member", CaseOutcome.SKIPPED),))
