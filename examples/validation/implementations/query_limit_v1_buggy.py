"""Buggy v1 parser: zero is accidentally accepted."""


def parse_limit(raw: str | None) -> int:
    if raw is None:
        return 20
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError("limit must contain ASCII decimal digits")

    value = int(raw)
    if value < 0 or value > 100:
        raise ValueError("limit must be between 1 and 100")
    return value
