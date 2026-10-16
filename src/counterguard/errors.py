"""Domain errors raised by CounterGuard's public interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from counterguard.models import RunRecord


class CounterGuardError(Exception):
    """Base class for errors callers may handle at an CounterGuard boundary."""


class RunnerDependencyError(CounterGuardError, OSError):
    """The current interpreter cannot provide the optional pytest executor."""


class ArtifactIntegrityError(CounterGuardError):
    """An artifact digest or reference does not match the stored content."""


class InvalidEvidenceError(CounterGuardError):
    """Evidence does not satisfy the contract required by a downstream stage."""


class FeatureExtractionError(CounterGuardError):
    """Source syntax or target structure cannot be extracted reliably."""


class InsufficientScopeEvidence(CounterGuardError):
    """Refuse a scope when verified training evidence cannot support it."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


class GuardReplayIntegrityError(ArtifactIntegrityError):
    """Keep the actual run when post-execution checks detect changed input bytes."""

    def __init__(self, detail: str, run: RunRecord) -> None:
        super().__init__(detail)
        self.run = run


class GuardSelfCheckError(CounterGuardError):
    """A generated test failed its fixed-target validation; no Guard was published."""

    def __init__(self, run: RunRecord) -> None:
        super().__init__(f"Guard self-check failed: {run.outcome.value}")
        self.run = run
