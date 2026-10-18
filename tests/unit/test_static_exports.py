"""Bounded static exports, role reconstruction and refusal without Python imports."""

import json
import random
from pathlib import Path

import pytest
from pydantic import ValidationError

from counterguard.bootstrap_binding import bind_contract, prepare_contract, verify_binding
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.standalone_capture import capture_standalone
from counterguard.standalone_contracts import (
    StandaloneContractV4,
    StandaloneContractV5,
    read_standalone_contract,
)
from counterguard.standalone_test import render_standalone_test
from counterguard.static_exports import ExportProblem, resolve_static_reexport
from tests.unit.test_bootstrap_binding import REF, B, F, H
from tests.unit.test_bootstrap_binding import repository as repository

ROOT = b"from .core import price\n__all__ = ['price']\n"
SOURCE = b"def price(x): return x + 1\n"


def resolve(root=ROOT, source=SOURCE, **extra):
    return resolve_static_reexport(
        {"sample/__init__.py": root, "sample/core.py": source, **extra},
        module="sample",
        symbol="price",
        import_root=".",
    )


@pytest.mark.parametrize("root", [ROOT, b"from sample.core import price\n"])
def test_explicit_absolute_and_relative_root_exports_are_source_pinned(root):
    value = resolve(root)
    assert value["definition_module"] == "sample.core"
    assert value["definition_symbol"] == "price"
    assert value["definition_ref"] == "sample/core.py"
    assert [x["path"] for x in value["files"]] == ["sample/__init__.py", "sample/core.py"]
    assert all(x["content_digest"].startswith("sha256:") for x in value["files"])


def test_explicit_alias_preserves_public_symbol_and_defining_symbol():
    value = resolve(b"from .core import original as price\n", b"def original(x): return x\n")
    assert value["target_symbol"] == "price" and value["definition_symbol"] == "original"


@pytest.mark.parametrize(
    "root,reason",
    [
        (b"from .core import *\n", "export_wildcard_import"),
        (b"if True:\n from .core import price\n", "export_root_statement_unsupported"),
        (ROOT + b"price = 0\n", "export_root_assignment"),
        (ROOT + b"del price\n", "export_root_statement_unsupported"),
        (ROOT + b"price = helper()\n", "export_nonliteral_assignment"),
        (ROOT + b"globals()['price'] = 0\n", "export_dynamic_assignment"),
        (ROOT + b"setattr(helper, 'price', 0)\n", "export_root_statement_unsupported"),
        (ROOT + b"def __getattr__(name): return 0\n", "export_root_statement_unsupported"),
        (b"from .core import price, other as price\n", "export_rebinding"),
        (b"from .core import price\nfrom .other import other\n", "export_single_import_required"),
        (b"from ..core import price\n", "export_direct_child_required"),
        (b"from other.core import price\n", "export_direct_child_required"),
        (b"from .nested.core import price\n", "export_direct_child_required"),
        (b"from .core import price, __getattr__\n", "export_hook_binding"),
        (ROOT + b"__all__ += ['price']\n", "export_root_statement_unsupported"),
    ],
)
def test_root_side_effects_and_ambiguous_bindings_are_explicitly_refused(root, reason):
    with pytest.raises(ExportProblem, match=reason):
        resolve(root)


