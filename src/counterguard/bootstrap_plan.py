"""Read-only input planning, deliberately separate from execution authorization.

Follow imports at module granularity, including package initializers and imports
inside functions/branches. Never infer that a selected function makes the rest of
its module irrelevant. This is a review aid, not a Python dependency proof.
"""

import ast
import configparser
import json
import tomllib
from pathlib import Path, PurePosixPath

from pydantic import TypeAdapter

from counterguard.admission import STDLIB, assess_minimal_python
from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.contract_draft import project_test
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.project_config import Module, RepositoryPath, Symbol, reject_links
from counterguard.repository import read_committed_files

MAX_MODULES = 256
MAX_AST_NODES = 50000
BOOTSTRAP_NAMES = frozenset(
    {
        "conftest.py",
        "pytest.ini",
        ".pytest.ini",
        "pytest.toml",
        ".pytest.toml",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "tox.ini",
    }
)


def describe_bootstrap_files(files: dict[str, bytes], selected_refs: set[str]) -> list[dict]:
    """File presence and explicit declarations, not an inference of necessity."""
    result = []
    for ref, raw in sorted(files.items()):
        name = PurePosixPath(ref).name
        if name not in BOOTSTRAP_NAMES:
            continue
        item = {
            "path": ref,
            "content_digest": digest_bytes(raw),
            "in_proposed_runtime_closure": ref in selected_refs,
            "loaded_by_plan": False,
            "interpretation": "presence_and_syntax_only_not_target_requirement",
        }
        try:
            if name in {"conftest.py", "setup.py"}:
                parsed = ast.parse(raw)
                functions = sorted(
                    node.name
                    for node in parsed.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                )
                item["top_level_functions"] = functions
                item["named_pytest_hooks"] = [n for n in functions if n.startswith("pytest_")]
            elif name.endswith(".toml"):
                config = tomllib.loads(raw.decode())
                if name == "pyproject.toml":
                    tool = config.get("tool", {})
                    item["pytest_sections"] = ["tool.pytest"] if "pytest" in tool else []
                    item["dependency_group_names"] = sorted(config.get("dependency-groups", {}))
                else:
                    item["pytest_sections"] = ["pytest"] if "pytest" in config else []
            else:
                config = configparser.ConfigParser(interpolation=None)
                config.read_string(raw.decode())
                sections = sorted(config.sections())
                item["config_sections"] = sections
                item["pytest_sections"] = [
                    section for section in sections if section in {"pytest", "tool:pytest"}
                ]
        except (
            SyntaxError,
            UnicodeError,
            ValueError,
            TypeError,
            AttributeError,
            configparser.Error,
            RecursionError,
        ):
            item["parse_status"] = "requires_manual_review"
        else:
            item["parse_status"] = "parsed_syntax_only"
        result.append(item)
    return result


