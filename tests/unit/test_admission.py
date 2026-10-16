"""The static engineering classifier cannot authorize, import or install a target."""

import json
import random

import pytest
from typer.testing import CliRunner

from counterguard.admission import admission_user_guidance, assess_minimal_python
from counterguard.cli import app

META = b'[project]\nname="example"\nversion="0.1"\ndependencies=[]\n'


def files(root="src/"):
    return {
        "pyproject.toml": META,
        root + "sample/__init__.py": b"from .core import total\n",
        root + "sample/core.py": b"from decimal import Decimal\ndef total(x): return Decimal(x)\n",
        "tests/test_core.py": (
            b"from sample import total\ndef test_total(): assert total('1') == 1\n"
        ),
    }


@pytest.mark.parametrize("root", ["src", "."])
def test_minimal_root_and_src_are_candidates_never_ready(root):
    report = assess_minimal_python(files("src/" if root == "src" else ""), import_root=root)
    assert report["status"] == "eligible_candidate"
    assert report["engineering_prerequisites"] == ["1_import_layout", "4_repository_guard"]
    assert report["verify_supported"] is False
    assert report["runtime_dependencies"] == []


@pytest.mark.parametrize(
    "path,body,code,prerequisite",
    [
        (
            "pyproject.toml",
            b'[project]\ndependencies=["requests"]',
            "runtime_dependency_installation_required",
            "3_controlled_dependency_installation",
        ),
        (
            "tests/nested/conftest.py",
            b"raise RuntimeError('never execute')",
            "repository_conftest",
            "2_controlled_pytest_bootstrap",
        ),
        (
            "tests/test_core.py",
            b"def test_x(tmp_path): assert True",
            "test_fixture_or_nonliteral_parametrization",
            "2_controlled_pytest_bootstrap",
        ),
        (
            "src/sample/core.py",
            b"import requests",
            "unresolved_or_third_party_import",
            "3_controlled_dependency_installation",
        ),
        (
            "src/sample/core.py",
            b"import importlib\nimportlib.import_module('requests')",
            "dynamic_import_or_code_requires_review",
            "1_import_layout",
        ),
        (
            "src/sample/core.py",
            b"import sys\nsys.path.append('vendor')",
            "custom_import_path_requires_review",
            "1_import_layout",
        ),
        (
            "src/sample/x.so",
            b"not a library",
            "native_code_outside_profile",
            "3_controlled_dependency_installation",
        ),
        (
            "pyproject.toml",
            b'[project]\ndynamic=["dependencies"]',
            "dynamic_runtime_dependencies",
            "3_controlled_dependency_installation",
        ),
        (
            "tests/test_core.py",
            b"import pytest\npytest_plugins=['x']",
            "pytest_plugins_declaration",
            "2_controlled_pytest_bootstrap",
        ),
        (
            "tests/test_core.py",
            b"import pytest\n@pytest.mark.asyncio\nasync def test_x(): pass",
            "async_test_requires_plugin_review",
            "2_controlled_pytest_bootstrap",
        ),
    ],
)
def test_findings_name_missing_prerequisite_and_next_step(path, body, code, prerequisite):
    value = files() | {path: body}
    report = assess_minimal_python(value, import_root="src")
    assert report["status"] != "eligible_candidate"
    item = next(x for x in report["findings"] if x["code"] == code)
    assert item["prerequisite"] == prerequisite and item["next_step"]


def test_literal_builtin_parametrization_does_not_require_a_plugin():
    value = files() | {
        "tests/test_core.py": b"""import pytest
@pytest.mark.parametrize('x', [1, 2])
def test_number(x): assert x > 0
"""
    }
    assert assess_minimal_python(value, import_root="src")["status"] == "eligible_candidate"
    value["tests/test_core.py"] = b"""import pytest
@pytest.mark.parametrize('x', [1], indirect=True)
def test_number(x): assert x > 0
"""
    assert assess_minimal_python(value, import_root="src")["status"] == "unknown"


def test_missing_namespace_or_wrong_layout_is_unknown():
    value = files()
    del value["src/sample/__init__.py"]
    assert assess_minimal_python(value, import_root="src")["status"] == "unknown"
    assert assess_minimal_python(files(), import_root=".")["status"] == "unknown"


@pytest.mark.parametrize(
    "body,code",
    [
        (
            b"import pytest as pt\n@pt.fixture\ndef data(): return 1",
            "pytest_alias_requires_bootstrap_review",
        ),
        (
            b"from pytest import fixture\n@fixture\ndef data(): return 1",
            "pytest_api_requires_bootstrap_review",
        ),
        (
            b'from importlib import import_module as load\nload("requests")',
            "dynamic_import_framework_requires_review",
        ),
    ],
)
def test_known_aliases_cannot_hide_bootstrap_requirements(body, code):
    report = assess_minimal_python(files() | {"tests/test_core.py": body}, import_root="src")
    assert report["status"] == "unknown"
    assert code in {x["code"] for x in report["findings"]}


def test_declared_python_constraint_and_runner_shadow_are_checked():
    report = assess_minimal_python(
        files() | {"pyproject.toml": META + b'requires-python=">=3.14"\n'}, import_root="src"
    )
    assert report["status"] == "blocked"
    report = assess_minimal_python(files() | {"src/json.py": b""}, import_root="src")
    assert "runner_or_stdlib_module_shadowed" in {x["code"] for x in report["findings"]}


def test_twenty_input_orders_preserve_static_result():
    entries = list(files().items()) + [
        ("tests/conftest.py", b""),
        ("src/sample/x.py", b"import xx"),
    ]
    expected = assess_minimal_python(dict(entries), import_root="src")
    for seed in range(20):
        random.Random(seed).shuffle(entries)
        assert assess_minimal_python(dict(entries), import_root="src") == expected


@pytest.mark.parametrize("status", ["eligible_candidate", "blocked", "unknown", "rejected"])
def test_user_guidance_never_asks_users_to_implement_internal_prerequisites(status):
    value = admission_user_guidance(status)
    assert value["next_action"] and value["maintainer_action"]
    assert value["eta"] is None and value["user_can_enable_verify"] is False
    assert value["tracking_url"].endswith("/docs/roadmap.md")
    assert "1_import_layout" not in value["next_action"]


def test_read_failure_points_to_repository_recovery_instead_of_feature_work():
    value = admission_user_guidance("unknown", finding_codes={"repository_unavailable"})
    assert "Check the clone" in value["next_action"]
    assert "has not classified" in value["next_action"]


def test_cli_explicit_mode_and_invalid_profile(monkeypatch):
    seen = []

    def fake(*args, **kwargs):
        seen.append(kwargs)
        return {"status": "eligible_candidate", "execution_allowed": False}

    monkeypatch.setattr("counterguard.admission.admission_repository", fake)
    result = CliRunner().invoke(
        app,
        [
            "preflight",
            "--repo",
            ".",
            "--revision",
            "HEAD",
            "--profile",
            "minimal-python",
            "--import-root",
            "src",
        ],
    )
    assert result.exit_code == 0 and json.loads(result.stdout)["execution_allowed"] is False
    assert seen == [{"import_root": "src"}]
    result = CliRunner().invoke(
        app,
        [
            "preflight",
            "--repo",
            ".",
            "--revision",
            "HEAD",
            "--profile",
            "minimal-python",
            "--import-root",
            "lib",
        ],
    )
    assert result.exit_code == 2 and len(seen) == 1
