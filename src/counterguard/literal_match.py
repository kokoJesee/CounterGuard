"""A bounded literal-only subset of pytest's regex-search message oracle.

Never compile or evaluate patterns while inspecting a repository. An accepted
pattern has the same meaning when passed unchanged to pytest.raises(match=...).
"""

META = frozenset(r".^$*+?{}[]\|()")
ESCAPABLE = META | frozenset(" -#&~")
MATCH_LIMIT = 4096


def validate_literal_match(pattern: str) -> str:
    if not isinstance(pattern, str) or len(pattern) > MATCH_LIMIT:
        raise ValueError("exception_match_literal_required")
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += 1
            if index == len(pattern) or pattern[index] not in ESCAPABLE:
                raise ValueError("exception_match_regex_unsupported")
        elif char in META:
            raise ValueError("exception_match_regex_unsupported")
        index += 1
    return pattern