def inspect_target_closure(files: dict[str, bytes], *, module: str, import_root: str) -> dict:
    """Build a deterministic proposed input set; unresolved inputs stay visible."""
    TypeAdapter(Module).validate_python(module)
    if import_root not in {".", "src"}:
        raise ValueError("Use --import-root . or src")
    prefix = "" if import_root == "." else "src/"
    modules = {}
    for ref in sorted(files):
        if not ref.startswith(prefix) or not ref.endswith(".py"):
            continue
        parts = ref[len(prefix) : -3].split("/")
        if parts[-1] == "__init__":
            parts.pop()
        if parts and all(part.isidentifier() for part in parts):
            modules.setdefault(".".join(parts), []).append(ref)
    findings, edges, stdlib, selected = set(), set(), set(), {}
    pending, visited, total_nodes = {module}, set(), 0

    def issue(code, ref, detail="", severity="unknown"):
        findings.add((code, ref, detail, severity))

    def follow(name, ref):
        top = name.split(".")[0]
        # Local shadowing must be checked before recognizing a stdlib import.
        if top in STDLIB | {"pytest", "__future__"} and top in modules:
            issue("runner_or_stdlib_shadowed", ref, top, "blocked")
        if name in modules:
            edges.add((ref, name))
            pending.add(name)
        elif top in STDLIB | {"__future__"}:
            stdlib.add(name)
        else:
            issue("unresolved_or_external_import", ref, name)

    while pending:
        name = min(pending)
        pending.remove(name)
        if name in visited:
            continue
        visited.add(name)
        if len(visited) > MAX_MODULES:
            issue("closure_module_budget_exceeded", "", severity="blocked")
            break
        refs = modules.get(name, [])
        if len(refs) != 1:
            issue("missing_or_ambiguous_module", "", name, "blocked")
            continue
        ref = refs[0]
        selected[ref] = files[ref]
        if PurePosixPath(ref).name == "conftest.py" or any(
            part in {"tests", "test"} for part in PurePosixPath(ref).parts[:-1]
        ):
            issue("test_bootstrap_in_runtime_closure", ref, severity="blocked")
        parts = name.split(".")
        for index in range(1, len(parts)):
            parent = ".".join(parts[:index])
            expected = prefix + "/".join(parts[:index]) + "/__init__.py"
            if modules.get(parent) != [expected]:
                issue("namespace_or_ambiguous_package", ref, parent, "blocked")
            else:
                pending.add(parent)
                edges.add((ref, parent))
        if parts[0] in STDLIB | {"pytest", "__future__"}:
            issue("runner_or_stdlib_shadowed", ref, parts[0], "blocked")
        try:
            tree = ast.parse(files[ref])
        except (SyntaxError, UnicodeError, ValueError, RecursionError):
            issue("unparseable_closure_module", ref, severity="blocked")
            continue
        nodes = []
        for node in ast.walk(tree):
            nodes.append(node)
            if len(nodes) > MAX_AST_NODES:
                break
        total_nodes += len(nodes)
        if len(nodes) > MAX_AST_NODES or total_nodes > 250000:
            issue("closure_ast_budget_exceeded", ref, severity="blocked")
            break
        package = parts if ref.endswith("/__init__.py") else parts[:-1]
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    follow(alias.name, ref)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if node.level > len(package):
                        issue("relative_import_outside_package", ref, severity="blocked")
                        continue
                    base = package[: len(package) - node.level + 1]
                    name_from = ".".join(base + ([node.module] if node.module else []))
                else:
                    name_from = node.module or ""
                follow(name_from, ref)
                for alias in node.names:
                    if alias.name == "*":
                        issue("wildcard_import_requires_review", ref, name_from)
                    # from p import child may initialize a module, even if it is
                    # also exported as an attribute. Include both possibilities.
                    child = name_from + "." + alias.name
                    if child in modules:
                        follow(child, ref)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imported = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                if any(x.split(".")[0] in {"importlib", "pkgutil", "runpy"} for x in imported):
                    issue("dynamic_import_framework_requires_review", ref)
            if isinstance(node, ast.Call):
                called = ast.unparse(node.func)
                if called.split(".")[-1] in {
                    "exec",
                    "eval",
                    "compile",
                    "__import__",
                    "import_module",
                    "exec_module",
                    "load_module",
                    "extend_path",
                    "declare_namespace",
                    "getattr",
                    "setattr",
                }:
                    issue("dynamic_code_or_lookup_requires_review", ref)
                if called.split(".")[-1] in {
                    "open",
                    "read_text",
                    "read_bytes",
                    "files",
                    "get_data",
                    "CDLL",
                    "PyDLL",
                }:
                    issue("resource_or_native_access_requires_review", ref)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == (
                "__getattr__"
            ):
                issue("module_lookup_hook_requires_review", ref)
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)) and any(
                (isinstance(child, ast.Name) and child.id == "__path__")
                or (
                    isinstance(child, ast.Attribute)
                    and child.attr in {"path", "meta_path", "path_hooks", "modules"}
                )
                for child in ast.walk(node)
            ):
                issue("import_state_mutation_requires_review", ref)
    return {
        "status": "blocked"
        if any(x[3] == "blocked" for x in findings)
        else "unknown"
        if findings
        else "review_required",
        "algorithm": "module-import-closure.v1",
        "files": [
            {"path": ref, "content_digest": digest_bytes(body)}
            for ref, body in sorted(selected.items())
        ],
        "import_edges": [{"from_ref": ref, "to_module": name} for ref, name in sorted(edges)],
        "stdlib_imports": sorted(stdlib),
        "findings": [
            dict(zip(("code", "path", "detail", "severity"), item, strict=True))
            for item in sorted(findings)
        ],
        "claim": "Proposed module input set, not proof of dependency completeness or safety. "
        "All imports in visited modules are considered, including conditional/function imports. "
        "Dynamic aliases, arbitrary Python effects and resource use require human review.",
    }


