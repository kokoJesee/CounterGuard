"""Domain errors raised by EvidenceGuard's public interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evidenceguard.models import RunRecord


class EvidenceGuardError(Exception):
    """Base class for errors callers may handle at an EvidenceGuard boundary."""


class ArtifactIntegrityError(EvidenceGuardError):
    """An artifact digest or reference does not match the stored content."""


class InvalidEvidenceError(EvidenceGuardError):
    """Evidence does not satisfy the contract required by a downstream stage."""


class FeatureExtractionError(EvidenceGuardError):
    """Source syntax or target structure cannot be extracted reliably."""


class InsufficientScopeEvidence(EvidenceGuardError):
    """Refuse a scope when verified training evidence cannot support it."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


class GuardSelfCheckError(EvidenceGuardError):
    """A generated test failed its fixed-target validation; no Guard was published."""

    def __init__(self, run: RunRecord) -> None:
        super().__init__(f"Guard self-check failed: {run.outcome.value}")
        self.run = run
