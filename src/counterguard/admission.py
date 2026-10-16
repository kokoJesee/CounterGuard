"""Read-only classification of the narrow no-install/no-plugin engineering profile.

This is deliberately a static candidate check, never a runtime authorization or a
proof that arbitrary Python cannot hide imports. It does not change preflight.v1.
"""

import ast
import re
import sys
import tomllib
from pathlib import Path, PurePosixPath

from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import digest_json_artifact
from counterguard.preflight import inspect_execution_requirements
from counterguard.repository import RepositoryProblem, read_committed_files

PROFILE = "minimal-python.v1"
# Exclude platform-specific/removed modules; the target runner is Linux Python 3.13.
STDLIB = frozenset(
    [
        "abc",
        "argparse",
        "array",
        "ast",
        "asyncio",
        "atexit",
        "base64",
        "binascii",
        "bisect",
        "builtins",
        "bz2",
        "calendar",
        "cmath",
        "codecs",
        "collections",
        "colorsys",
        "concurrent",
        "contextlib",
        "contextvars",
        "copy",
        "copyreg",
        "csv",
        "ctypes",
        "dataclasses",
        "datetime",
        "decimal",
        "difflib",
        "dis",
        "email",
        "enum",
        "errno",
        "faulthandler",
        "fcntl",
        "filecmp",
        "fileinput",
        "fnmatch",
        "fractions",
        "functools",
        "gc",
        "getopt",
        "getpass",
        "gettext",
        "glob",
        "graphlib",
        "gzip",
        "hashlib",
        "heapq",
        "hmac",
        "html",
        "http",
        "importlib",
        "inspect",
        "io",
        "ipaddress",
        "itertools",
        "json",
        "keyword",
        "linecache",
        "locale",
        "logging",
        "lzma",
        "math",
        "mimetypes",
        "mmap",
        "multiprocessing",
        "numbers",
        "operator",
        "os",
        "pathlib",
        "pickle",
        "pickletools",
        "pkgutil",
        "platform",
        "plistlib",
        "pprint",
        "profile",
        "pstats",
        "pty",
        "pwd",
        "py_compile",
        "queue",
        "random",
        "re",
        "reprlib",
        "resource",
        "rlcompleter",
        "runpy",
        "sched",
        "secrets",
        "select",
        "selectors",
        "shelve",
        "shlex",
        "shutil",
        "signal",
        "site",
        "socket",
        "socketserver",
        "sqlite3",
        "ssl",
        "stat",
        "statistics",
        "string",
        "stringprep",
        "struct",
        "subprocess",
        "sys",
        "sysconfig",
        "tarfile",
        "tempfile",
        "textwrap",
        "threading",
        "time",
        "timeit",
        "tkinter",
        "token",
        "tokenize",
        "tomllib",
        "trace",
        "traceback",
        "tracemalloc",
        "tty",
        "types",
        "typing",
        "unicodedata",
        "unittest",
        "urllib",
        "uuid",
        "venv",
        "warnings",
        "wave",
        "weakref",
        "webbrowser",
        "xml",
        "xmlrpc",
        "zipapp",
        "zipfile",
        "zipimport",
        "zlib",
        "zoneinfo",
    ]
) - {"tkinter"}  # Not supplied by the reviewed slim runner.
PREREQUISITES = {
    "layout": "1_import_layout",
    "plugins": "2_controlled_pytest_bootstrap",
    "dependencies": "3_controlled_dependency_installation",
    "guard": "4_repository_guard",
}
NEXT = {
    "layout": "Provide a reviewed root/src import mapping and complete local import closure.",
    "plugins": "Plugin/fixture execution is unsupported. Supply a reviewed standalone contract "
    "independent of it; otherwise wait for controlled pytest bootstrap. No bypass flag exists.",
    "dependencies": "Dependency installation is unsupported. Supply a genuinely self-contained "
    "reviewed target/contract closure or wait for locked offline dependency installation. "
    "Do not delete declarations to pass this check.",
    "guard": "Supply a source-controlled contract, real buggy/fixed commits, verified Evidence "
    "and a reviewed exact-snapshot Scope. Generic Docker bootstrap is not implemented.",
}


