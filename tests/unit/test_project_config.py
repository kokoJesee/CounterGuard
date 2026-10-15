"""Configuration is bounded data with portable literal paths, never executable YAML."""

import json

import pytest

from evidenceguard.project_config import (
    CONFIG_LIMIT,
    ProjectConfig,
    load_project_config,
    repository_path,
)
from evidenceguard.repository import validate_revision


def mapping(**updates):
    return {
        "target_id": "pricing",
        "guard_id": "grd_price",
        "source_ref": "src/pricing.py",
        "symbol": "price",
        "contract_ref": "contracts/price.json",
        **updates,
    }


def project(**updates):
    return {
        "schema_version": "project-config.v1",
        "project_id": "fixture",
        "targets": [mapping()],
        **updates,
    }


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "../x.py",
        "/x.py",
        "C:/x.py",
        "a\\b.py",
        "a//b.py",
        "a/./b.py",
        "a/../b.py",
        ".git/config",
        ".GIT/config",
        "a:b.py",
        "a\nb.py",
        "a\x00b.py",
        "a\x1bb.py",
        "a\u202eb.py",
        "CON.py",
        "a/nul.txt",
        "a/COM1",
        "a. /x.py",
        "a./x.py",
        "a /x.py",
        "a/*.py",
        "a/?x.py",
        'a/"x.py',
        "a/<x.py",
        "a/|x.py",
        "a/e\u0301.py",
    ],
)
def test_unsafe_paths_are_rejected(path):
    with pytest.raises(ValueError):
        repository_path(path)


def test_json_subset_and_input_digest_are_explicit(tmp_path):
    path = tmp_path / "project.yaml"
    path.write_text(json.dumps(project()), encoding="utf-8")
    config, digest = load_project_config(path)
    assert config.targets[0].input_refs() == ("contracts/price.json", "src/pricing.py")
    assert digest.startswith("sha256:")
    path.write_text("project_id: fixture\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON syntax"):
        load_project_config(path)


def test_module_is_optional_for_inspection_and_strict_when_declared():
    without_module = ProjectConfig.model_validate_json(json.dumps(project()))
    with_module = ProjectConfig.model_validate_json(
        json.dumps(project(targets=[mapping(module="src.pricing")]))
    )

    assert without_module.targets[0].module is None
    assert with_module.targets[0].module == "src.pricing"


def test_config_size_limit_is_checked_before_parsing(tmp_path):
    path = tmp_path / "project.json"
    path.write_bytes(b" " * (CONFIG_LIMIT + 1))
    with pytest.raises(ValueError, match="128 KiB"):
        load_project_config(path)


@pytest.mark.parametrize(
    "path",
    [
        "CHANGELOG",
        "LICENSE.txt",
        ".gitignore",
        ".github/workflows/ci.yml",
        ".github/dependabot.yaml",
        ".circleci/config.yml",
        ".gitlab-ci.yml",
    ],
)
def test_explicit_auxiliary_control_plane_paths_can_be_declared(path):
    config = ProjectConfig.model_validate_json(json.dumps(project(ignored_paths=[path])))
    assert config.ignored_paths == (path,)


@pytest.mark.parametrize(
    "payload",
    [
        project(targets=[mapping(), mapping()]),
        project(ignored_paths=["src/pricing.py"]),
        project(ignored_paths=["requirements.txt"]),
        project(ignored_paths=["assets/logo.png"]),
        project(ignored_paths=[".github/actions/build/action.yml"]),
        project(extra_command="do something"),
        project(targets=[mapping(source_ref="src/pricing.txt")]),
        project(targets=[mapping(symbol="price.__globals__")]),
        project(targets=[mapping(module="src/pricing")]),
        project(targets=[mapping(module="os.__dict__")]),
        project(targets=[mapping(dependency_refs=["dep.py", "dep.py"])]),
    ],
)
def test_config_refuses_ambiguous_bindings_and_implicit_execution(payload):
    with pytest.raises(ValueError):
        ProjectConfig.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "revision",
    [
        "",
        "--all",
        "--output=x",
        "HEAD;exit",
        "HEAD\n",
        "a..b",
        "HEAD:path.py",
        "$(command)",
        "refs//heads/main",
        "HEAD@{1}",
    ],
)
def test_unsafe_or_unsupported_revision_syntax_never_becomes_an_argument(revision):
    with pytest.raises(ValueError):
        validate_revision(revision)
