"""Append-only review states, independent of immutable Guard bytes and disable status."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.models import Digest, FrozenModel, UtcDateTime


class GuardState(StrEnum):
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    ACTIVE = "active"
    RETIRED = "retired"


TRANSITIONS = {
    GuardState.CANDIDATE: frozenset({GuardState.SHADOW, GuardState.RETIRED}),
    GuardState.SHADOW: frozenset({GuardState.ACTIVE, GuardState.RETIRED}),
    GuardState.ACTIVE: frozenset({GuardState.SHADOW, GuardState.RETIRED}),
    GuardState.RETIRED: frozenset(),
}


def require_transition(before: GuardState, after: GuardState) -> None:
    if after not in TRANSITIONS[before]:
        raise ValueError(f"Illegal Guard transition: {before} -> {after}")


class LifecycleEvent(FrozenModel):
    schema_version: Literal["guard-lifecycle-event.v1"] = "guard-lifecycle-event.v1"
    registry_id: str
    sequence: Annotated[int, Field(ge=1)]
    guard_id: Annotated[str, Field(min_length=1, max_length=512)]
    guard_digest: Digest
    evidence_digest: Digest
    kind: Literal["transitioned"] = "transitioned"
    before: GuardState
    after: GuardState
    actor: Annotated[str, Field(min_length=1, max_length=512)]
    reason: Annotated[str, Field(min_length=1, max_length=512)]
    created_at: UtcDateTime
    previous_digest: Digest
    artifact_digest: Digest

    @model_validator(mode="after")
    def legal_transition(self):
        require_transition(self.before, self.after)
        return self


def state_from_events(events, guard_id: str) -> GuardState:
    state = GuardState.CANDIDATE
    for event in events:
        if event.guard_id == guard_id and isinstance(event, LifecycleEvent):
            if event.before is not state:
                raise ValueError("Guard lifecycle history is discontinuous")
            state = event.after
    return state
