"""Buggy v2 parser: it keeps the v1 default while using the v2 range."""


def parse_limit(raw: str | None) -> int:
    if raw is None:
        return 20
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError("limit must contain ASCII decimal digits")

    value = int(raw)
    if value < 1 or value > 200:
        raise ValueError("limit must be between 1 and 200")
    return value
