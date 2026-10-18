"""Message oracles retain pytest search semantics without a general regex parser."""

import importlib
import json
import re
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

from counterguard.bootstrap_binding import bind_contract, prepare_contract, verify_binding
from counterguard.contract_draft import draft_contract, project_test
from counterguard.contract_draft_models import (
    ContractProposal,
    ContractProposalV2,
    DraftCase,
    DraftMatchCase,
)
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.literal_match import validate_literal_match
from counterguard.standalone_contracts import (
    StandaloneContract,
    StandaloneContractV4,
    read_standalone_contract,
)
from counterguard.standalone_guard import render_minimal_test
from counterguard.standalone_test import render_standalone_test
from tests.unit.test_bootstrap_binding import REF, B, F, H
from tests.unit.test_bootstrap_binding import repository as repository


def source(expression="'invalid value'", *, exception="ValueError"):
    return (
        "import pytest\nfrom sample.core import price\ndef test_price():\n"
        f"    with pytest.raises({exception}, match={expression}): price(-1)\n"
    ).encode()


def project(raw):
    return project_test(
        raw, test_function="test_price", target_module="sample.core", target_symbol="price"
    )


@pytest.mark.parametrize(
    "pattern",
    [
        "invalid value",
        "",
        "错误：无效",
        "two\nlines",
        r"invalid\[value\]",
        r"literal\.\*\(\)\\",
        r"a\ b\#c\-d",
    ],
)
def test_literal_patterns_are_preserved_and_have_only_literal_search_semantics(pattern):
    case = project(source(repr(pattern)))["cases"][0]
    assert isinstance(case, DraftMatchCase)
    assert case.exception_match == pattern and case.oracle == "raises"
    assert case.exception == "ValueError" and case.expected is None
    assert validate_literal_match(pattern) == pattern
    assert case.model_dump()["exception_match"] == pattern


@pytest.mark.parametrize(
    "pattern",
    [
        ".*",
        "a+",
        "(a+)+",
        "[0-9]",
        "a|b",
        "^x$",
        "x{2}",
        "(?i)x",
        "(?=x)",
        r"\d",
        r"\1",
        r"\q",
        "x\\",
        "x" * 4097,
    ],
)
def test_regex_syntax_is_explicitly_unsupported_not_escaped_or_weakened(pattern):
    value = project(source(repr(pattern)))
    assert value["cases"] == () and value["source_assertions"] == 1
    assert value["unsupported"][0].reason_code in {
        "exception_match_regex_unsupported",
        "exception_match_literal_required",
    }
    assert value["unsupported"][0].assertion_count == 1


@pytest.mark.parametrize(
    "expression",
    [
        "None",
        "42",
        "b'x'",
        "helper()",
        "re.escape('x')",
        "re.compile('x')",
        "pattern",
        "f'{helper()}'",
    ],
)
def test_nonliteral_match_never_evaluates_or_silently_discards_an_expression(expression):
    value = project(source(expression))
    assert not value["cases"]
    assert value["unsupported"][0].reason_code == "exception_match_literal_required"


@pytest.mark.parametrize(
    "substitution",
    [
        "ValueError, match='x', check=helper",
        "ValueError, **opts",
        "(ValueError, TypeError), match='x'",
        "RuntimeError, match='x'",
    ],
)
def test_message_support_preserves_exception_and_keyword_allowlists(substitution):
    value = project(source().replace(b"ValueError, match='invalid value'", substitution.encode()))
    assert not value["cases"] and value["unsupported"]


def test_match_has_stable_identity_and_changes_oracle_digest():
    raw = source()
    first = project(raw)
    for _ in range(20):
        assert project(raw) == first
    assert project(b"# shifted line\n" + raw)["cases"][0].case_id == first["cases"][0].case_id
    changed = project(source("'different value'"))
    bare = project(raw.replace(b", match='invalid value'", b""))
    assert len({x["cases"][0].case_id for x in (first, changed, bare)}) == 3
    assert digest_json_artifact(first) != digest_json_artifact(changed)
    assert "exception_match" not in bare["cases"][0].model_dump()


def test_parameter_expansion_retains_all_cases_and_partial_assertion_accounting():
    raw = b"""import pytest
from sample.core import price
@pytest.mark.parametrize('x', [-1, -2])
def test_price(x):
    with pytest.raises(ValueError, match='invalid'): price(x)
    with pytest.raises(ValueError, match='.*'): price(x)
    with pytest.raises(TypeError): price(x)
"""
    value = project(raw)
    assert len(value["cases"]) == 4 and value["represented_assertions"] == 2
    assert value["source_assertions"] == 3 and len(value["unsupported"]) == 1
    assert sum(x.assertion_count for x in value["unsupported"]) == 1


