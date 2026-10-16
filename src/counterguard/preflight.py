"""Conservative, static admission for the existing no-install Docker profile."""

from __future__ import annotations

import ast
import re
import shlex
import tomllib
from pathlib import Path, PurePosixPath

from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import digest_json_artifact
from counterguard.repository import RepositoryProblem, read_committed_files


def inspect_execution_requirements(
    files: dict[str, bytes], *, pytest_version: str = "8.4.2", import_root: str = "."
) -> dict:
    """Parse metadata/AST only; eligible means candidate, never permission to execute."""
    if import_root not in {".", "src"} or not re.fullmatch(r"\d+\.\d+\.\d+", pytest_version):
        raise ValueError("Unsupported static runner profile")
    runner_version = tuple(int(part) for part in pytest_version.split("."))
    findings, warnings = [], []
    runtime_dependencies = None
    optional_dependencies = {}

    def finding(code, path, *, unknown=False):
        findings.append((code, path, "unknown" if unknown else "blocked"))

    def pytest_config(config, path):
        minimum = config.get("minversion")
        if minimum is not None:
            if not isinstance(minimum, str) or not re.fullmatch(r"\d+(?:\.\d+){0,2}", minimum):
                finding("unrecognized_pytest_minversion", path, unknown=True)
            else:
                version = tuple(int(x) for x in minimum.split("."))
                version += (0,) * (3 - len(version))
                if version > runner_version:
                    finding("declared_pytest_minversion_exceeds_formal_runner", path)
        if config.get("required_plugins"):
            finding("required_pytest_plugins", path)
        options = config.get("addopts", [])
        options = shlex.split(options) if isinstance(options, str) else options
        if not isinstance(options, list) or any(not isinstance(x, str) for x in options):
            finding("unrecognized_pytest_options", path, unknown=True)
        elif any(x.startswith("-p") for x in options):
            finding("explicit_pytest_plugin", path)
        if config.get("pythonpath") and config["pythonpath"] not in ([import_root], import_root):
            finding("non_root_import_path", path)
        warnings.append(("repository_pytest_config_is_not_loaded", path))

    for ref, body in sorted(files.items()):
        name = PurePosixPath(ref).name
        if name == "conftest.py":
            finding("repository_conftest", ref)
        if name in {"setup.py", "setup.cfg"}:
            finding("legacy_install_metadata_requires_review", ref, unknown=True)
        if name in {"pytest.ini", ".pytest.ini", "tox.ini"}:
            finding("legacy_test_configuration_requires_review", ref, unknown=True)
        if name in {"pytest.toml", ".pytest.toml"}:
            try:
                config = tomllib.loads(body.decode("utf-8")).get("pytest", {})
                pytest_config(config, ref)
                if runner_version < (9, 0, 0):
                    finding("native_pytest_toml_requires_newer_runner", ref)
            except (ValueError, UnicodeError, TypeError, AttributeError):
                finding("invalid_pytest_toml", ref, unknown=True)
        if name == "pyproject.toml":
            try:
                value = tomllib.loads(body.decode("utf-8"))
                project = value.get("project", {})
                dependencies = project.get("dependencies")
                if "dependencies" in project.get("dynamic", []):
                    finding("dynamic_runtime_dependencies", ref, unknown=True)
                elif dependencies is None or not isinstance(dependencies, list):
                    finding("runtime_dependencies_not_declared", ref, unknown=True)
                else:
                    runtime_dependencies = dependencies
                    if dependencies:
                        finding("runtime_dependency_installation_required", ref)
                optional_dependencies = project.get("optional-dependencies", {})
                tool = value.get("tool", {})
                pytest_table = tool.get("pytest")
                config = (
                    pytest_table.get("ini_options", pytest_table)
                    if isinstance(pytest_table, dict)
                    else pytest_table
                )
                if config is not None:
                    pytest_config(config, ref)
                where = tool.get("setuptools", {}).get("packages", {}).get("find", {})
                if isinstance(where, dict) and where and where.get("where", ["."]) != [import_root]:
                    finding("package_import_mapping_requires_review", ref, unknown=True)
                if optional_dependencies:
                    warnings.append(("optional_extras_are_not_installed", ref))
            except (ValueError, UnicodeError, TypeError, AttributeError):
                finding("invalid_or_unsupported_project_metadata", ref, unknown=True)
        if not ref.endswith(".py"):
            continue
        try:
            tree = ast.parse(body)
        except (SyntaxError, UnicodeError, ValueError, RecursionError):
            finding("unparseable_python", ref, unknown=True)
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                if any(
                    isinstance(child, ast.Name) and child.id == "pytest_plugins"
                    for target in targets
                    for child in ast.walk(target)
                ):
                    finding("pytest_plugins_declaration", ref)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"exec", "eval", "__import__"}
            ):
                warnings.append(("dynamic_code_requires_target_review", ref))
    if not any(PurePosixPath(ref).name == "pyproject.toml" for ref in files):
        finding("runtime_dependencies_not_declared", "pyproject.toml", unknown=True)
    findings = sorted(set(findings))
    return {
        "status": "blocked"
        if any(x[2] == "blocked" for x in findings)
        else "unknown"
        if findings
        else "eligible_candidate",
        "findings": [dict(zip(("code", "path", "severity"), x, strict=True)) for x in findings],
        "warnings": [dict(zip(("code", "path"), x, strict=True)) for x in sorted(set(warnings))],
        "runtime_dependencies": runtime_dependencies,
        "optional_dependencies": optional_dependencies,
        "formal_runner_pytest": pytest_version,
        "claim": "static compatibility candidate only; not dependency completeness, "
        "Scope applicability, ready inspection or execution authorization",
    }


def preflight_repository(repo: str | Path, revision: str) -> dict:
    files, pins, commit = {}, (), None
    try:
        commit, files, pins = read_committed_files(repo, revision)
        requirements = inspect_execution_requirements(files)
    except RepositoryProblem as error:
        requirements = {
            "status": "rejected" if error.rejected else "unknown",
            "findings": [{"code": error.code, "path": None}],
        }
    except (OSError, ValueError, UnicodeError) as error:
        requirements = {
            "status": "unknown",
            "findings": [
                {
                    "code": "repository_preflight_unavailable",
                    "path": None,
                    "error_type": type(error).__name__,
                },
            ],
        }
    result = {
        "schema_version": "repository-preflight.v1",
        "requested_revision": revision,
        "commit": commit,
        "source_selection": "complete_committed_tree_only",
        "execution_allowed": False,
        "execution_outcome": "not_run",
        "profile": "docker-policy.v1/no-install/root-imports",
        **requirements,
        "file_count": len(files),
        "files": [pin.model_dump(mode="json") for pin in pins],
        "implementation_digests": inspection_implementation_digests(),
    }
    result["artifact_digest"] = digest_json_artifact(result)
    return result
