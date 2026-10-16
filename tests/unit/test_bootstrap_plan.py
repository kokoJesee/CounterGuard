"""Planning is stable input discovery, never authorization or target execution."""

import importlib
import json
import random
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from counterguard.admission import assess_minimal_python
from counterguard.bootstrap_plan import (
    describe_bootstrap_files,
    inspect_target_closure,
    plan_bootstrap,
)
from counterguard.cli import app
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import Guard
from counterguard.repository import FilePin
from counterguard.repository_models import RepositoryGuard

planner = importlib.import_module("counterguard.bootstrap_plan")


def tree(root="."):
    prefix = "" if root == "." else "src/"
    return {
        prefix + "sample/__init__.py": b"raise RuntimeError('never import package')\n",
        prefix + "sample/core.py": b"from .helpers import total\ndef price(x): return total(x)\n",
        prefix + "sample/helpers.py": b"import math\ndef total(x): return math.ceil(x)\n",
        "pyproject.toml": b'[project]\nname="sample"\ndependencies=[]\n',
        "tests/conftest.py": b"raise RuntimeError('never load conftest')\n",
        "tests/test_core.py": b"from sample.core import price\n"
        b"def test_price():\n    assert price(1) == 1\n    assert price(price(1)) == 1\n",
    }


def closure(files, root="."):
    return inspect_target_closure(files, module="sample.core", import_root=root)


@pytest.mark.parametrize("root", [".", "src"])
def test_includes_package_initializers_and_relative_imports_not_upstream_bootstrap(root):
    value = closure(tree(root), root)
    prefix = "" if root == "." else "src/"
    assert value["status"] == "review_required"
    assert {item["path"] for item in value["files"]} == {
        prefix + "sample/" + tail for tail in ("__init__.py", "core.py", "helpers.py")
    }
    assert value["stdlib_imports"] == ["math"]
    # A raise in the package initializer does not run; static planning does not
    # certify that the later isolated import will succeed.
    assert assess_minimal_python(tree(root), import_root=root)["status"] == "blocked"


def test_initializer_imports_from_children_cycles_and_conditional_imports_are_not_pruned():
    files = tree()
    files["sample/__init__.py"] = b"from . import sibling\n"
    files["sample/sibling.py"] = b"from . import core\nif False:\n import external_dependency\n"
    result = closure(files)
    assert result["status"] == "unknown"
    assert "sample/sibling.py" in {item["path"] for item in result["files"]}
    assert any(item["detail"] == "external_dependency" for item in result["findings"])


@pytest.mark.parametrize(
    "change,code,status",
    [
        ({"sample/__init__.py": None}, "namespace_or_ambiguous_package", "blocked"),
        ({"sample.py": b""}, "namespace_or_ambiguous_package", "blocked"),
        ({"sample/core/__init__.py": b""}, "missing_or_ambiguous_module", "blocked"),
        (
            {"sample/core.py": b"from ...other import x"},
            "relative_import_outside_package",
            "blocked",
        ),
        (
            {"sample/core.py": b"from .helpers import *"},
            "wildcard_import_requires_review",
            "unknown",
        ),
        (
            {"sample/core.py": b"import importlib as loader"},
            "dynamic_import_framework_requires_review",
            "unknown",
        ),
        (
            {"sample/core.py": b"getattr(object(), 'foo')"},
            "dynamic_code_or_lookup_requires_review",
            "unknown",
        ),
        (
            {"sample/core.py": b"def __getattr__(name): pass"},
            "module_lookup_hook_requires_review",
            "unknown",
        ),
        ({"sample/core.py": b"__path__ = []"}, "import_state_mutation_requires_review", "unknown"),
        (
            {"sample/core.py": b"sys.modules['x'] = 1"},
            "import_state_mutation_requires_review",
            "unknown",
        ),
        (
            {"sample/core.py": b"open('payload')"},
            "resource_or_native_access_requires_review",
            "unknown",
        ),
        ({"math.py": b"raise RuntimeError()"}, "runner_or_stdlib_shadowed", "blocked"),
        ({"sample/core.py": b"def !"}, "unparseable_closure_module", "blocked"),
        (
            {"sample/core.py": b"import tests.conftest", "tests/__init__.py": b""},
            "test_bootstrap_in_runtime_closure",
            "blocked",
        ),
    ],
)
def test_uncertainty_and_blockers_remain_explicit(change, code, status):
    files = tree()
    for ref, raw in change.items():
        if raw is None:
            files.pop(ref)
        else:
            files[ref] = raw
    result = closure(files)
    assert result["status"] == status
    assert code in {item["code"] for item in result["findings"]}


def test_closure_budgets_fail_closed(monkeypatch):
    monkeypatch.setattr(planner, "MAX_MODULES", 1)
    assert closure(tree())["status"] == "blocked"
    monkeypatch.setattr(planner, "MAX_MODULES", 256)
    monkeypatch.setattr(planner, "MAX_AST_NODES", 2)
    assert "closure_ast_budget_exceeded" in {item["code"] for item in closure(tree())["findings"]}


