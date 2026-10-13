"""A different code shape that still satisfies the v1 query-limit contract."""

import re


def parse_limit(raw: str | None) -> int:
    if raw is None:
        return 20
    if re.fullmatch(r"[0-9]+", raw) is None:
        raise ValueError("limit must contain ASCII decimal digits")

    value = int(raw)
    if not 1 <= value <= 100:
        raise ValueError("limit is outside the accepted range")
    return value
