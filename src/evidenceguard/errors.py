"""Domain errors raised by EvidenceGuard's public interfaces."""


class EvidenceGuardError(Exception):
    """Base class for errors callers may handle at an EvidenceGuard boundary."""


class ArtifactIntegrityError(EvidenceGuardError):
    """An artifact digest or reference does not match the stored content."""


class InvalidEvidenceError(EvidenceGuardError):
    """Evidence does not satisfy the contract required by a downstream stage."""
