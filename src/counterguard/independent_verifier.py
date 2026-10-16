"""Strict candidate generation boundary; only the Gate can produce trusted Evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, ValidationError, field_validator, model_validator

from counterguard.compiler import _render_test
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.model_client import MAX_RESPONSE_BYTES, ModelClient
from counterguard.models import ArtifactRef, Digest, FrozenModel, TargetRef, UtcDateTime

EMPTY_DIGEST = "sha256:" + "0" * 64
CaseId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")]
RequestId = Annotated[
    str, StringConstraints(pattern=r"^req_[a-z0-9][a-z0-9_]*_v[1-9][0-9]*$", max_length=48)
]
CandidateReason = Literal[
    "candidate_schema", "response_too_large", "contract_digest", "case_coverage"
]


class VerificationRequest(FrozenModel):
    schema_version: Literal["verification-request.v1"] = "verification-request.v1"
    request_id: RequestId
    contract_ref: ArtifactRef
    buggy_target: str
    fixed_target: str
    response_ref: ArtifactRef
    timeout_seconds: Annotated[float, Field(gt=0, le=300, allow_inf_nan=False)] = 30.0


class AgentContext(FrozenModel):
    """Explicit allowlist: no fixed implementation, labels, metrics or environment."""

    schema_version: Literal["agent-context.v1"] = "agent-context.v1"
    contract_ref: ArtifactRef
    contract_digest: Digest
    contract_json: str
    buggy_target: TargetRef
    buggy_target_digest: Digest
    buggy_source_code: str


class CandidateTest(FrozenModel):
    """An oracle-free proposal referencing existing, authoritative contract cases."""

    schema_version: Literal["candidate-test.v1"] = "candidate-test.v1"
    contract_digest: Digest
    case_ids: Annotated[tuple[CaseId, ...], Field(min_length=1)]

    @field_validator("case_ids")
    @classmethod
    def canonical_cases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Candidate case IDs must be unique")
        return tuple(sorted(value))


class CandidateRecord(FrozenModel):
    schema_version: Literal["candidate-record.v1"] = "candidate-record.v1"
    candidate_id: str
    created_at: UtcDateTime
    request_ref: ArtifactRef
    request_digest: Digest
    context_digest: Digest
    response_ref: ArtifactRef
    response_digest: Digest
    response_size: Annotated[int, Field(ge=0)]
    status: Literal["admitted", "rejected"]
    candidate: CandidateTest | None
    reason_code: CandidateReason | None
    generator_version: Literal["guard-test.v2"] = "guard-test.v2"
    artifact_digest: Digest

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        if self.status == "admitted":
            if self.candidate is None or self.reason_code is not None:
                raise ValueError("Admitted candidates require a proposal and no rejection")
        elif self.candidate is not None or self.reason_code is None:
            raise ValueError("Rejected candidates retain only a fingerprint and reason")
        return self


def assess_candidate(
    raw: bytes, context: AgentContext
) -> tuple[CandidateTest | None, CandidateReason | None]:
    """Do not return validation messages or raw responses, which may contain secrets."""
    if len(raw) > MAX_RESPONSE_BYTES:
        return None, "response_too_large"
    try:
        candidate = CandidateTest.model_validate_json(raw)
    except ValidationError:
        return None, "candidate_schema"
    if candidate.contract_digest != context.contract_digest:
        return None, "contract_digest"
    expected_ids = {case["case_id"] for case in json.loads(context.contract_json)["cases"]}
    # D3 audits all known contract cases. Subsets cannot masquerade as full capture.
    if set(candidate.case_ids) != expected_ids:
        return None, "case_coverage"
    return candidate, None


def propose_candidate(
    client: ModelClient,
    context: AgentContext,
    *,
    candidate_id: str,
    request_ref: str,
    request_digest: str,
    response_ref: str,
) -> CandidateRecord:
    if type(context) is not AgentContext:
        raise TypeError("Candidate generator accepts AgentContext only")
    raw = client.generate(context)
    candidate, reason = assess_candidate(raw, context)
    draft = CandidateRecord(
        candidate_id=candidate_id,
        created_at=datetime.now(UTC),
        request_ref=request_ref,
        request_digest=request_digest,
        context_digest=digest_bytes(canonical_json_bytes(context)),
        response_ref=response_ref,
        response_digest=digest_bytes(raw),
        response_size=len(raw),
        status="admitted" if candidate is not None else "rejected",
        candidate=candidate,
        reason_code=reason,
        artifact_digest=EMPTY_DIGEST,
    )
    return draft.model_copy(update={"artifact_digest": digest_json_artifact(draft)})


def render_candidate(candidate: CandidateTest, context: AgentContext) -> bytes:
    """Only trusted contract values enter the existing, fixed test template."""
    admitted, reason = assess_candidate(candidate.model_dump_json().encode(), context)
    if reason is not None or admitted is None:
        raise ValueError("Candidate is not bound to the complete authoritative contract")
    contract = json.loads(context.contract_json)
    by_id = {case["case_id"]: case for case in contract["cases"]}
    return _render_test(
        {
            "argument_types": contract["argument_types"],
            "return_type": contract["return_type"],
            "cases": [by_id[case_id] for case_id in admitted.case_ids],
        }
    )
