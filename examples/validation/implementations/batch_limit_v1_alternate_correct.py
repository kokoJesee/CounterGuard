"""A holdout batch-limit implementation with a different parsing path."""

import re


def parse_limit(raw: str | None) -> int:
    if raw is None:
        return 250
    if re.fullmatch(r"[0-9]+", raw) is None:
        raise ValueError("batch size must contain ASCII decimal digits")

    value = int(raw)
    if not 1 <= value <= 1000:
        raise ValueError("batch size is outside the accepted range")
    return value
