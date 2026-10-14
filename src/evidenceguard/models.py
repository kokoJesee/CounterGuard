"""Frozen data contracts for trusted EvidenceGuard execution evidence."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_serializer,
    model_validator,
)

from evidenceguard.contracts import ContractType, ExceptionName, convert_contract_value

Digest = Annotated[
    str,
    StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$", strict=True),
]
NonEmptyText = Annotated[str, StringConstraints(min_length=1, strict=True)]

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def _relative_posix_path(value: str, *, allow_dot: bool) -> str:
    if "\\" in value:
        raise ValueError("path must use POSIX separators")
    if _WINDOWS_DRIVE.match(value):
        raise ValueError("path must not include a Windows drive")

    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError("path must be relative")
    if ".." in path.parts:
        raise ValueError("path must not contain '..'")
    if not value or (value == "." and not allow_dot):
        raise ValueError("path must name a relative artifact")
    if str(path) != value:
        raise ValueError("path must be a canonical POSIX path")
    return value


def _artifact_ref(value: str) -> str:
    return _relative_posix_path(value, allow_dot=False)


def _working_directory(value: str) -> str:
    return _relative_posix_path(value, allow_dot=True)


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("datetime must be timezone-aware UTC")
    return value


ArtifactRef = Annotated[
    str,
    StringConstraints(min_length=1, strict=True),
    AfterValidator(_artifact_ref),
]
WorkingDirectory = Annotated[
    str,
    StringConstraints(min_length=1, strict=True),
    AfterValidator(_working_directory),
]
UtcDateTime = Annotated[datetime, AfterValidator(_utc_datetime)]


class FrozenModel(BaseModel):
    """Strict immutable base for persisted v1 data contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, validate_default=True)


class RunRole(StrEnum):
    """The purpose of a captured pytest execution."""

    BUGGY = "buggy"
    FIXED = "fixed"
    REPLAY = "replay"


class RunOutcome(StrEnum):
    """Normalized outcome of a pytest process."""

    PASSED = "passed"
    TEST_FAILED = "test_failed"
    INTERRUPTED = "interrupted"
    PYTEST_INTERNAL_ERROR = "pytest_internal_error"
    PYTEST_USAGE_ERROR = "pytest_usage_error"
    NO_TESTS_COLLECTED = "no_tests_collected"
    TIMEOUT = "timeout"
    LAUNCH_ERROR = "launch_error"
    PROCESS_ERROR = "process_error"


