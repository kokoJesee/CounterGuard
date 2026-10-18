"""Draft syntax extraction never evaluates expressions or endorses runtime semantics."""

import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.contract_draft import draft_contract, project_test
from counterguard.contract_draft_models import ContractProposal
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import Guard
from counterguard.repository import FilePin

draft_module = importlib.import_module("counterguard.contract_draft")


def project(body):
    return project_test(
        body.encode(),
        test_function="test_price",
        target_module="sample.pricing",
        target_symbol="price",
    )


def test_direct_assertions_preserve_literal_types_and_oracle_semantics():
    data = project("""from sample.pricing import price
def test_price():
    assert price((1, 2), tags=['a'], context={'x': None}) == b'ok'
    assert price(-1, 1.25) is None
    assert price(True) is not False
    assert price('x') != 0
    assert price(1)
    assert not price(0)
""")
    assert not data["unsupported"] and len(data["cases"]) == 6
    assert [case.oracle for case in data["cases"]] == [
        "eq",
        "is",
        "is_not",
        "ne",
        "truthy",
        "falsey",
    ]
    first = data["cases"][0]
    assert first.positional_args[0].kind == "tuple"
    assert first.keyword_args[0].literal.kind == "list"
    assert first.keyword_args[1].literal.kind == "dict"
    assert first.expected.kind == "bytes" and first.expected.value == "6f6b"
    assert data["cases"][1].positional_args[0].value == -1


def test_literal_parametrization_and_lexical_target_alias():
    data = project("""import pytest
from sample import pricing
@pytest.mark.parametrize('value,expected', [(1, 2), (2, 3)])
@pytest.mark.parametrize('extra', [0, 1])
def test_price(value, expected, extra):
    calculate = pricing.price
    assert calculate(value, extra) == expected
""")
    assert len(data["cases"]) == 4 and data["represented_assertions"] == 1
    assert len({case.case_id for case in data["cases"]}) == 4


def test_truthiness_is_not_misrepresented_as_singleton_identity():
    data = project("from sample.pricing import price\ndef test_price(): assert price(1)\n")
    assert data["cases"][0].oracle == "truthy" and data["cases"][0].expected is None


@pytest.mark.parametrize(
    "statement,reason",
    [
        ("assert price(1 + 2) == 3", "nonliteral_expression"),
        ("assert price(price(1)) == 2", "nonliteral_expression"),
        ("assert price(*[1]) == 2", "argument_expansion_requires_review"),
        ("assert price(1) == helper()", "nonliteral_expression"),
        ("assert 1 == price(2)", "assertion_is_not_a_direct_target_call"),
        ("assert 1 < price(2) < 3", "chained_comparison_requires_review"),
        ("assert price(1) is 'foo'", "literal_or_oracle_requires_review"),
        ("assert price(float('nan')) == 0", "nonliteral_expression"),
        ("assert price(1) == 2, helper()", "nonliteral_expression"),
    ],
)
def test_unsupported_assertions_are_counted_and_never_partly_evaluated(statement, reason):
    data = project(
        "from sample.pricing import price\ndef test_price():\n"
        "    assert price(0) == 0\n    " + statement + "\n"
    )
    assert len(data["cases"]) == 1 and data["source_assertions"] == 2
    assert data["unsupported"][0].reason_code == reason
    assert data["represented_assertions"] + sum(x.assertion_count for x in data["unsupported"]) == 2


@pytest.mark.parametrize(
    "setup", ["prepare()", "result = price(1)", "if True:\n        assert price(1) == 1"]
)
def test_fixture_setup_or_control_flow_rejects_the_selected_function(setup):
    data = project(
        "from sample.pricing import price\ndef test_price():\n    "
        + setup
        + "\n    assert price(0) == 0\n"
    )
    assert not data["cases"]
    assert data["unsupported"][0].reason_code == "test_setup_or_control_flow_requires_review"


def test_simple_whitelisted_exception_oracle_only():
    good = """import pytest
from sample.pricing import price
def test_price():
    with pytest.raises(ValueError):
        price(-1)
"""
    data = project(good)
    assert data["cases"][0].oracle == "raises" and data["cases"][0].exception == "ValueError"
    for source in (
        good.replace("ValueError", "RuntimeError"),
        good.replace("pytest.raises(ValueError)", "pytest.raises(ValueError, match='x.*')"),
        "class ValueError(Exception): pass\n" + good,
    ):
        result = project(source)
        assert not result["cases"] and result["unsupported"]


