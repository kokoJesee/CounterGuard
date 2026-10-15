"""Execution backends with an explicit trusted-local versus isolated boundary."""

from evidenceguard.runners.base import ExecutionBackend
from evidenceguard.runners.local import LocalTrustedExecutor

__all__ = ["ExecutionBackend", "LocalTrustedExecutor"]
