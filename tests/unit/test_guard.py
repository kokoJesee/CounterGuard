"""Minimal Guard data and its fixed-target validation form one strict contract."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from evidenceguard.models import (
    CaseOutcome,
    Guard,
    RaisesGuardCase,
    RunOutcome,
    RunRole,
    ValueGuardCase,
)
from tests.unit.test_models import SHA_A, SHA_C, case, run


def guard_payload() -> dict:
    return {
        "guard_id": "grd_price_regression",
        "created_at": datetime.now(UTC),
        "source_evidence_id": "evd_price_fix",
        "source_evidence_ref": "artifacts/evidence/evd_price_fix/evidence.json",
        "source_evidence_digest": SHA_A,
        "contract_id": "membership-discount-final-price-v1",
        "contract_digest": SHA_A,
        "target_interface": {
            "contract_family": "membership_discount",
            "contract_version": "v1",
            "interface_kind": "final_price",
            "symbol_signature": "decimal_bool_to_decimal",
        },
        "argument_types": {"amount": "decimal", "is_member": "boolean"},
        "return_type": "decimal",
        "cases": (
            ValueGuardCase(
                case_id="member", args={"amount": "100", "is_member": True}, expected="80"
            ),
        ),
        "test_ref": "artifacts/guards/grd_price_regression/test_guard.py",
        "test_digest": SHA_A,
        "source_buggy_digest": SHA_A,
        "source_fixed_digest": SHA_C,
        "validation_run": run(
            RunRole.REPLAY, RunOutcome.PASSED, (case("member", CaseOutcome.PASSED),)
        ),
        "artifact_digest": SHA_A,
    }


def test_guard_json_round_trip() -> None:
    guard = Guard.model_validate(guard_payload())
    assert Guard.model_validate_json(guard.model_dump_json()) == guard


@pytest.mark.parametrize(
    "change",
    [
        {"cases": ()},
        {"source_fixed_digest": SHA_A},
        {"contract_id": "wrong-contract"},
        {"guard_id": "membership-discount-final-price-v1"},
        {"unexpected": True},
    ],
)
def test_guard_rejects_empty_invalid_or_mismatched_records(change: dict) -> None:
    with pytest.raises(ValidationError):
        Guard.model_validate({**guard_payload(), **change})


def test_guard_rejects_failed_self_check() -> None:
    payload = guard_payload()
    payload["validation_run"] = run(
        RunRole.REPLAY, RunOutcome.TEST_FAILED, (case("member", CaseOutcome.FAILED),)
    )
    with pytest.raises(ValidationError, match="successful fixed-target self-check"):
        Guard.model_validate(payload)


def test_guard_rejects_wrong_case_set_in_self_check() -> None:
    payload = guard_payload()
    payload["validation_run"] = run(
        RunRole.REPLAY, RunOutcome.PASSED, (case("other", CaseOutcome.PASSED),)
    )
    with pytest.raises(ValidationError, match="exactly its minimal case set"):
        Guard.model_validate(payload)


def test_case_oracle_is_exactly_one_of_expected_or_raises() -> None:
    with pytest.raises(ValidationError):
        RaisesGuardCase(case_id="negative", args={}, raises="ValueError", expected="anything")
    with pytest.raises(ValidationError):
        ValueGuardCase(case_id="missing", args={})
    with pytest.raises(ValidationError):
        RaisesGuardCase(case_id="unknown", args={}, raises="SystemExit")