def plan_bootstrap(
    repo: Path,
    revision: str,
    *,
    target: str,
    import_root: str,
    test_ref: str,
    test_function: str,
    output: Path,
    cwd: Path | None = None,
) -> dict:
    """Publish a fresh review plan from one committed tree; never start a runner."""
    if target.count(":") != 1:
        raise ValueError("Use a module:symbol target")
    module, symbol = target.split(":")
    TypeAdapter(Module).validate_python(module)
    TypeAdapter(Symbol).validate_python(symbol)
    TypeAdapter(Symbol).validate_python(test_function)
    TypeAdapter(RepositoryPath).validate_python(test_ref)
    if import_root not in {".", "src"} or not test_function.startswith("test_"):
        raise ValueError("Select .|src and one test_* function")
    cwd = (cwd or Path.cwd()).resolve(strict=True)
    output = output if output.is_absolute() else cwd / output
    reject_links(output)
    output = output.resolve()
    if not output.is_relative_to(cwd) or output == cwd or output.is_relative_to(repo.resolve()):
        raise ValueError("Plan output must be below cwd and outside target repository")
    if output.exists():
        raise ArtifactIntegrityError("Plan output exists; choose a new plan ID")
    commit, files, pins = read_committed_files(repo, revision)
    if test_ref not in files:
        raise ValueError("Selected test must exist in the committed tree")
    closure = inspect_target_closure(files, module=module, import_root=import_root)
    projection = project_test(
        files[test_ref],
        test_function=test_function,
        target_module=module,
        target_symbol=symbol,
    )
    # The whole-tree check keeps its own conservative semantics. Nothing here
    # converts its rejected/unknown inputs into permission to execute a subset.
    repository = assess_minimal_python(files, import_root=import_root)
    selected_refs = {item["path"] for item in closure["files"]}
    pinned = {pin.path: pin for pin in pins}
    bootstrap = describe_bootstrap_files(files, selected_refs)
    payload = {
        "schema_version": "bootstrap-plan.v1",
        "status": "blocked"
        if closure["status"] == "blocked" or not projection["cases"]
        else "unknown"
        if closure["status"] == "unknown"
        else "review_required",
        "requested_revision": revision,
        "commit": commit,
        "target": target,
        "import_root": import_root,
        "test_ref": test_ref,
        "test_function": test_function,
        "source_selection": "complete_committed_tree_only",
        "files": [pin.model_dump(mode="json") for pin in sorted(pins, key=lambda p: p.path)],
        "proposed_runtime_pins": [
            pinned[ref].model_dump(mode="json") for ref in sorted(selected_refs)
        ],
        "target_closure": closure,
        "test_projection": {
            **projection,
            "test_digest": digest_bytes(files[test_ref]),
            "test_object_id": pinned[test_ref].object_id,
        },
        "upstream_test_environment": {
            "bootstrap_files": bootstrap,
            "whole_tree_assessment": repository,
        },
        "human_review_required": True,
        "execution_allowed": False,
        "verify_supported": False,
        "execution_outcome": "not_run",
        "upstream_tests_selected_for_execution": False,
        "missing_capabilities": [
            "generic_owner_head_contract",
            "generic_docker_capture",
            "generic_guard_provenance_and_scope",
        ],
        "next_action": "Review target/package initializer imports, resources, every projected "
        "oracle and unsupported assertion. A standalone Guard may avoid upstream test bootstrap "
        "only after separate closure review and implemented isolated Docker capture. "
        "Do not run upstream tests or register this plan. Final contract must be committed "
        "by the owner to assertion head; this plan is neither that contract nor authorization.",
        "implementation_digests": inspection_implementation_digests(),
    }
    payload["artifact_digest"] = digest_json_artifact(payload)
    value = json.loads(canonical_json_bytes(payload))
    write_immutable(output / "plan.json", canonical_json_bytes(value))
    return value
