"""Bounded positional calls and class-return oracles; never import candidate code."""

from __future__ import annotations

import ast
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from counterguard.digests import canonical_json_bytes, digest_bytes
from counterguard.models import Digest, FrozenModel, NonEmptyText

TEST_REF = "tests/test_complete_values.py"
CONTRACT_REF = "contracts/mac-complete-v2.json"
CONFIG_REF = "counterguard.yaml"
SOURCE_REF = "src/validators/mac_address.py"
GUARD_ID = "grd_validators_mac_complete_v1"
EVIDENCE_ID = "evd_validators_mac_complete_v3"
BASE = "e01166b00424be9d7d544d262e0e0873e1f0a999"
FIXED = "6ffd8625ee4272dade063653bff615014bdc4734"
FORK_URL = "https://github.com/kokoJesee/validators"
UPSTREAM_URL = "https://github.com/python-validators/validators"
SUFFIX_IDS = ("plain", "lf", "crlf", "space", "lf-extra")


class RepositoryCase(FrozenModel):
    case_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$")]
    positional_args: tuple[str]
    oracle: Literal["is_true", "validation_error_instance"]


class RepositoryContract(FrozenModel):
    schema_version: Literal["contract.v2"] = "contract.v2"
    contract_id: Literal["validators-mac-complete.v2"] = "validators-mac-complete.v2"
    target_module: Literal["validators.mac_address"] = "validators.mac_address"
    target_symbol: Literal["mac_address"] = "mac_address"
    source_ref: Literal["src/validators/mac_address.py"] = SOURCE_REF
    class_module: Literal["validators.utils"] = "validators.utils"
    class_symbol: Literal["ValidationError"] = "ValidationError"
    upstream_commit: Literal[FIXED] = FIXED
    upstream_test_ref: Literal[TEST_REF] = TEST_REF
    upstream_test_digest: Digest
    extraction_version: Literal["validators-test-projection.v1"] = "validators-test-projection.v1"
    upstream_case_count: Literal[35] = 35
    selected_case_count: Literal[10] = 10
    selection: Literal["validate binding is mac_address; all values and suffixes"] = (
        "validate binding is mac_address; all values and suffixes"
    )
    cases: Annotated[tuple[RepositoryCase, ...], Field(min_length=10, max_length=10)]

    @model_validator(mode="after")
    def canonical_cases(self) -> Self:
        ids = [case.case_id for case in self.cases]
        if ids != sorted(set(ids)):
            raise ValueError("Contract case IDs must be unique and sorted")
        return self


