"""Offline provider seam: responses are data, never executable Python or Evidence."""

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from counterguard.independent_verifier import AgentContext

MAX_RESPONSE_BYTES = 64 * 1024


class ModelClient(Protocol):
    def generate(self, context: "AgentContext") -> bytes:
        """Return an untrusted JSON candidate using only the whitelisted context."""
        ...


class RecordedModelClient:
    """Replay a reviewed response without network access or credential discovery."""

    def __init__(self, response_path: Path):
        self.response_path = response_path

    def generate(self, context: "AgentContext") -> bytes:
        # Reject the wrong envelope rather than duck-typing a request with fixed answers.
        from counterguard.independent_verifier import AgentContext

        if type(context) is not AgentContext:
            raise TypeError("Provider accepts AgentContext only")
        with self.response_path.open("rb") as stream:
            return stream.read(MAX_RESPONSE_BYTES + 1)