def test_bootstrap_presence_is_separate_from_pytest_sections_and_fixture_necessity():
    observed = describe_bootstrap_files(
        {
            "setup.cfg": b"[metadata]\nlicense_files=LICENSE\n",
            "tox.ini": b"[tox]\nenvlist=py313\n[testenv]\ncommands=pytest\n",
            "tests/conftest.py": b"def pytest_ignore_collect(path, config): return False\n",
            "pyproject.toml": b"[tool.pytest.ini_options]\naddopts='--doctest-modules'\n",
        },
        set(),
    )
    by_ref = {item["path"]: item for item in observed}
    assert by_ref["setup.cfg"]["pytest_sections"] == []
    assert by_ref["tox.ini"]["pytest_sections"] == []
    assert by_ref["pyproject.toml"]["pytest_sections"] == ["tool.pytest"]
    assert by_ref["tests/conftest.py"]["named_pytest_hooks"] == ["pytest_ignore_collect"]
    assert all(item["loaded_by_plan"] is False for item in observed)


@pytest.mark.parametrize(
    "ref,raw",
    [
        ("setup.cfg", b"no section"),
        ("pyproject.toml", b"[broken"),
        ("conftest.py", b"def !"),
    ],
)
def test_bad_bootstrap_metadata_stays_visible_as_manual_review(ref, raw):
    result = describe_bootstrap_files({ref: raw}, set())
    assert result[0]["parse_status"] == "requires_manual_review"
    assert result[0]["content_digest"] == digest_bytes(raw)


def test_twenty_file_order_shuffles_have_identical_closure_and_digest():
    values = list(tree().items())
    expected = canonical_json_bytes(closure(dict(values)))
    for seed in range(20):
        random.Random(seed).shuffle(values)
        assert canonical_json_bytes(closure(dict(values))) == expected


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    files = tree()
    pins = tuple(
        FilePin(
            revision="head",
            path=ref,
            object_id=digest_bytes(body)[7:47],
            content_digest=digest_bytes(body),
        )
        for ref, body in files.items()
    )
    monkeypatch.setattr(planner, "read_committed_files", lambda *_: ("a" * 40, files, pins))
    monkeypatch.chdir(tmp_path)
    return repo, files, pins


def run_plan(repo, output):
    return plan_bootstrap(
        repo,
        "HEAD",
        target="sample.core:price",
        import_root=".",
        test_ref="tests/test_core.py",
        test_function="test_price",
        output=Path(output),
    )


def test_plan_pins_complete_tree_and_subset_without_changing_old_profile(inputs):
    repo, files, _ = inputs
    result = run_plan(repo, "one")
    assert result["status"] == "review_required"
    assert len(result["files"]) == len(files)
    assert len(result["proposed_runtime_pins"]) == 3
    assert result["upstream_test_environment"]["whole_tree_assessment"] == (
        assess_minimal_python(files, import_root=".")
    )
    assert any(
        item["path"] == "tests/conftest.py"
        for item in result["upstream_test_environment"]["bootstrap_files"]
    )
    assert result["test_projection"]["source_assertions"] == 2
    assert result["test_projection"]["represented_assertions"] == 1
    assert result["test_projection"]["unsupported"][0]["assertion_count"] == 1
    assert result["artifact_digest"] == digest_json_artifact(result)
    for key in ("execution_allowed", "verify_supported", "upstream_tests_selected_for_execution"):
        assert result[key] is False
    for model in (Guard, RepositoryGuard):
        with pytest.raises(ValidationError):
            model.model_validate(result)
    assert result == run_plan(repo, "two")
    with pytest.raises(ArtifactIntegrityError):
        run_plan(repo, "one")


def test_plan_sorting_is_independent_of_pin_and_tree_iteration_order(inputs, monkeypatch):
    repo, files, pins = inputs
    expected = run_plan(repo, "expected")
    items = list(files.items())
    pin_list = list(pins)
    for seed in range(20):
        random.Random(seed).shuffle(items)
        random.Random(seed).shuffle(pin_list)
        monkeypatch.setattr(
            planner, "read_committed_files", lambda *_: ("a" * 40, dict(items), tuple(pin_list))
        )
        assert run_plan(repo, f"shuffle-{seed}") == expected


def test_cli_emits_plan_but_never_successful_admission(inputs):
    repo, _, _ = inputs
    result = CliRunner().invoke(
        app,
        [
            "bootstrap",
            "plan",
            "--repo",
            str(repo),
            "--revision",
            "HEAD",
            "--target",
            "sample.core:price",
            "--import-root",
            ".",
            "--test-ref",
            "tests/test_core.py",
            "--test-function",
            "test_price",
            "--output",
            "cli",
        ],
    )
    assert result.exit_code == 4, result.output
    assert json.loads(result.stdout)["execution_outcome"] == "not_run"
    assert Path("cli/plan.json").is_file()


def test_output_cannot_write_inside_target_or_escape_caller_workspace(inputs):
    repo, _, _ = inputs
    for output in (repo / "result", Path("..") / "escape"):
        with pytest.raises(ValueError, match="outside target repository"):
            run_plan(repo, output)