class CaseOutcome(StrEnum):
    """Normalized result for one stable contract case."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class TargetRef(FrozenModel):
    """A Python symbol and its repository-relative source file."""

    module: Annotated[
        str,
        StringConstraints(
            pattern=r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$",
            strict=True,
        ),
    ]
    symbol: Annotated[
        str,
        StringConstraints(
            pattern=r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$",
            strict=True,
        ),
    ]
    source_ref: ArtifactRef


class CaseResult(FrozenModel):
    """The result of one case, linked by its stable contract case ID."""

    case_id: NonEmptyText
    node_id: NonEmptyText
    outcome: CaseOutcome
    duration_ms: Annotated[int, Field(ge=0)] = 0
    message: str | None = None

    @model_validator(mode="after")
    def validate_message(self) -> Self:
        if self.outcome is CaseOutcome.ERROR and not self.message:
            raise ValueError("error case results require a message")
        return self


class RunRecord(FrozenModel):
    """Immutable, reproducible record of one pytest invocation."""

    schema_version: Literal["run-record.v1"] = "run-record.v1"
    run_id: Annotated[str, StringConstraints(pattern=r"^run_[A-Za-z0-9][A-Za-z0-9_-]*$")]
    role: RunRole
    contract_id: NonEmptyText
    contract_digest: Digest
    target: TargetRef
    target_digest: Digest
    argv: Annotated[tuple[NonEmptyText, ...], Field(min_length=1)]
    cwd: WorkingDirectory
    started_at: UtcDateTime
    duration_ms: Annotated[int, Field(ge=0)]
    timeout_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 30.0
    pytest_exit_code: int | None
    outcome: RunOutcome
    case_results: tuple[CaseResult, ...]
    stdout_ref: ArtifactRef
    stdout_digest: Digest
    stderr_ref: ArtifactRef
    stderr_digest: Digest
    junit_ref: ArtifactRef
    junit_digest: Digest
    python_version: NonEmptyText
    pytest_version: NonEmptyText
    error_detail: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        case_ids = [result.case_id for result in self.case_results]
        node_ids = [result.node_id for result in self.case_results]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_results must contain unique case_id values")
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("case_results must contain unique node_id values")
        if self.case_results != tuple(
            sorted(self.case_results, key=lambda result: (result.case_id, result.node_id))
        ):
            raise ValueError("case_results must be sorted by case_id and node_id")

        outcomes = {result.outcome for result in self.case_results}
        expected_exit_codes: dict[RunOutcome, int | None] = {
            RunOutcome.PASSED: 0,
            RunOutcome.TEST_FAILED: 1,
            RunOutcome.INTERRUPTED: 2,
            RunOutcome.PYTEST_INTERNAL_ERROR: 3,
            RunOutcome.PYTEST_USAGE_ERROR: 4,
            RunOutcome.NO_TESTS_COLLECTED: 5,
            RunOutcome.TIMEOUT: None,
            RunOutcome.LAUNCH_ERROR: None,
        }
        if self.outcome in expected_exit_codes:
            expected = expected_exit_codes[self.outcome]
            if self.pytest_exit_code != expected:
                raise ValueError(f"{self.outcome.value} requires pytest_exit_code={expected!r}")
        elif self.pytest_exit_code is None or self.pytest_exit_code in {2, 3, 4, 5}:
            raise ValueError("process_error requires exit code 0, 1, or an unrecognized exit code")

        if self.outcome is RunOutcome.PASSED:
            if outcomes != {CaseOutcome.PASSED}:
                raise ValueError("passed run requires all collected cases to pass")
        elif self.outcome is RunOutcome.TEST_FAILED:
            if CaseOutcome.FAILED not in outcomes:
                raise ValueError("test_failed run requires a mapped failed case")
            if outcomes - {CaseOutcome.PASSED, CaseOutcome.FAILED}:
                raise ValueError("test_failed run cannot contain errors or skipped cases")

        domain_outcomes = {RunOutcome.PASSED, RunOutcome.TEST_FAILED}
        if self.outcome in domain_outcomes and self.error_detail is not None:
            raise ValueError("passed and test_failed runs cannot contain error_detail")
        if self.outcome not in domain_outcomes and not self.error_detail:
            raise ValueError("infrastructure outcomes require error_detail")
        return self


class EvidenceLink(FrozenModel):
    evidence_id: NonEmptyText
    evidence_ref: ArtifactRef
    artifact_digest: Digest


class Evidence(FrozenModel):
    """A bidirectionally verified bug reproduction artifact."""

    schema_version: Literal["evidence.v1", "evidence.v2"] = "evidence.v2"
    evidence_id: Annotated[str, StringConstraints(pattern=r"^evd_[A-Za-z0-9][A-Za-z0-9_-]*$")]
    created_at: UtcDateTime
    contract_id: NonEmptyText
    contract_ref: ArtifactRef
    contract_digest: Digest
    test_ref: ArtifactRef
    test_digest: Digest
    buggy_target: TargetRef
    fixed_target: TargetRef
    buggy_target_digest: Digest
    fixed_target_digest: Digest
    buggy_run: RunRecord
    fixed_run: RunRecord
    failing_case_ids: tuple[NonEmptyText, ...]
    reproduced: bool
    rejection_reasons: tuple[NonEmptyText, ...] = ()
    tool_version: NonEmptyText
    artifact_digest: Digest
    capture_revision: Annotated[int, Field(ge=1)] = 1
    supersedes: EvidenceLink | None = None
    recapture_reason: NonEmptyText | None = None

    @model_serializer(mode="wrap")
    def serialize_legacy_shape(self, handler):
        payload = handler(self)
        if self.schema_version == "evidence.v1":
            for key in ("capture_revision", "supersedes", "recapture_reason"):
                payload.pop(key, None)
        return payload

    @model_validator(mode="after")
    def validate_reproduction(self) -> Self:
        revision_fields = {"capture_revision", "supersedes", "recapture_reason"}
        if self.schema_version == "evidence.v1" and revision_fields & self.model_fields_set:
            raise ValueError("Legacy Evidence cannot declare v2 revision fields")
        if (self.supersedes is None) != (self.recapture_reason is None):
            raise ValueError("supersedes and recapture_reason must be provided together")
        if self.supersedes is None and self.capture_revision != 1:
            raise ValueError("A recapture revision requires a predecessor")
        if self.supersedes is not None and (
            self.supersedes.evidence_id == self.evidence_id or self.capture_revision < 2
        ):
            raise ValueError("A recapture must use a distinct ID and advance its revision")
        if self.buggy_run.role is not RunRole.BUGGY:
            raise ValueError("buggy_run must have role=buggy")
        if self.fixed_run.role is not RunRole.FIXED:
            raise ValueError("fixed_run must have role=fixed")

        for label, run, target, target_digest in (
            ("buggy", self.buggy_run, self.buggy_target, self.buggy_target_digest),
            ("fixed", self.fixed_run, self.fixed_target, self.fixed_target_digest),
        ):
            if run.contract_id != self.contract_id or run.contract_digest != self.contract_digest:
                raise ValueError(f"{label}_run contract does not match Evidence")
            if run.target != target or run.target_digest != target_digest:
                raise ValueError(f"{label}_run target does not match Evidence")

        buggy_by_case = {result.case_id: result for result in self.buggy_run.case_results}
        fixed_by_case = {result.case_id: result for result in self.fixed_run.case_results}
        same_cases = buggy_by_case.keys() == fixed_by_case.keys()
        expected_failing = tuple(
            sorted(
                case_id
                for case_id in buggy_by_case.keys() & fixed_by_case.keys()
                if buggy_by_case[case_id].outcome is CaseOutcome.FAILED
                and fixed_by_case[case_id].outcome is CaseOutcome.PASSED
            )
        )

        if self.failing_case_ids != tuple(sorted(set(self.failing_case_ids))):
            raise ValueError("failing_case_ids must be unique and sorted")
        if self.failing_case_ids != expected_failing:
            raise ValueError("failing_case_ids must exactly reflect the two run records")
        if self.rejection_reasons != tuple(sorted(set(self.rejection_reasons))):
            raise ValueError("rejection_reasons must be unique and sorted")

        qualifies = (
            same_cases
            and self.buggy_run.outcome is RunOutcome.TEST_FAILED
            and self.fixed_run.outcome is RunOutcome.PASSED
            and bool(expected_failing)
            and self.failing_case_ids == expected_failing
        )
        if self.reproduced != qualifies:
            raise ValueError("reproduced must exactly reflect the two run records")
        if self.reproduced and self.rejection_reasons:
            raise ValueError("reproduced Evidence cannot contain rejection reasons")
        if not self.reproduced and not self.rejection_reasons:
            raise ValueError("unreproduced Evidence requires at least one rejection reason")
        return self


class TargetInterface(FrozenModel):
    """Trusted contract metadata; target source identity is supplied at replay."""

    contract_family: NonEmptyText
    contract_version: NonEmptyText
    interface_kind: NonEmptyText
    symbol_signature: NonEmptyText


class ValueGuardCase(FrozenModel):
    case_id: NonEmptyText
    args: dict[str, JsonValue]
    expected: JsonValue


class RaisesGuardCase(FrozenModel):
    case_id: NonEmptyText
    args: dict[str, JsonValue]
    raises: ExceptionName


GuardCase = ValueGuardCase | RaisesGuardCase


class Guard(FrozenModel):
    """A minimal, self-contained regression test with explicit provenance."""

    schema_version: Literal["guard.v1"] = "guard.v1"
    guard_id: Annotated[str, StringConstraints(pattern=r"^grd_[A-Za-z0-9][A-Za-z0-9_-]*$")]
    guard_version: Annotated[int, Field(ge=1)] = 1
    created_at: UtcDateTime
    source_evidence_id: Annotated[
        str, StringConstraints(pattern=r"^evd_[A-Za-z0-9][A-Za-z0-9_-]*$")
    ]
    source_evidence_ref: ArtifactRef
    source_evidence_digest: Digest
    contract_id: NonEmptyText
    contract_digest: Digest
    target_interface: TargetInterface
    argument_types: dict[str, ContractType]
    return_type: ContractType
    cases: Annotated[tuple[GuardCase, ...], Field(min_length=1)]
    generator_version: Literal["guard-test.v1", "guard-test.v2"] = "guard-test.v2"
    test_ref: ArtifactRef
    test_digest: Digest
    source_buggy_digest: Digest
    source_fixed_digest: Digest
    validation_run: RunRecord
    state: Literal["candidate"] = "candidate"
    artifact_digest: Digest

    @model_validator(mode="after")
    def validate_guard(self) -> Self:
        if self.guard_id == self.contract_id:
            raise ValueError("Guard and contract must have independent identities")
        if not self.argument_types:
            raise ValueError("Guard must declare argument types")
        case_ids = tuple(case.case_id for case in self.cases)
        if case_ids != tuple(sorted(set(case_ids))):
            raise ValueError("Guard case IDs must be unique and sorted")
        for case in self.cases:
            if set(case.args) != set(self.argument_types):
                raise ValueError("Guard case arguments do not match argument_types")
            for name, value in case.args.items():
                convert_contract_value(value, self.argument_types[name])
            if isinstance(case, ValueGuardCase):
                convert_contract_value(case.expected, self.return_type)
        run = self.validation_run
        if run.role is not RunRole.REPLAY or run.outcome is not RunOutcome.PASSED:
            raise ValueError("Guard requires a successful fixed-target self-check")
        if run.contract_id != self.contract_id or run.contract_digest != self.contract_digest:
            raise ValueError("Guard self-check contract mismatch")
        if run.target_digest != self.source_fixed_digest:
            raise ValueError("Guard self-check must use the source fixed target")
        if tuple(case.case_id for case in run.case_results) != case_ids:
            raise ValueError("Guard self-check must execute exactly its minimal case set")
        return self