def extract_mac_contract(test_bytes: bytes) -> RepositoryContract:
    """Expand the audited upstream parametrize form using AST/literals only."""
    tree = ast.parse(test_bytes)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(functions) != 1 or functions[0].name != "test_complete_identifier":
        raise ValueError("Unsupported upstream test shape")
    function = functions[0]
    expected_body = ast.parse(
        "if suffix:\n"
        "    assert isinstance(validate(value + suffix), ValidationError)\n"
        "else:\n"
        "    assert validate(value) is True\n"
    ).body[0]
    if len(function.body) != 2 or ast.dump(function.body[-1]) != ast.dump(expected_body):
        raise ValueError("Upstream oracle changed; projection requires independent review")
    params = {}
    for decorator in function.decorator_list:
        if (
            not isinstance(decorator, ast.Call)
            or ast.unparse(decorator.func) != "pytest.mark.parametrize"
            or len(decorator.args) != 2
            or decorator.keywords
        ):
            raise ValueError("Unsupported test parametrization")
        key = ast.literal_eval(decorator.args[0])
        if key in params:
            raise ValueError("Duplicate parameter dimension")
        params[key] = decorator.args[1]
    if set(params) != {"validate,value", "suffix"}:
        raise ValueError("Unexpected test parameter dimensions")
    suffixes = ast.literal_eval(params["suffix"])
    if suffixes != ["", "\n", "\r\n", " ", "\nextra"]:
        raise ValueError("Upstream suffix dimension changed")
    values = params["validate,value"]
    if not isinstance(values, ast.List) or len(values.elts) != 7:
        raise ValueError("Upstream value dimension changed")
    known = {"mac_address", "fi_business_id", "fi_ssn", "fr_ssn", "ind_aadhar"}
    selected = []
    for entry in values.elts:
        if (
            not isinstance(entry, ast.Tuple)
            or len(entry.elts) != 2
            or not isinstance(entry.elts[0], ast.Name)
            or entry.elts[0].id not in known
        ):
            raise ValueError("Unsupported validation function binding")
        value = ast.literal_eval(entry.elts[1])
        if not isinstance(value, str):
            raise ValueError("Expected a string input")
        if entry.elts[0].id != "mac_address":
            continue
        value_id = "colons" if ":" in value else "hyphens"
        for suffix_id, suffix in zip(SUFFIX_IDS, suffixes, strict=True):
            selected.append(
                RepositoryCase(
                    case_id=f"mac-{value_id}-{suffix_id}",
                    positional_args=(value + suffix,),
                    oracle="validation_error_instance" if suffix else "is_true",
                )
            )
    return RepositoryContract(
        upstream_test_digest=digest_bytes(test_bytes),
        cases=tuple(sorted(selected, key=lambda case: case.case_id)),
    )


def render_repository_test(
    contract: RepositoryContract, case_ids: tuple[str, ...] | None = None
) -> bytes:
    """Only the two audited oracles are expressible; no eval or arbitrary class lookup."""
    selected = (
        contract.cases
        if case_ids is None
        else tuple(case for case in contract.cases if case.case_id in case_ids)
    )
    if not selected or (case_ids is not None and tuple(c.case_id for c in selected) != case_ids):
        raise ValueError("Guard selection must be canonical and contain known cases")
    payload = canonical_json_bytes([case.model_dump(mode="json") for case in selected]).decode()
    return (
        '"""Generated by guard-test.v3; positional calls preserve the public decorator."""\n'
        "import importlib\nimport json\nimport os\nimport pytest\n\n"
        f"CASES = json.loads({payload!r})\n\n"
        "@pytest.mark.parametrize('case', [pytest.param(c, id=c['case_id']) for c in CASES])\n"
        "def test_guard_case(case):\n"
        "    module = os.environ.get('COUNTERGUARD_TARGET')\n"
        "    symbol = os.environ.get('COUNTERGUARD_SYMBOL')\n"
        "    if module != 'validators.mac_address' or symbol != 'mac_address':\n"
        "        raise pytest.UsageError('This Guard requires its admitted Docker target')\n"
        "    target = getattr(importlib.import_module(module), symbol)\n"
        "    error_class = importlib.import_module('validators.utils').ValidationError\n"
        "    result = target(*case['positional_args'])\n"
        "    if case['oracle'] == 'is_true':\n"
        "        assert result is True\n"
        "    else:\n"
        "        assert isinstance(result, error_class)\n"
    ).encode()


def read_contract(raw: bytes) -> RepositoryContract:
    if len(raw) > 128 * 1024:
        raise ValueError("Contract exceeds byte limit")
    return RepositoryContract.model_validate_json(raw)


class ExplicitPilotScope(FrozenModel):
    schema_version: Literal["pilot-scope.v1"] = "pilot-scope.v1"
    basis: Literal["audited_exact_snapshot"] = "audited_exact_snapshot"
    manifest_digest: Digest
    guard_digest: Digest
    contract_digest: Digest
    source_digest: Digest
    runtime_closure_digest: Digest
    head_commit: NonEmptyText
    reason: Literal["MAC test projection; reviewed decorator and exact fixed snapshot only"] = (
        "MAC test projection; reviewed decorator and exact fixed snapshot only"
    )
    artifact_digest: Digest