@pytest.mark.parametrize(
    "source,reason",
    [
        (b"from .other import price\n", "export_local_import"),
        (b"class price: pass\n", "export_import_time_statement_unsupported"),
        (b"async def price(x): return x\n", "export_import_time_statement_unsupported"),
        (b"@decorator\ndef price(x): return x\n", "export_target_decorated"),
        (SOURCE + b"price = 0\n", "export_rebinding"),
        (SOURCE + b"price = helper()\n", "export_nonliteral_assignment"),
        (SOURCE + b"del price\n", "export_import_time_statement_unsupported"),
        (SOURCE + b"globals()['price'] = 0\n", "export_dynamic_assignment"),
        (SOURCE + b"helper()\n", "export_import_time_statement_unsupported"),
        (b"def price(x=helper()): return x\n", "export_evaluated_default"),
        (b"def price(x: helper()): return x\n", "export_evaluated_annotation"),
        (SOURCE + b"if False:\n price = 0\n", "export_conditional_binding"),
        (SOURCE + b"import external\n", "export_nonstdlib_import"),
        (SOURCE + b"from functools import *\n", "export_wildcard_import"),
        (SOURCE + b"@helper\ndef other(): pass\n", "export_other_decorator_unsupported"),
        (SOURCE + b"def __getattr__(name): return 0\n", "export_hook_binding"),
        (b"def other(): pass\n", "export_definition_not_ordinary_function"),
    ],
)
def test_definition_module_rebinding_and_import_time_execution_stay_unknown(source, reason):
    with pytest.raises(ExportProblem, match=reason):
        resolve(source=source)


def test_deferred_annotations_false_typing_block_and_other_stdlib_cache_are_supported():
    source = b"""from __future__ import annotations
from functools import cache
TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any
@cache
def other(x): return x
def price(x: Any = None) -> Any: return x
"""
    assert resolve(source=source)["definition_symbol"] == "price"
    with pytest.raises(ExportProblem, match="export_rebinding"):
        resolve(source=source + b"cache = 0\n")
    with pytest.raises(ExportProblem, match="export_conditional_binding"):
        resolve(source=source.replace(b"TYPE_CHECKING = False", b"TYPE_CHECKING = True"))


def test_ambiguous_missing_and_unparseable_sources_are_not_guessed():
    for extra in ({"sample.py": b""}, {"sample/core/__init__.py": b""}):
        with pytest.raises(ExportProblem, match="export_ambiguous_module"):
            resolve(**extra)
    with pytest.raises(ExportProblem, match="export_source_unparseable"):
        resolve(source=b"not python !!!")
    with pytest.raises(ExportProblem, match="export_source_missing"):
        resolve_static_reexport({}, module="sample", symbol="price", import_root=".")
    with pytest.raises(ExportProblem, match="export_ast_budget_exceeded"):
        resolve(source=b"pass\n" * 50001)


@pytest.fixture
def exported_contract(repository):
    repo, trees, metadata = repository
    for revision in (B, F):
        trees[revision]["sample/__init__.py"] = ROOT
    trees[F]["tests/test_price.py"] = b"""import pytest
from sample import price
def test_price():
    with pytest.raises(ValueError, match='invalid value'): price(-1)
"""
    report = prepare_contract(
        repo,
        buggy=B,
        fixed=F,
        contract_id="price.export.v1",
        target="sample:price",
        import_root=".",
        test_ref="tests/test_price.py",
        test_function="test_price",
        output=Path("export-prepared"),
    )
    raw = Path("export-prepared/contract.json").read_bytes()
    trees[H] = {**trees[F], REF: raw}
    return repo, trees, metadata, report, read_standalone_contract(raw)


def test_v5_preserves_public_call_and_reconstructs_all_three_roles(exported_contract):
    repo, trees, _, report, contract = exported_contract
    assert isinstance(contract, StandaloneContractV5) and contract.schema_version == "contract.v5"
    assert contract.source_ref == "sample/__init__.py"
    assert contract.definition_ref == "sample/core.py"
    with pytest.raises(ValidationError):
        StandaloneContractV4.model_validate_json(canonical_json_bytes(contract))
    assert report["runtime_assessment"]["status"] == "review_required"
    assert report["buggy_runtime_assessment"]["status"] == "review_required"
    value = bind_contract(repo, H, REF, output=Path("export-bound"))
    assert value["schema_version"] == "bootstrap-binding.v3"
    assert value["capture_input_status"] == "review_required" and not value["execution_allowed"]
    for role in ("buggy", "fixed", "head"):
        assert value["runtime_assessments"][role]["static_export"]["definition_symbol"] == "price"
    assert verify_binding(repo, Path("export-bound/binding.json")) == value
    rendered = render_standalone_test(contract)
    assert b"MODULE = 'sample'\nSYMBOL = 'price'" in rendered
    assert b"MODULE = 'sample.core'" not in rendered
    for seed in range(20):
        for revision, files in list(trees.items()):
            items = list(files.items())
            random.Random(seed).shuffle(items)
            trees[revision] = dict(items)
        assert bind_contract(repo, H, REF, output=Path(f"export-shuffle-{seed}")) == value