def _test_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Only literal built-in parametrization can discharge a test function argument."""
    names = set()
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call) or ast.unparse(decorator.func) != (
            "pytest.mark.parametrize"
        ):
            continue
        if len(decorator.args) < 2 or decorator.keywords:
            continue
        try:
            labels = ast.literal_eval(decorator.args[0])
            ast.literal_eval(decorator.args[1])
        except (ValueError, TypeError, SyntaxError, RecursionError):
            continue
        labels = labels.split(",") if isinstance(labels, str) else labels
        if isinstance(labels, (list, tuple)) and all(isinstance(x, str) for x in labels):
            names.update(x.strip() for x in labels)
    return names


def assess_minimal_python(files: dict[str, bytes], *, import_root: str) -> dict:
    if import_root not in {".", "src"}:
        raise ValueError("Use --import-root . or src")
    requirements = inspect_execution_requirements(
        files, pytest_version="9.0.3", import_root=import_root
    )
    findings = []

    def add(code, path, group, severity="blocked"):
        findings.append(
            {
                "code": code,
                "path": path,
                "severity": severity,
                "prerequisite": PREREQUISITES[group],
                "next_step": NEXT[group],
            }
        )

    for item in requirements["findings"]:
        code = item["code"]
        group = (
            "dependencies"
            if "dependenc" in code or "install" in code
            else "plugins"
            if any(x in code for x in ("pytest", "conftest", "test_config"))
            else "layout"
        )
        add(code, item["path"], group, item["severity"])

    try:
        project = tomllib.loads(files.get("pyproject.toml", b"").decode()).get("project", {})
        constraint = project.get("requires-python")
        if constraint is not None:
            for term in constraint.split(","):
                match = re.fullmatch(r"\s*(>=|<=|!=|==|>|<)\s*(\d+(?:\.\d+){0,2})\s*", term)
                if not match:
                    add(
                        "python_version_constraint_requires_review",
                        "pyproject.toml",
                        "layout",
                        "unknown",
                    )
                    break
                op, version = match.groups()
                parts = tuple(int(x) for x in version.split("."))
                required = parts + (0,) * (3 - len(parts))
                runner_python = (3, 13, 16)  # Both current reviewed profiles; not host Python.
                compatible = {
                    ">=": runner_python >= required,
                    "<=": runner_python <= required,
                    ">": runner_python > required,
                    "<": runner_python < required,
                    "==": runner_python == required,
                    "!=": runner_python != required,
                }[op]
                if not compatible:
                    add("declared_python_version_excludes_runner", "pyproject.toml", "layout")
    except (ValueError, TypeError, AttributeError, UnicodeError):
        add("project_metadata_requires_review", "pyproject.toml", "layout", "unknown")

    prefix = "" if import_root == "." else "src/"
    modules = set()
    python = {}
    for ref, body in sorted(files.items()):
        path = PurePosixPath(ref)
        if path.suffix.lower() in {".so", ".pyd", ".dll", ".dylib", ".pyx"}:
            add("native_code_outside_profile", ref, "dependencies")
        if path.name == "pyproject.toml" and ref != "pyproject.toml":
            add("nested_project_requires_separate_review", ref, "layout", "unknown")
        if path.suffix != ".py":
            continue
        try:
            python[ref] = ast.parse(body)
        except (SyntaxError, ValueError, UnicodeError, RecursionError):
            add("unparseable_python", ref, "layout", "unknown")
            continue
        if not ref.startswith(prefix) or "tests" in path.parts or path.name.startswith("test_"):
            continue
        relative = ref[len(prefix) :]
        parts = PurePosixPath(relative).parts
        # Only regular packages or top-level modules, no namespace/import hooks.
        if not all(
            (prefix + "/".join(parts[:i]) + "/__init__.py") in files for i in range(1, len(parts))
        ):
            add("namespace_or_unmapped_package", ref, "layout", "unknown")
            continue
        module = relative[:-3].replace("/", ".")
        if any(not part.isidentifier() for part in module.split(".")):
            add("invalid_module_path", ref, "layout", "unknown")
        if module.split(".")[0] in STDLIB | {"pytest"}:
            add("runner_or_stdlib_module_shadowed", ref, "layout", "unknown")
        modules.add(module.removesuffix(".__init__"))
    if not modules:
        add("no_source_at_declared_import_root", import_root, "layout", "unknown")

    for ref, tree in python.items():
        path = PurePosixPath(ref)
        is_test = any(part in {"test", "tests"} for part in path.parts) or (
            path.name.startswith("test_") or path.name.endswith("_test.py")
        )
        relative = ref[len(prefix) :] if ref.startswith(prefix) else ref
        package = relative[:-3].split("/")[:-1]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
                if any(
                    alias.name == "pytest" and alias.asname not in {None, "pytest"}
                    for alias in node.names
                ):
                    add("pytest_alias_requires_bootstrap_review", ref, "plugins", "unknown")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "pytest" and any(
                    alias.name not in {"raises", "approx"} for alias in node.names
                ):
                    add("pytest_api_requires_bootstrap_review", ref, "plugins", "unknown")
                if node.level:
                    if node.level > len(package):
                        add("unresolved_relative_import", ref, "layout", "unknown")
                        continue
                    imports = [
                        ".".join(
                            package[: len(package) - node.level + 1]
                            + ([node.module] if node.module else [])
                        )
                    ]
                else:
                    imports = [node.module or ""]
            else:
                imports = []
            for name in imports:
                top = name.split(".")[0]
                if top in {"importlib", "runpy"}:
                    add("dynamic_import_framework_requires_review", ref, "layout", "unknown")
                if name in modules or top in STDLIB or top == "__future__":
                    continue
                if is_test and name == "pytest":
                    continue
                add("unresolved_or_third_party_import", ref, "dependencies", "unknown")
            if isinstance(node, ast.Call):
                called = ast.unparse(node.func)
                if called in {"exec", "eval", "__import__"} or called.endswith(
                    (
                        ".import_module",
                        ".exec_module",
                        ".load_module",
                        ".spec_from_file_location",
                        ".__import__",
                        ".exec",
                        ".eval",
                        ".run_module",
                        ".run_path",
                    )
                ):
                    add("dynamic_import_or_code_requires_review", ref, "layout", "unknown")
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if (node.value.id, node.attr) in {
                    ("sys", "path"),
                    ("sys", "meta_path"),
                    ("sys", "path_hooks"),
                }:
                    add("custom_import_path_requires_review", ref, "layout", "unknown")
                if (
                    is_test
                    and node.value.id == "pytest"
                    and node.attr not in {"mark", "raises", "approx"}
                ):
                    add("pytest_api_requires_bootstrap_review", ref, "plugins", "unknown")
            if (
                is_test
                and isinstance(node, ast.Attribute)
                and (
                    isinstance(node.value, ast.Attribute)
                    and ast.unparse(node.value) == "pytest.mark"
                    and node.attr != "parametrize"
                )
            ):
                add("test_mark_requires_review", ref, "plugins", "unknown")
            if is_test and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith(("pytest_", "setup_", "teardown_")):
                    add("test_hook_requires_bootstrap_review", ref, "plugins")
                if node.name.startswith("test_"):
                    args = node.args
                    actual = {arg.arg for arg in args.posonlyargs + args.args + args.kwonlyargs}
                    if actual - _test_parameters(node) or args.vararg or args.kwarg:
                        add("test_fixture_or_nonliteral_parametrization", ref, "plugins", "unknown")
                    if isinstance(node, ast.AsyncFunctionDef):
                        add("async_test_requires_plugin_review", ref, "plugins", "unknown")
                    for decorator in node.decorator_list:
                        func = decorator.func if isinstance(decorator, ast.Call) else decorator
                        if ast.unparse(func) != "pytest.mark.parametrize":
                            add("test_decorator_requires_review", ref, "plugins", "unknown")
    unique = {(x["code"], x["path"], x["prerequisite"]): x for x in findings}
    findings = [unique[key] for key in sorted(unique)]
    status = (
        "blocked"
        if any(x["severity"] == "blocked" for x in findings)
        else ("unknown" if findings else "eligible_candidate")
    )
    return {
        "status": status,
        "findings": findings,
        "import_root": import_root,
        "local_modules": sorted(modules),
        "runtime_dependencies": requirements["runtime_dependencies"],
        "warnings": requirements["warnings"],
        "engineering_prerequisites": [PREREQUISITES["layout"], PREREQUISITES["guard"]],
        "verify_supported": False,
        "next_step": NEXT["guard"]
        if not findings
        else "Resolve each finding; rerun on a new commit.",
        "claim": "Static no-install/no-plugin candidate only, not a proof of dependency "
        "completeness, test semantics, Scope, generic verify support or execution permission.",
        "scanner_python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }


def admission_repository(repo: str | Path, revision: str, *, import_root: str) -> dict:
    commit, files, pins = None, {}, ()
    try:
        commit, files, pins = read_committed_files(repo, revision)
        assessment = assess_minimal_python(files, import_root=import_root)
    except RepositoryProblem as error:
        assessment = {
            "status": "rejected" if error.rejected else "unknown",
            "findings": [{"code": error.code, "path": None}],
            "verify_supported": False,
        }
    except (OSError, ValueError, UnicodeError, RecursionError):
        assessment = {
            "status": "unknown",
            "findings": [{"code": "admission_unavailable"}],
            "verify_supported": False,
        }
    guidance = admission_user_guidance(
        assessment["status"], finding_codes={item["code"] for item in assessment["findings"]}
    )
    report = {
        "schema_version": "repository-admission.v2",
        "profile": PROFILE,
        "requested_revision": revision,
        "commit": commit,
        "source_selection": "complete_committed_tree_only",
        "execution_allowed": False,
        "execution_outcome": "not_run",
        "file_count": len(files),
        "files": [pin.model_dump(mode="json") for pin in pins],
        "implementation_digests": inspection_implementation_digests(),
        **assessment,
        "user_guidance": guidance,
        "next_step": guidance["next_action"],
    }
    report["artifact_digest"] = digest_json_artifact(report)
    return report


def admission_user_guidance(status: str, *, finding_codes=()) -> dict:
    """Product support is separate from a static tree's compatibility findings."""
    if set(finding_codes).intersection({"repository_unavailable", "admission_unavailable"}):
        action = (
            "Repository data could not be read. Check the clone, complete commit history and "
            "local read/snapshot permissions, then rerun this read-only command. This result "
            "has not classified project compatibility and cannot authorize execution."
        )
    elif status == "eligible_candidate":
        action = (
            "This is a static candidate, not a supported new-project verify profile. "
            "Use contract draft to prepare review-only test material. Only use verify if your "
            "project already satisfies an explicitly supported profile; otherwise wait for "
            "maintainer implementation and review of generic Docker bootstrap."
        )
    elif status == "rejected":
        action = (
            "Stop before execution. Resolve the Git/path integrity rejection and rerun this "
            "read-only check. Do not use local capture to bypass it."
        )
    else:
        action = (
            "Read each finding's next_step. Supply missing metadata or an audited target/test "
            "mapping for review; required dependency or fixture support is currently unavailable. "
            "Even clearing findings does not implement generic bootstrap. Use an already "
            "supported profile or wait for tool support; choosing a simpler project "
            "is not a guarantee."
        )
    return {
        "current_support": "generic_project_verify_not_supported",
        "user_can_enable_verify": False,
        "next_action": action,
        "maintainer_action": "Implement and audit import closure plus generic repository "
        "contract/Guard capture; engineering_prerequisites are internal work, not user steps.",
        "eta": None,
        "tracking_url": "https://github.com/kokoJesee/CounterGuard/blob/main/docs/roadmap.md",
        "notification": "No feature-specific subscription or promised date; GitHub Watch can "
        "follow repository updates. This command does not schedule notifications.",
    }
