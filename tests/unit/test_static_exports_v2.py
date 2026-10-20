"""Opt-in exports cannot broaden old contracts or suppress unresolved inputs."""

import copy
import json
import random
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from counterguard.bootstrap_binding import bind_contract, prepare_contract, verify_binding
from counterguard.bootstrap_plan import inspect_target_closure
from counterguard.cli import app
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.standalone_capture import capture_standalone
from counterguard.standalone_contracts import (
    StandaloneContractV5,
    StandaloneContractV6,
    read_standalone_contract,
)
from counterguard.static_exports import ExportProblem, resolve_static_reexport
from tests.unit.test_bootstrap_binding import REF, B, F, H
from tests.unit.test_bootstrap_binding import repository as repository

ROOT = b"from .helpers import other\nfrom .core import price\n__version__: str = '1.0'\n"
CORE = b"from __future__ import annotations\nfrom .helpers import other\ndef price(x): return x+1\n"
HELPERS = b"def other(x): return x\n"


def files():
    return {"sample/__init__.py": ROOT, "sample/core.py": CORE, "sample/helpers.py": HELPERS}


def resolve(tree=None, algorithm="static-root-reexport.v2"):
    return resolve_static_reexport(
        files() if tree is None else tree,
        module="sample",
        symbol="price",
        import_root=".",
        algorithm=algorithm,
    )


def test_explicit_v2_pins_all_root_imports_and_definition_relative_imports():
    value = resolve()
    assert value["algorithm"] == "static-root-reexport.v2"
    assert value["definition_ref"] == "sample/core.py"
    assert {x["path"] for x in value["files"]} == set(files())
    with pytest.raises(ExportProblem, match="export_root_statement_unsupported"):
        resolve(algorithm="static-root-reexport.v1")
    with pytest.raises(ExportProblem, match="export_algorithm_unsupported"):
        resolve(algorithm="static-root-reexport.v3")


@pytest.mark.parametrize(
    "suffix,reason",
    [
        (b"price=1\n", "export_root_assignment"),
        (b"from .helpers import other as price\n", "export_rebinding"),
        (b"from .helpers import *\n", "export_wildcard_import"),
        (b"if True:\n from .helpers import price\n", "export_root_statement_unsupported"),
        (b"def __getattr__(name): return 1\n", "export_root_statement_unsupported"),
        (b"__version__: str = 'again'\n", "export_rebinding"),
        (b"open('sentinel','w')\n", "export_root_statement_unsupported"),
        (b"from other.core import value\n", "export_direct_child_required"),
        (b"from .nested.core import value\n", "export_direct_child_required"),
        (b"from .helpers import other as __getattr__\n", "export_hook_binding"),
        (b"from .missing import value\n", "export_missing_or_ambiguous_import"),
        (b"from .helpers import other as str\n", "export_version_annotation_unsupported"),
    ],
)
def test_root_side_effects_hooks_ambiguous_exports_remain_refused(suffix, reason):
    tree = files()
    tree["sample/__init__.py"] += suffix
    with pytest.raises(ExportProblem, match=reason):
        resolve(tree)


@pytest.mark.parametrize(
    "version,reason",
    [
        (b"__version__: list = '1.0'\n", "export_version_annotation_unsupported"),
        (b"__version__: str = 1\n", "export_version_not_literal_string"),
        (b"__version__ = str(1)\n", "export_nonliteral_assignment"),
        (b"value: str = '1.0'\n", "export_root_assignment"),
    ],
)
def test_version_is_one_literal_string_not_general_annotated_assignment(version, reason):
    tree = files()
    tree["sample/__init__.py"] = ROOT.split(b"__version__")[0] + version
    with pytest.raises(ExportProblem, match=reason):
        resolve(tree)


@pytest.mark.parametrize(
    "source,reason",
    [
        (b"from .helpers import price\n", "export_definition_not_ordinary_function"),
        (b"from .core import price\n", "export_rebinding"),
        (b"from .missing import other\n" + CORE, "export_missing_or_ambiguous_import"),
        (b"from ..other import value\n" + CORE, "export_direct_child_required"),
        (CORE + b"price = 1\n", "export_rebinding"),
        (CORE + b"open('sentinel','w')\n", "export_import_time_statement_unsupported"),
        (b"@other\ndef price(x): return x\n", "export_target_decorated"),
        (b"def price(x=other()): return x\n", "export_evaluated_default"),
    ],
)
def test_definition_cannot_be_multihop_rebound_decorated_or_effectful(source, reason):
    tree = files()
    tree["sample/core.py"] = source
    with pytest.raises(ExportProblem, match=reason):
        resolve(tree)


def test_implicit_child_module_binding_cannot_overwrite_an_earlier_export():
    tree = files()
    tree["sample/__init__.py"] = b"from .core import price\nfrom .price import other\n"
    tree["sample/price.py"] = HELPERS
    with pytest.raises(ExportProblem, match="export_rebinding"):
        resolve(tree)


@pytest.fixture
def bound_v6(repository):
    repo, trees, metadata = repository
    for revision in (B, F):
        trees[revision].update(files())
    trees[B]["sample/core.py"] = CORE.replace(b"x+1", b"x")
    trees[F]["tests/test_price.py"] = (
        b"from sample import price\ndef test_price():\n assert price(1)==2\n"
    )
    prepare_contract(
        repo,
        buggy=B,
        fixed=F,
        contract_id="price.exports.v2",
        target="sample:price",
        import_root=".",
        test_ref="tests/test_price.py",
        test_function="test_price",
        output=Path("prepared-v6"),
        profile="static-reexport-v2",
    )
    trees[H] = {**trees[F], REF: Path("prepared-v6/contract.json").read_bytes()}
    value = bind_contract(repo, H, REF, output=Path("bound-v6"))
    return repo, trees, metadata, value


