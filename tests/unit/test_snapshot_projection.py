"""The research grammar is explicit; legacy projection does not acquire it."""

import pytest

from counterguard.contract_draft import project_test
from counterguard.snapshot_execution import render_snapshot_test
from counterguard.snapshot_projection import project_snapshot_test


def source(row):
    return (
        "import pytest\nfrom sample.core import check\n"
        f"@pytest.mark.parametrize('value', [{row}])\n"
        "def test_check(value):\n"
        " with pytest.raises(ValueError, match='outside range'): check(value)\n"
    ).encode()


def project(raw, extractor=project_snapshot_test):
    return extractor(
        raw, test_function="test_check", target_module="sample.core", target_symbol="check"
    )


def test_param_preserves_tuple_literal_match_and_original_identity_deterministically():
    raw = source("pytest.param((-1, 256), id='two values')")
    result = project(raw)
    assert not result["unsupported"]
    assert result["parameter_ids"] == (("two values",),)
    case = result["cases"][0]
    assert case.positional_args[0].kind == "tuple"
    assert case.exception == "ValueError" and case.exception_match == "outside range"
    assert case.parameter_index == 1 and case.assertion_index == 1
    for _ in range(20):
        assert project(raw) == result
    assert (
        project(source("pytest.param((-1, 256), id='different id')"))["source_digest"]
        != result["source_digest"]
    )
    assert project(raw, project_test)["unsupported"][0].reason_code == "nonliteral_expression"


@pytest.mark.parametrize(
    "row",
    [
        "pytest.param(-1)",
        "pytest.param(-1, id=str(1))",
        "pytest.param(-1, id=None)",
        "pytest.param(-1, id='x', marks=pytest.mark.slow)",
        "pytest.param(*[-1], id='x')",
        "pytest.param(-1, **{'id': 'x'})",
        "pytest.param(object(), id='x')",
        "pytest.param(-1, id='x', id='y')",
        "other.param(-1, id='x')",
    ],
)
def test_unsupported_forms_never_silently_drop_rows(row):
    result = project(source(row))
    assert result["unsupported"] and not result["cases"]
    assert result["source_assertions"] == 1 and result["represented_assertions"] == 0


def test_all_parameters_and_assertions_keep_source_order_and_duplicate_input_identity():
    raw = source("pytest.param(-1, id='same'), pytest.param(-1, id='same')")
    result = project(raw)
    assert len(result["cases"]) == 2 and result["parameter_ids"] == (("same",), ("same",))
    assert len({c.case_id for c in result["cases"]}) == 2
    assert [c.parameter_index for c in result["cases"]] == [1, 2]


def test_default_literal_grammar_keeps_legacy_results_and_fixture_remains_unsupported():
    raw = source("-1, 256")
    old, new = project(raw, project_test), project(raw)
    assert [c.positional_args for c in old["cases"]] == [c.positional_args for c in new["cases"]]
    assert not new["unsupported"] and old["cases"][0].case_id != new["cases"][0].case_id
    assert project(raw.replace(b"test_check(value)", b"test_check(value, fixture)"))["unsupported"]


def test_render_minimal_guard_rejects_missing_duplicate_or_reordered_ids():
    from types import SimpleNamespace

    from counterguard.errors import ArtifactIntegrityError

    cases = project(source("-1, 256"))["cases"]
    contract = SimpleNamespace(cases=cases)
    for ids in [
        (),
        ("missing",),
        (cases[0].case_id,) * 2,
        tuple(c.case_id for c in reversed(cases)),
    ]:
        with pytest.raises(ArtifactIntegrityError):
            render_snapshot_test(contract, ids)
