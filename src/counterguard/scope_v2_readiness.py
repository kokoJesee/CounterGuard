"""Machine-verifiable readiness gate for the formal scope_v2 study.

This gate records research readiness.  It does not authorize target execution,
assign semantic labels, or turn engineering fixtures into study observations.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.models import ArtifactRef, Digest, FrozenModel, UtcDateTime
from counterguard.project_config import Identifier, reject_links
from counterguard.standalone_contracts import strict_json

StageName = Literal[
    "specification",
    "feasibility",
    "formal_contracts",
    "real_data",
    "freeze",
    "train_fit",
]
StageStatus = Literal["passed", "partial", "blocked", "not_started"]
Outcome = Literal["insufficient_data", "ready_for_freeze", "study_fit_complete"]
STAGE_ORDER: tuple[StageName, ...] = (
    "specification",
    "feasibility",
    "formal_contracts",
    "real_data",
    "freeze",
    "train_fit",
)


class ReadinessInput(FrozenModel):
    ref: ArtifactRef
    content_digest: Digest
    role: Literal[
        "research_specification",
        "data_card",
        "candidate_ledger",
        "source_observation",
        "engineering_qualification",
    ]


class ReadinessStage(FrozenModel):
    name: StageName
    status: StageStatus
    reason_codes: Annotated[tuple[Identifier, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def canonical_reasons(self):
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("Readiness reason codes must be unique and sorted")
        if self.status == "passed" and self.reason_codes:
            raise ValueError("A passed readiness stage cannot retain blockers")
        if self.status != "passed" and not self.reason_codes:
            raise ValueError("An incomplete readiness stage requires a reason code")
        return self


class ReadinessCounts(FrozenModel):
    candidate_records: Annotated[int, Field(ge=0)]
    verified_source_repairs: Annotated[int, Field(ge=0)]
    external_observation_pairs: Annotated[int, Field(ge=0)]
    formally_admitted_scenarios: Annotated[int, Field(ge=0)]
    frozen_train_rows: Annotated[int, Field(ge=0)]
    frozen_holdout_rows: Annotated[int, Field(ge=0)]
    fitted_guard_slots: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def monotone_evidence(self):
        if self.external_observation_pairs > self.verified_source_repairs:
            raise ValueError("External observations cannot exceed verified source repairs")
        if self.formally_admitted_scenarios > self.external_observation_pairs:
            raise ValueError("Formal scenarios require prior external observation")
        if self.fitted_guard_slots and not self.frozen_train_rows:
            raise ValueError("Fitted Guard slots require frozen training rows")
        return self


class ScopeV2Readiness(FrozenModel):
    schema_version: Literal["scope-v2-readiness.v1"] = "scope-v2-readiness.v1"
    study_id: Literal["scope_v2"] = "scope_v2"
    created_at: UtcDateTime
    source_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$", strict=True)]
    inputs: Annotated[tuple[ReadinessInput, ...], Field(min_length=1, max_length=64)]
    stages: Annotated[tuple[ReadinessStage, ...], Field(min_length=6, max_length=6)]
    counts: ReadinessCounts
    outcome: Outcome
    holdout_exposure: Literal["not_created", "sealed", "known"]
    standards_relaxed: Literal[False] = False
    external_execution_allowed: Literal[False] = False
    next_phase_allowed: bool
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent(self):
        if tuple(row.name for row in self.stages) != STAGE_ORDER:
            raise ValueError("Readiness stages must use the canonical order")
        refs = tuple(row.ref for row in self.inputs)
        if refs != tuple(sorted(set(refs))):
            raise ValueError("Readiness inputs must be unique and sorted")
        by_name = {row.name: row.status for row in self.stages}
        all_passed = all(status == "passed" for status in by_name.values())
        if self.outcome == "study_fit_complete":
            if not all_passed or not self.next_phase_allowed:
                raise ValueError("A completed fit requires every readiness stage to pass")
            if (
                self.counts.formally_admitted_scenarios == 0
                or self.counts.frozen_train_rows == 0
                or self.counts.frozen_holdout_rows == 0
                or self.counts.fitted_guard_slots == 0
            ):
                raise ValueError("A completed fit requires formal data, holdout and fitted slots")
        elif self.next_phase_allowed:
            raise ValueError("Only a completed study fit can open the next phase")
        if self.outcome == "ready_for_freeze" and (
            by_name["feasibility"] != "passed"
            or by_name["formal_contracts"] != "passed"
            or by_name["real_data"] != "passed"
        ):
            raise ValueError("Freeze readiness requires feasibility, contracts and real data")
        if self.holdout_exposure == "not_created" and self.counts.frozen_holdout_rows:
            raise ValueError("A missing holdout cannot contain rows")
        return self


class ReadinessError(ValueError):
    """A readiness artifact or one of its pinned facts is invalid."""


def seal_readiness(value: ScopeV2Readiness) -> ScopeV2Readiness:
    return value.model_copy(update={"artifact_digest": digest_json_artifact(value)})


def _read_bounded(root: Path, ref: str) -> bytes:
    path = root / ref
    reject_links(path)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ReadinessError("readiness_input_missing") from error
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ReadinessError("readiness_input_escaped")
    if resolved.stat().st_size > 4 * 1024 * 1024:
        raise ReadinessError("readiness_input_too_large")
    return resolved.read_bytes()


def verify_readiness(root: Path, path: Path) -> ScopeV2Readiness:
    root = root.resolve(strict=True)
    reject_links(path)
    raw = path.read_bytes()
    strict_json(raw, limit=4 * 1024 * 1024)
    value = ScopeV2Readiness.model_validate_json(raw)
    if value.artifact_digest != digest_json_artifact(value):
        raise ReadinessError("readiness_artifact_digest_mismatch")
    for item in value.inputs:
        if digest_bytes(_read_bounded(root, item.ref)) != item.content_digest:
            raise ReadinessError("readiness_input_digest_mismatch")
    command = subprocess.run(
        ["git", "cat-file", "-e", value.source_commit + "^{commit}"],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if command.returncode != 0:
        raise ReadinessError("readiness_source_commit_missing")
    return value


def dump_readiness(value: ScopeV2Readiness) -> bytes:
    return canonical_json_bytes(value)
