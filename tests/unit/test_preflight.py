"""Static candidate checks cannot import code or silently enable repository plugins."""

import json

import pytest
from typer.testing import CliRunner

from evidenceguard.cli import app
from evidenceguard.preflight import inspect_execution_requirements

META = b'[project]\nname="fixture"\ndependencies=[]\n'


def test_plain_zero_dependency_project_is_only_a_candidate():
    report = inspect_execution_requirements(
        {
            "pyproject.toml": META,
            "library.py": b"raise RuntimeError('never import')",
        }
    )
    assert report["status"] == "eligible_candidate"
    assert report["runtime_dependencies"] == []
    assert "not dependency completeness" in report["claim"]


@pytest.mark.parametrize(
    "ref,body,reason",
    [
        ("tests/nested/conftest.py", b"raise RuntimeError()", "repository_conftest"),
        ("tests/test_one.py", b"pytest_plugins=['plugin']", "pytest_plugins_declaration"),
        (
            "pyproject.toml",
            META + b'[tool.pytest.ini_options]\nrequired_plugins=["cov"]\n',
            "required_pytest_plugins",
        ),
        (
            "pyproject.toml",
            META + b'[tool.pytest.ini_options]\naddopts="-p plugin"\n',
            "explicit_pytest_plugin",
        ),
        (
            "pyproject.toml",
            META + b'[tool.pytest.ini_options]\npythonpath=["src"]\n',
            "non_root_import_path",
        ),
        (
            "pyproject.toml",
            b'[project]\ndependencies=["requests"]\n',
            "runtime_dependency_installation_required",
        ),
    ],
)
def test_hidden_configuration_and_install_requirements_are_blocked(ref, body, reason):
    report = inspect_execution_requirements({"pyproject.toml": META, ref: body})
    assert report["status"] == "blocked"
    assert reason in {row["code"] for row in report["findings"]}


@pytest.mark.parametrize(
    "files",
    [
        {"a.py": b"def x(): return 1"},
        {"pyproject.toml": b"invalid toml"},
        {"pyproject.toml": b'[project]\ndynamic=["dependencies"]'},
        {"pyproject.toml": META, "setup.py": b"raise RuntimeError('never execute')"},
        {"pyproject.toml": META, "a.py": b"def invalid python"},
    ],
)
def test_missing_dynamic_legacy_or_unparseable_inputs_remain_unknown(files):
    assert inspect_execution_requirements(files)["status"] == "unknown"


def test_shuffling_paths_preserves_the_static_report():
    files = {"pyproject.toml": META, "b.py": b"x=1", "a.py": b"pytest_plugins=[]"}
    assert inspect_execution_requirements(files) == inspect_execution_requirements(
        dict(reversed(list(files.items())))
    )


@pytest.mark.parametrize("table", ["tool.pytest", "tool.pytest.ini_options"])
def test_both_pytest_toml_forms_and_minversion_are_audited(table):
    body = META + f'[{table}]\nminversion="9.0"\npythonpath=["src"]\n'.encode()
    report = inspect_execution_requirements({"pyproject.toml": body})
    reasons = {row["code"] for row in report["findings"]}
    assert report["status"] == "blocked"
    assert "declared_pytest_minversion_exceeds_formal_runner" in reasons
    assert "non_root_import_path" in reasons


def test_src_layout_alone_requires_review_and_does_not_claim_install_is_necessary():
    body = META + b'[tool.setuptools.packages.find]\nwhere=["src"]\n'
    report = inspect_execution_requirements({"pyproject.toml": body})
    assert report["status"] == "unknown"
    assert report["findings"][0]["code"] == "package_import_mapping_requires_review"


@pytest.mark.parametrize("ref", ["pytest.toml", ".pytest.toml"])
def test_separate_native_pytest_toml_is_not_missed(ref):
    report = inspect_execution_requirements(
        {
            "pyproject.toml": META,
            ref: b'[pytest]\nrequired_plugins=["pytest-cov"]\n',
        }
    )
    assert report["status"] == "blocked"
    assert "required_pytest_plugins" in {x["code"] for x in report["findings"]}


def test_preflight_cli_unknown_never_launches_a_local_executor(monkeypatch):
    payload = {"status": "blocked", "execution_allowed": False, "execution_outcome": "not_run"}
    monkeypatch.setattr("evidenceguard.cli.preflight_repository", lambda *_: payload)
    result = CliRunner().invoke(app, ["preflight", "--repo", ".", "--revision", "HEAD"])
    assert result.exit_code == 4
    assert json.loads(result.stdout)["execution_allowed"] is False