@pytest.mark.parametrize("role", [B, F])
def test_changed_export_in_either_role_stops_before_transport(exported_contract, role):
    repo, trees, _, _, _ = exported_contract
    trees[role]["sample/__init__.py"] = ROOT + b"price = 0\n"
    if role == F:
        trees[H]["sample/__init__.py"] = trees[F]["sample/__init__.py"]
    value = bind_contract(repo, H, REF, output=Path("bad-export"))
    assert value["capture_input_status"] == "unknown"
    assert any(
        item["code"] == "export_root_assignment"
        for item in value["runtime_assessments"]["buggy" if role == B else "fixed"]["findings"]
    )
    result = capture_standalone(
        repo,
        Path("bad-export/binding.json"),
        runner_id="root-pytest8",
        evidence_id="evd_bad_export",
        review_reason="cannot override unknown",
        output=Path("refused-export"),
    )
    assert result["reason_code"] == "capture_inputs_require_resolution"
    assert result["completed_record_refs"] == [] and result["reproduced"] is False


def test_forged_definition_is_not_authorized_by_a_self_digest(exported_contract):
    repo, trees, _, _, _ = exported_contract
    data = json.loads(trees[H][REF])
    data["definition_symbol"] = "other"
    trees[H][REF] = canonical_json_bytes(data)
    value = bind_contract(repo, H, REF, output=Path("forged-export"))
    assert value["capture_input_status"] == "unknown"
    assert any(
        x["code"] == "export_definition_mismatch"
        for x in value["runtime_assessments"]["fixed"]["findings"]
    )
    value["capture_input_status"] = "review_required"
    value["artifact_digest"] = digest_json_artifact(value)
    Path("forged-export/binding.json").write_bytes(canonical_json_bytes(value))
    with pytest.raises(ArtifactIntegrityError, match="does_not_match"):
        verify_binding(repo, Path("forged-export/binding.json"))


def test_old_contract_cannot_be_relabelled_into_export_support(exported_contract):
    _, _, _, _, contract = exported_contract
    value = json.loads(canonical_json_bytes(contract))
    value.update(schema_version="contract.v4", profile="standalone-literals-match.v1")
    with pytest.raises(ValidationError):
        read_standalone_contract(canonical_json_bytes(value))


def test_plain_cases_retain_projection_v1_in_new_export_contract(repository):
    repo, trees, _ = repository
    for revision in (B, F):
        trees[revision]["sample/__init__.py"] = ROOT
    trees[F]["tests/test_price.py"] = (
        b"from sample import price\ndef test_price():\n assert price(1) == 2\n"
    )
    prepare_contract(
        repo,
        buggy=B,
        fixed=F,
        contract_id="price.plain-export.v1",
        target="sample:price",
        import_root=".",
        test_ref="tests/test_price.py",
        test_function="test_price",
        output=Path("plain-export"),
    )
    contract = read_standalone_contract(Path("plain-export/contract.json").read_bytes())
    assert contract.schema_version == "contract.v5"
    assert contract.test_origin.extractor_version == "literal-test-projection.v1"
    assert "exception_match" not in contract.cases[0].model_dump()
    assert b"standalone-test.v2" in render_standalone_test(contract)
    value = json.loads(canonical_json_bytes(contract))
    value["definition_ref"] = "sample/other.py"
    with pytest.raises(ValidationError):
        read_standalone_contract(canonical_json_bytes(value))