def test_rebound_global_import_and_fixture_parameters_do_not_claim_target_identity():
    rebound = project(
        "from sample.pricing import price\nprice = object()\n"
        "def test_price(): assert price(1) == 2\n"
    )
    assert not rebound["cases"]
    fixture = project(
        "from sample.pricing import price\ndef test_price(tmp_path): assert price(1) == 2\n"
    )
    assert fixture["unsupported"][0].reason_code == "fixture_or_default_argument_requires_review"


def test_parameter_and_local_scope_cannot_impersonate_imported_functions():
    data = project("""import pytest
from sample.pricing import price
@pytest.mark.parametrize('price', [1])
def test_price(price): assert price(0) == 0
""")
    assert not data["cases"]
    data = project("""from sample import pricing
def test_price():
    assert calculate(1) == 2
    calculate = pricing.price
""")
    assert not data["cases"]
    assert data["unsupported"][0].reason_code == "alias_assignment_after_assertion"
    data = project("""import pytest
from sample.pricing import price
@pytest.mark.parametrize('ValueError', [1])
def test_price(ValueError):
    with pytest.raises(ValueError): price(-1)
""")
    assert not data["cases"]


def test_twenty_repeats_and_comment_changes_preserve_case_ids():
    body = "from sample.pricing import price\ndef test_price(): assert price(1) == 2\n"
    first = project(body)
    for _ in range(20):
        assert project(body) == first
    shifted = project("# source line deliberately changes\n" + body)
    assert shifted["cases"][0].case_id == first["cases"][0].case_id
    assert shifted["cases"][0].source_line != first["cases"][0].source_line


def test_parametrize_explosion_and_side_effect_arguments_cannot_execute():
    oversized = f"""import pytest
from sample.pricing import price
@pytest.mark.parametrize('x', {list(range(17))!r})
@pytest.mark.parametrize('y', {list(range(17))!r})
def test_price(x, y): assert price(x) == y
"""
    assert project(oversized)["unsupported"][0].reason_code == "case_budget_exceeded"
    source = (
        "from sample.pricing import price\ndef test_price(): assert price(__import__('evil')) == 0"
    )
    assert not project(source)["cases"]


def test_invalid_test_and_non_exception_contexts_do_not_hide_assertions():
    with pytest.raises(ValueError, match="cannot be parsed"):
        project("def invalid syntax")
    data = project("""from sample.pricing import price
def test_price():
    with resource():
        assert price(1) == 2
""")
    assert data["source_assertions"] == 1 and not data["cases"]
    assert data["unsupported"][0].assertion_count == 1


@pytest.fixture
def draft_inputs(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    raw = (
        b"raise RuntimeError('module must never load')\nfrom sample.pricing import price\n"
        b"def test_price(): assert price(1) == 2\n"
    )
    pin = FilePin(
        revision="head",
        path="tests/test_price.py",
        object_id="c" * 40,
        content_digest=digest_bytes(raw),
    )
    monkeypatch.setattr(
        draft_module, "read_committed_files", lambda *_: ("a" * 40, {pin.path: raw}, (pin,))
    )
    return tmp_path, repo, raw


def test_proposals_are_pinned_deterministic_and_cannot_enter_guard_models(draft_inputs):
    root, repo, raw = draft_inputs
    values = []
    for name in ("one", "two"):
        value = draft_contract(
            repo,
            "HEAD",
            test_ref="tests/test_price.py",
            test_function="test_price",
            target="sample.pricing:price",
            output=Path(name),
            cwd=root,
        )
        assert value.test_digest == digest_bytes(raw) and value.commit == "a" * 40
        assert value.artifact_digest == digest_json_artifact(value)
        assert value.human_review_required and not value.execution_allowed
        values.append(value)
    assert values[0] == values[1]
    ContractProposal.model_validate_json(canonical_json_bytes(values[0]))
    with pytest.raises(ValidationError):
        Guard.model_validate_json(canonical_json_bytes(values[0]))
    with pytest.raises(ArtifactIntegrityError):
        draft_contract(
            repo,
            "HEAD",
            test_ref="tests/test_price.py",
            test_function="test_price",
            target="sample.pricing:price",
            output=Path("one"),
            cwd=root,
        )


def test_cli_emits_a_review_only_proposal_without_executors(draft_inputs, monkeypatch):
    root, repo, _ = draft_inputs
    monkeypatch.chdir(root)
    result = CliRunner().invoke(
        app,
        [
            "contract",
            "draft",
            "--repo",
            str(repo),
            "--revision",
            "HEAD",
            "--test-ref",
            "tests/test_price.py",
            "--test-function",
            "test_price",
            "--target",
            "sample.pricing:price",
            "--output",
            "proposal",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["execution_allowed"] is False
    assert (root / "proposal/proposal.json").is_file()