@pytest.fixture
def matched_contract(repository, request):
    repo, trees, metadata = repository
    trees[F]["tests/test_price.py"] = source()
    exported = getattr(request, "param", "direct") == "reexport"
    if exported:
        for revision in (B, F):
            trees[revision]["sample/__init__.py"] = b"from .core import price\n"
        trees[F]["tests/test_price.py"] = source().replace(b"from sample.core", b"from sample")
    report = prepare_contract(
        repo,
        buggy=B,
        fixed=F,
        contract_id="price.match.v1",
        target="sample:price" if exported else "sample.core:price",
        import_root=".",
        test_ref="tests/test_price.py",
        test_function="test_price",
        output=Path("match-prepared"),
    )
    raw = Path("match-prepared/contract.json").read_bytes()
    trees[H] = {**trees[F], REF: raw}
    return repo, trees, metadata, report, read_standalone_contract(raw)


def test_new_shapes_are_versioned_and_old_models_reject_message_data(matched_contract, monkeypatch):
    repo, _, _, report, contract = matched_contract
    assert isinstance(contract, StandaloneContractV4)
    assert contract.test_origin.extractor_version == "literal-test-projection.v2"
    assert contract.schema_version == "contract.v4" and report["execution_allowed"] is False
    assert report["runtime_assessment"]["status"] == "review_required"
    with pytest.raises(ValidationError):
        StandaloneContract.model_validate_json(canonical_json_bytes(contract))
    with pytest.raises(ValidationError):
        DraftCase.model_validate_json(canonical_json_bytes(contract.cases[0]))
    bind_contract(repo, H, REF, output=Path("match-bound"))
    assert (
        verify_binding(repo, Path("match-bound/binding.json"))["contract"]["cases"][0][
            "exception_match"
        ]
        == "invalid value"
    )
    monkeypatch.setattr(
        importlib.import_module("counterguard.contract_draft"),
        "read_committed_files",
        importlib.import_module("counterguard.bootstrap_binding").read_committed_files,
    )
    proposal = draft_contract(
        repo,
        F,
        test_ref="tests/test_price.py",
        test_function="test_price",
        target="sample.core:price",
        output=Path("match-draft"),
    )
    assert isinstance(
        proposal, ContractProposalV2
    ) and proposal.artifact_digest == digest_json_artifact(proposal)
    with pytest.raises(ValidationError):
        ContractProposal.model_validate_json(canonical_json_bytes(proposal))


def test_relabeling_or_tampering_with_message_contract_fails_closed(matched_contract):
    _, _, _, _, contract = matched_contract
    value = json.loads(canonical_json_bytes(contract))
    value["cases"][0]["exception_match"] = ".*"
    with pytest.raises(ValidationError):
        read_standalone_contract(canonical_json_bytes(value))
    value["cases"][0]["exception_match"] = "valid"
    value["schema_version"] = "contract.v3"
    value["profile"] = "standalone-literals.v1"
    value["test_origin"]["extractor_version"] = "literal-test-projection.v1"
    with pytest.raises(ValidationError):
        read_standalone_contract(canonical_json_bytes(value))
    case = json.loads(canonical_json_bytes(contract.cases[0]))
    case.update(oracle="truthy", exception=None)
    with pytest.raises(ValidationError):
        DraftMatchCase.model_validate_json(canonical_json_bytes(case))


def load_trusted_fixture_test(contract, monkeypatch, target):
    module = ModuleType("sample.core")
    module.price = target
    monkeypatch.setitem(importlib.import_module("sys").modules, "sample.core", module)
    monkeypatch.setenv("COUNTERGUARD_TARGET", "sample.core")
    monkeypatch.setenv("COUNTERGUARD_SYMBOL", "price")
    namespace = {}
    exec(
        compile(render_standalone_test(contract), "<tool-owned generated fixture>", "exec"),
        namespace,
    )
    return namespace


def test_generated_oracle_checks_type_message_substring_and_notes(matched_contract, monkeypatch):
    _, _, _, _, contract = matched_contract
    current = [ValueError("prefix invalid value suffix")]

    def trusted_fixture(_):
        raise current[0]

    namespace = load_trusted_fixture_test(contract, monkeypatch, trusted_fixture)
    case = namespace["CASES"][0]
    namespace["test_guard_case"](case)
    current[0] = ValueError("wrong message")
    with pytest.raises(AssertionError):
        namespace["test_guard_case"](case)
    current[0] = TypeError("invalid value")
    with pytest.raises(TypeError):
        namespace["test_guard_case"](case)
    current[0] = ValueError("different text")
    current[0].add_note("invalid value")
    namespace["test_guard_case"](case)
    minimal = render_minimal_test(contract, tuple(c.case_id for c in contract.cases))
    assert b"standalone-guard-test.v2" in minimal and b"exception_match" in minimal
    assert b"standalone-test.v2" in render_standalone_test(contract)


def test_literal_subset_agrees_with_pytest_search_without_running_target_code():
    # Independent equivalence check for a literal grammar, including escaped punctuation.
    for literal in ["plain", "a.b*[]()\\?", "中文", "a-b #", ""]:
        pattern = re.escape(literal)
        validate_literal_match(pattern)
        for message in [literal, "prefix " + literal + " suffix", "unrelated"]:
            assert bool(re.search(pattern, message)) == (literal in message)