def test_new_contract_and_binding_are_explicit_and_rebuilt_for_each_role(bound_v6):
    repo, trees, _, value = bound_v6
    contract = read_standalone_contract(trees[H][REF])
    assert type(contract) is StandaloneContractV6
    assert value["schema_version"] == "bootstrap-binding.v4"
    assert value["capture_input_status"] == "review_required" and not value["execution_allowed"]
    for role in ("buggy", "fixed", "head"):
        assessment = value["runtime_assessments"][role]
        assert assessment["algorithm"] == contract.closure_algorithm
        assert assessment["static_export"]["algorithm"] == contract.export_algorithm
        assert assessment["hook_observations"] == []
    with pytest.raises(ValidationError):
        StandaloneContractV5.model_validate_json(trees[H][REF])
    for field in ("hook_grammar", "closure_algorithm", "export_algorithm", "profile"):
        forged = json.loads(trees[H][REF])
        forged[field] = "unknown.v99"
        with pytest.raises(ValidationError):
            read_standalone_contract(canonical_json_bytes(forged))
    assert verify_binding(repo, Path("bound-v6/binding.json")) == value
    for seed in range(20):
        for revision, tree in list(trees.items()):
            items = list(tree.items())
            random.Random(seed).shuffle(items)
            trees[revision] = dict(items)
        assert bind_contract(repo, H, REF, output=Path(f"shuffle-v6-{seed}")) == value


@pytest.mark.parametrize("part", ["algorithm", "export", "hooks", "missing_file", "schema"])
def test_self_signed_binding_does_not_authorize_a_changed_algorithm_or_observation(bound_v6, part):
    repo, _, _, original = bound_v6
    value = copy.deepcopy(original)
    assessment = value["runtime_assessments"]["buggy"]
    if part == "algorithm":
        assessment["algorithm"] = "module-import-closure.v1"
    elif part == "export":
        assessment["static_export"]["definition_symbol"] = "other"
    elif part == "hooks":
        assessment["hook_observations"] = [{"recognition": "forged"}]
    elif part == "missing_file":
        assessment["files"].pop()
    else:
        value["schema_version"] = "bootstrap-binding.v3"
    value["artifact_digest"] = digest_json_artifact(value)
    Path("forged-v6.json").write_bytes(canonical_json_bytes(value))
    with pytest.raises(ArtifactIntegrityError, match="does_not_match"):
        verify_binding(repo, Path("forged-v6.json"))


def test_unchanged_default_prepare_does_not_try_the_broader_profile(bound_v6):
    repo, _, _, _ = bound_v6
    prepare_contract(
        repo,
        buggy=B,
        fixed=F,
        contract_id="price.default.v1",
        target="sample:price",
        import_root=".",
        test_ref="tests/test_price.py",
        test_function="test_price",
        output=Path("prepared-default"),
    )
    value = json.loads(Path("prepared-default/preparation.json").read_bytes())
    assert json.loads(Path("prepared-default/contract.json").read_bytes())["schema_version"] == (
        "contract.v3"
    )
    assert value["runtime_assessment"]["status"] == "unknown"


def test_module_hook_unknown_stops_before_resolving_any_runner(bound_v6, monkeypatch):
    repo, trees, _, _ = bound_v6
    for revision in (B, F, H):
        trees[revision]["sample/helpers.py"] += b"__getattr__ = other\n"
    value = bind_contract(repo, H, REF, output=Path("unknown-v6"))
    assert value["capture_input_status"] == "unknown"

    def forbidden(*args, **kwargs):
        pytest.fail("unknown inputs must not reach runner resolution")

    monkeypatch.setattr("counterguard.standalone_capture.resolve_runner", forbidden)
    result = capture_standalone(
        repo,
        Path("unknown-v6/binding.json"),
        runner_id="root-pytest8",
        evidence_id="evd_unknown_exports_v2",
        review_reason="cannot erase unknown",
        output=Path("not-executed-v6"),
    )
    assert result["reason_code"] == "capture_inputs_require_resolution"
    assert result["completed_record_refs"] == []


def test_cli_new_profile_is_visible_and_unknown_profile_refused(bound_v6):
    repo, _, _, _ = bound_v6
    command = [
        "contract",
        "prepare",
        "--repo",
        str(repo),
        "--buggy",
        B,
        "--fixed",
        F,
        "--contract-id",
        "price.cli.v2",
        "--target",
        "sample:price",
        "--import-root",
        ".",
        "--test-ref",
        "tests/test_price.py",
        "--test-function",
        "test_price",
        "--output",
        "cli-v6",
        "--profile",
        "static-reexport-v2",
    ]
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 4, result.output
    assert json.loads(Path("cli-v6/contract.json").read_bytes())["schema_version"] == "contract.v6"
    command[-1] = "bypass"
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 5 and "preparation_profile_unsupported" in result.output


def test_closure_unknown_versions_are_not_treated_as_the_latest():
    with pytest.raises(ValueError, match="Unsupported closure"):
        inspect_target_closure(files(), module="sample", import_root=".", algorithm="v99")
