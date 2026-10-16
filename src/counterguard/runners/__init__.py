"""Execution backends with an explicit trusted-local versus isolated boundary."""

from counterguard.runners.base import ExecutionBackend
from counterguard.runners.local import LocalTrustedExecutor

__all__ = ["ExecutionBackend", "LocalTrustedExecutor"]
