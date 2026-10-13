"""A legal v1 parser with batch-worker semantics instead of query semantics."""


def parse_limit(raw: str | None) -> int:
    if raw is None:
        return 250
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError("batch size must contain ASCII decimal digits")

    value = int(raw)
    if value < 1 or value > 1000:
        raise ValueError("batch size must be between 1 and 1000")
    return value
