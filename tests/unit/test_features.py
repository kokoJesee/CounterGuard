"""Positive, near-miss, and failure examples freeze the exact AST vocabulary."""

import pytest

from evidenceguard.errors import FeatureExtractionError
from evidenceguard.features import extract_ast_features
from evidenceguard.predicates import VOCABULARY

PAIRS = [
    (
        "branch:is_member",
        "def target(is_member):\n return 1 if is_member else 2",
        "def target(is_member):\n return 'is_member'",
    ),
    (
        "branch:none",
        "def target(raw):\n if raw is None: return 1\n return 2",
        "def target(raw):\n if raw == None: return 1\n return 2",
    ),
    ("decimal:multiply", "def target(x):\n return x * 2", "def target(x):\n return x ** 2"),
    ("decimal:subtract", "def target(x):\n return x - 2", "def target(x):\n return -x"),
    ("int:parse", "def target(raw):\n return int(raw)", "def target(raw):\n return parse_int(raw)"),
    (
        "regex:ascii_digits",
        "import re\ndef target(raw):\n return re.fullmatch('[0-9]+', raw)",
        "import re\ndef target(raw):\n return re.fullmatch(r'\\d+', raw)",
    ),
    (
        "range:check",
        "def target(x):\n if x < 1 or x > 100: return 0\n return x",
        "def target(x):\n if x < 1: return 0\n return x",
    ),
    (
        "round:half_up",
        "from decimal import ROUND_HALF_UP\ndef target(x):\n return ROUND_HALF_UP",
        "from decimal import ROUND_HALF_EVEN\ndef target(x):\n return ROUND_HALF_EVEN",
    ),
    (
        "str:isascii",
        "def target(raw):\n return raw.isascii()",
        "def target(raw):\n return raw.isascii",
    ),
    (
        "str:isdecimal",
        "def target(raw):\n return raw.isdecimal()",
        "def target(raw):\n return raw.isdigit()",
    ),
]


@pytest.mark.parametrize("token, positive, near_miss", PAIRS, ids=[item[0] for item in PAIRS])
def test_each_token_has_a_positive_and_near_miss(token, positive, near_miss):
    assert token in extract_ast_features(positive, "target")
    assert token not in extract_ast_features(near_miss, "target")


def test_all_ten_tokens_are_covered():
    assert {token for token, _, _ in PAIRS} == set(VOCABULARY)


@pytest.mark.parametrize(
    "expression", ["raw is None", "raw is not None", "None is raw", "None is not raw"]
)
def test_none_token_accepts_identity_checks_in_conditional_expressions(expression):
    assert extract_ast_features(
        f"def target(raw):\n return 1 if {expression} else 2", "target"
    ) == {"branch:none"}


@pytest.mark.parametrize(
    "source",
    [
        "def target(x):\n return x + 1",
        "def target(x):\n if x > 0: return x\n return 0",
        "def target(raw):\n return raw is None",
        "def target(x):\n other = 0\n if other is None: return x\n return 0",
    ],
)
def test_branch_none_never_means_absence_of_branch_tokens(source):
    assert "branch:none" not in extract_ast_features(source, "target")


def test_if_statement_and_if_expression_both_recognize_is_member():
    statement = "def target(is_member):\n if is_member: return 1\n return 2"
    expression = "def target(is_member):\n return 1 if is_member else 2"
    assert extract_ast_features(statement, "target") == extract_ast_features(expression, "target")


def test_other_functions_defaults_and_module_code_do_not_supply_target_tokens():
    source = """from decimal import ROUND_HALF_UP
outside = 2 * 3
def unrelated(raw):
 if raw is None: return int(raw)
 return 0
def target(x=2*3):
 return x + 1
raise RuntimeError('must never execute source')
"""
    assert extract_ast_features(source, "target") == frozenset()


@pytest.mark.parametrize(
    "condition", ["1 <= x <= 100", "x >= 1 and 100 >= x", "x < 0 or x > 100", "-10 < x < 10"]
)
def test_range_requires_complete_numeric_bounds_in_one_condition(condition):
    assert "range:check" in extract_ast_features(
        f"def target(x):\n if {condition}: return x\n return 0", "target"
    )


@pytest.mark.parametrize("condition", ["x < 1 or y > 100", "x > 1 or x > 100", "low < x < high"])
def test_partial_or_different_value_ranges_do_not_count(condition):
    assert "range:check" not in extract_ast_features(
        f"def target(x, y, low, high):\n if {condition}: return x\n return 0", "target"
    )


def test_shadowed_builtin_or_module_alias_is_not_assumed_to_be_the_real_api():
    assert "int:parse" not in extract_ast_features(
        "def target(int, raw):\n return int(raw)", "target"
    )
    assert "int:parse" not in extract_ast_features(
        "int = custom\ndef target(raw):\n return int(raw)", "target"
    )
    assert "regex:ascii_digits" not in extract_ast_features(
        "def target(re, raw):\n return re.fullmatch('[0-9]+', raw)", "target"
    )
    assert "round:half_up" not in extract_ast_features(
        "from decimal import ROUND_HALF_UP\ndef target(ROUND_HALF_UP):\n return ROUND_HALF_UP",
        "target",
    )


def test_import_aliases_resolve_to_the_declared_library_api():
    source = """import re as regex
import decimal as dec
def target(raw):
 result = regex.fullmatch('[0-9]+', raw)
 return dec.ROUND_HALF_UP
"""
    assert extract_ast_features(source, "target") == {"regex:ascii_digits", "round:half_up"}
    assert extract_ast_features(
        "from builtins import int as parse_int\ndef target(raw):\n return parse_int(raw)", "target"
    ) == {"int:parse"}


@pytest.mark.parametrize(
    "source, symbol",
    [
        ("def broken(:", "target"),
        ("def target(x, x): return x", "target"),
        ("def other(): pass", "target"),
        ("def target(): pass\ndef target(): pass", "target"),
        ("class Box:\n def target(self): pass", "Box.target"),
        ("async def target(): pass", "target"),
        ("@wrap\ndef target(): pass", "target"),
        ("def target():\n def nested(): return 2*3\n return nested()", "target"),
        ("def target():\n return lambda x: x*2", "target"),
        ("def target(xs):\n return [x*2 for x in xs]", "target"),
        ("def target(x):\n while x: x -= 1\n return x", "target"),
    ],
)
def test_unresolved_or_unsupported_source_fails_instead_of_returning_empty_features(source, symbol):
    with pytest.raises(FeatureExtractionError):
        extract_ast_features(source, symbol)
