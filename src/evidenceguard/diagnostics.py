"""Bound user-facing diagnostics; original evidence remains in private raw logs."""

import re

_CREDENTIAL = re.compile(
    r"""(?i)(\b(?:api[_-]?key|access[_-]?token|token|password|secret|authorization)\s*[:=]\s*)"""
    r"""(?:"[^"\r\n]*"|'[^'\r\n]*'|(?:Bearer\s+)?[^\s,;]+)"""
)
_ABSOLUTE_PATH = re.compile(r"""(?<![\w.:/\\])(?:[A-Za-z]:[\\/]|\\\\|/(?!/))[^\r\n"'<>]+""")


def public_diagnostic(message: str) -> str:
    """Remove explicit credential assignments and absolute paths from CLI error text.

    This is a bounded diagnostic policy, not a general secret detector or public log exporter.
    """
    message = _CREDENTIAL.sub(lambda match: match[1] + "[redacted]", message)
    return _ABSOLUTE_PATH.sub("[redacted-path]", message)
