"""Reconstruct B/F/H provenance; never execute or install candidate code."""

import ast
import configparser
import json
import tomllib
from pathlib import Path

from pydantic import TypeAdapter

from counterguard.artifacts import write_immutable
from counterguard.bootstrap_plan import describe_bootstrap_files, inspect_target_closure
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.contract_draft import project_test
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.project_config import Module, RepositoryPath, Symbol, reject_links
from counterguard.repository import RepositoryProblem, read_commit_metadata, read_committed_files
from counterguard.standalone_contracts import (
    CONTRACT_LIMIT,
    CommitId,
    ContractId,
    StandaloneContract,
    StandaloneTestOrigin,
    read_standalone_contract,
    strict_json,
)

BINDING_LIMIT = 4 * 1024 * 1024


class BindingProblem(ArtifactIntegrityError):
    """A finite reason code; never emit target-controlled exception text."""


def _require(condition, code):
    if not condition:
        raise BindingProblem(code)


def _new_output(repo: Path, output: Path, cwd: Path | None) -> Path:
    cwd = (cwd or Path.cwd()).resolve(strict=True)
    output = output if output.is_absolute() else cwd / output
    reject_links(output)
    output = output.resolve()
    if not output.is_relative_to(cwd) or output == cwd or output.is_relative_to(repo.resolve()):
        raise ValueError("Output must be below cwd and outside target repository")
    if output.exists():
        raise ArtifactIntegrityError("Output exists; choose a new binding/preparation ID")
    return output


def _read_tree(repo, revision):
    TypeAdapter(CommitId).validate_python(revision)
    actual, files, pins = read_committed_files(repo, revision)
    _require(actual == revision, "commit_resolution_mismatch")
    return files, tuple(sorted(pins, key=lambda pin: pin.path))


def _metadata(repo, revision):
    value = read_commit_metadata(repo, revision)
    _require(value["commit"] == revision, "commit_metadata_mismatch")
    return value


def _projection(files, pins, *, test_ref, test_function, module, symbol):
    _require(test_ref in files, "fixed_test_missing")
    try:
        fragments = project_test(
            files[test_ref],
            test_function=test_function,
            target_module=module,
            target_symbol=symbol,
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise BindingProblem("fixed_test_projection_unavailable") from error
    _require(bool(fragments["cases"]), "fixed_test_has_no_supported_cases")
    origin = StandaloneTestOrigin(
        test_ref=test_ref,
        test_function=test_function,
        test_object_id=next(pin.object_id for pin in pins if pin.path == test_ref),
        test_digest=digest_bytes(files[test_ref]),
        projection_digest=digest_json_artifact(fragments),
    )
    return origin, fragments


def _runtime_assessment(files, contract):
    closure = inspect_target_closure(
        files,
        module=contract.target_module,
        import_root=contract.import_root,
    )
    findings = list(closure["findings"])

    def add(code, path, severity="unknown"):
        findings.append({"code": code, "path": path, "detail": "", "severity": severity})

    # This new source-only profile accepts PEP 621's static omitted dependencies.
    # It does not silently relax minimal-python.v1's explicit-empty policy.
    try:
        metadata = tomllib.loads(files.get("pyproject.toml", b"").decode())
        project = metadata.get("project")
        if not isinstance(project, dict) or not isinstance(project.get("name"), str):
            add("project_metadata_unavailable", "pyproject.toml")
        elif "dependencies" in project.get("dynamic", []):
            add("dynamic_runtime_dependencies", "pyproject.toml")
        elif not isinstance(project.get("dependencies", []), list):
            add("invalid_runtime_dependencies", "pyproject.toml")
        elif project.get("dependencies", []):
            add("runtime_dependency_installation_required", "pyproject.toml", "blocked")
    except (ValueError, UnicodeError, TypeError, AttributeError):
        add("project_metadata_unavailable", "pyproject.toml")
    if "setup.py" in files:
        add("legacy_install_code_requires_review", "setup.py")
    if "setup.cfg" in files:
        try:
            config = configparser.ConfigParser(interpolation=None)
            config.read_string(files["setup.cfg"].decode())
            if config.get("options", "install_requires", fallback="").strip():
                add("legacy_runtime_dependencies_require_review", "setup.cfg")
        except (configparser.Error, UnicodeError, ValueError):
            add("legacy_metadata_requires_review", "setup.cfg")
    try:
        tree = ast.parse(files[contract.source_ref])
        declarations = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == contract.target_symbol
        ]
        if len(declarations) != 1:
            add("target_binding_requires_review", contract.source_ref)
        elif declarations[0].decorator_list:
            add("target_decorators_require_review", contract.source_ref)
    except (KeyError, SyntaxError, UnicodeError, ValueError, RecursionError):
        add("target_binding_requires_review", contract.source_ref)
    closure["findings"] = sorted(
        findings,
        key=lambda item: (
            item["code"],
            item["path"],
            item["detail"],
            item["severity"],
        ),
    )
    closure["status"] = (
        "blocked"
        if any(x["severity"] == "blocked" for x in findings)
        else ("unknown" if findings else "review_required")
    )
    return closure


def prepare_contract(
    repo: Path,
    *,
    buggy: str,
    fixed: str,
    contract_id: str,
    target: str,
    import_root: str,
    test_ref: str,
    test_function: str,
    output: Path,
    cwd: Path | None = None,
) -> dict:
    """Prepare all supported cases; owner review/commit is a separate user action."""
    TypeAdapter(ContractId).validate_python(contract_id)
    TypeAdapter(CommitId).validate_python(buggy)
    TypeAdapter(CommitId).validate_python(fixed)
    TypeAdapter(RepositoryPath).validate_python(test_ref)
    TypeAdapter(Symbol).validate_python(test_function)
    if target.count(":") != 1 or import_root not in {".", "src"}:
        raise ValueError("Select module:symbol and .|src import root")
    module, symbol = target.split(":")
    TypeAdapter(Module).validate_python(module)
    TypeAdapter(Symbol).validate_python(symbol)
    output = _new_output(repo, output, cwd)
    buggy_files, _ = _read_tree(repo, buggy)
    files, pins = _read_tree(repo, fixed)
    _require(_metadata(repo, fixed)["parents"] == (buggy,), "fix_must_have_one_buggy_parent")
    origin, fragments = _projection(
        files, pins, test_ref=test_ref, test_function=test_function, module=module, symbol=symbol
    )
    closure = inspect_target_closure(files, module=module, import_root=import_root)
    _require(closure["status"] != "blocked", "fixed_closure_is_blocked")
    buggy_closure = inspect_target_closure(buggy_files, module=module, import_root=import_root)
    prefix = "" if import_root == "." else "src/"
    stem = prefix + module.replace(".", "/")
    candidates = [ref for ref in (stem + ".py", stem + "/__init__.py") if ref in files]
    _require(len(candidates) == 1, "target_source_is_ambiguous")
    contract = StandaloneContract(
        contract_id=contract_id,
        buggy_commit=buggy,
        fixed_commit=fixed,
        target_module=module,
        target_symbol=symbol,
        source_ref=candidates[0],
        import_root=import_root,
        runtime_refs=tuple(
            sorted({item["path"] for value in (closure, buggy_closure) for item in value["files"]})
        ),
        test_origin=origin,
        cases=tuple(sorted(fragments["cases"], key=lambda case: case.case_id)),
    )
    contract_raw = canonical_json_bytes(contract)
    _require(len(contract_raw) <= CONTRACT_LIMIT, "prepared_contract_byte_budget_exceeded")
    report = {
        "schema_version": "contract-preparation.v1",
        "contract_digest": digest_bytes(contract_raw),
        "buggy_commit": buggy,
        "fixed_commit": fixed,
        "runtime_assessment": _runtime_assessment(files, contract),
        "buggy_runtime_assessment": _runtime_assessment(buggy_files, contract),
        "projection_coverage": fragments,
        "human_review_required": True,
        "execution_allowed": False,
        "next_action": "Review literals, oracles, source closure and unsupported assertions. "
        "Owner must add this contract alone in a new child commit H of fixed. "
        "Then run bootstrap bind against H; no capture or execution is enabled.",
        "implementation_digests": inspection_implementation_digests(),
    }
    report["artifact_digest"] = digest_json_artifact(report)
    write_immutable(output / "contract.json", contract_raw)
    write_immutable(output / "preparation.json", canonical_json_bytes(report))
    return json.loads(canonical_json_bytes(report))


def rebuild_binding(repo: Path, head: str, contract_ref: str) -> dict:
    """Pure provenance reconstruction from bounded Git reads, no local checkout."""
    head_files, head_pins = _read_tree(repo, head)
    _require(contract_ref in head_files, "contract_missing_from_head")
    try:
        contract = read_standalone_contract(head_files[contract_ref])
    except (ValueError, UnicodeError, RecursionError) as error:
        raise BindingProblem("invalid_standalone_contract") from error
    fixed_files, fixed_pins = _read_tree(repo, contract.fixed_commit)
    buggy_files, buggy_pins = _read_tree(repo, contract.buggy_commit)
    _require(
        _metadata(repo, contract.fixed_commit)["parents"] == (contract.buggy_commit,),
        "fix_must_have_one_buggy_parent",
    )
    _require(
        _metadata(repo, head)["parents"] == (contract.fixed_commit,),
        "head_must_be_contract_child_of_fixed",
    )
    _require(
        set(head_files) - set(fixed_files) == {contract_ref}
        and all(head_files.get(ref) == body for ref, body in fixed_files.items()),
        "owner_head_must_only_add_contract",
    )
    _require(contract_ref not in contract.runtime_refs, "contract_cannot_be_runtime_source")
    origin, fragments = _projection(
        fixed_files,
        fixed_pins,
        test_ref=contract.test_origin.test_ref,
        test_function=contract.test_origin.test_function,
        module=contract.target_module,
        symbol=contract.target_symbol,
    )
    _require(origin == contract.test_origin, "test_origin_or_projection_mismatch")
    expected = tuple(sorted(fragments["cases"], key=lambda case: case.case_id))
    _require(contract.cases == expected, "contract_cases_differ_from_fixed_test")
    assessments = {}
    refs = set()
    for role, files in (("buggy", buggy_files), ("fixed", fixed_files), ("head", head_files)):
        assessment = _runtime_assessment(files, contract)
        assessments[role] = assessment
        refs.update(item["path"] for item in assessment["files"])
        _require(contract.source_ref in files, "target_source_missing_from_revision")
    _require(tuple(sorted(refs)) == contract.runtime_refs, "runtime_closure_union_mismatch")
    _require(
        any(buggy_files.get(ref) != fixed_files.get(ref) for ref in contract.runtime_refs),
        "runtime_sources_did_not_change",
    )
    # Pins include role-specific missing files implicitly: do not copy a newly
    # introduced F module into B or pretend all trees have an identical closure.
    role_status = {value["status"] for value in assessments.values()}
    status = (
        "blocked"
        if "blocked" in role_status
        else ("unknown" if "unknown" in role_status else "review_required")
    )
    payload = {
        "schema_version": "bootstrap-binding.v1",
        "binding_status": "sources_verified",
        "head_commit": head,
        "contract_ref": contract_ref,
        "contract_digest": digest_bytes(head_files[contract_ref]),
        "contract": contract.model_dump(mode="json"),
        "history_profile": "linear-fix-and-contract-only-child.v1",
        "trees": {
            role: {"commit": revision, "files": [pin.model_dump(mode="json") for pin in pins]}
            for role, revision, pins in (
                ("buggy", contract.buggy_commit, buggy_pins),
                ("fixed", contract.fixed_commit, fixed_pins),
                ("head", head, head_pins),
            )
        },
        "file_origins": {
            ref: {
                "origin": "assertion_head_contract" if ref == contract_ref else "fixed_tree",
                "commit": head if ref == contract_ref else contract.fixed_commit,
                "content_digest": digest_bytes(body),
            }
            for ref, body in sorted(head_files.items())
        },
        "runtime_assessments": assessments,
        "test_environment_observations": {
            role: describe_bootstrap_files(
                files, {item["path"] for item in assessments[role]["files"]}
            )
            for role, files in (
                ("buggy", buggy_files),
                ("fixed", fixed_files),
                ("head", head_files),
            )
        },
        "capture_input_status": status,
        "projection_coverage": fragments,
        "execution_allowed": False,
        "capture_available": False,
        "execution_outcome": "not_run",
        "reproduced": None,
        "semantic_review_required": True,
        "ownership_authentication": "not_provided_by_git_object_integrity",
        "next_action": "Review source/oracle independence and every runtime finding. "
        "Generic Docker capture, Evidence/Guard verification and Scope remain unimplemented. "
        "This binding is not an execution authorization or proof that buggy fails.",
        "implementation_digests": inspection_implementation_digests(),
    }
    payload["artifact_digest"] = digest_json_artifact(payload)
    _require(len(canonical_json_bytes(payload)) <= BINDING_LIMIT, "binding_byte_budget_exceeded")
    return json.loads(canonical_json_bytes(payload))


def bind_contract(
    repo: Path, head: str, contract_ref: str, *, output: Path, cwd: Path | None = None
) -> dict:
    TypeAdapter(CommitId).validate_python(head)
    TypeAdapter(RepositoryPath).validate_python(contract_ref)
    output = _new_output(repo, output, cwd)
    try:
        value = rebuild_binding(repo, head, contract_ref)
    except (BindingProblem, RepositoryProblem) as error:
        value = {
            "schema_version": "bootstrap-binding-failure.v1",
            "binding_status": "rejected"
            if isinstance(error, BindingProblem) or error.rejected
            else "unknown",
            "head_commit": head,
            "contract_ref": contract_ref,
            "reason_code": str(error) if isinstance(error, BindingProblem) else error.code,
            "execution_allowed": False,
            "execution_outcome": "not_run",
            "implementation_digests": inspection_implementation_digests(),
        }
        value["artifact_digest"] = digest_json_artifact(value)
        write_immutable(output / "binding-failure.json", canonical_json_bytes(value))
        return value
    write_immutable(output / "binding.json", canonical_json_bytes(value))
    return value


def verify_binding(repo: Path, path: Path) -> dict:
    reject_links(path)
    if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > BINDING_LIMIT:
        raise ArtifactIntegrityError("Binding must be a bounded unlinked regular file")
    try:
        value = strict_json(path.read_bytes(), limit=BINDING_LIMIT)
        _require(value.get("schema_version") == "bootstrap-binding.v1", "not_a_source_binding")
        _require(
            value.get("artifact_digest") == digest_json_artifact(value), "binding_digest_mismatch"
        )
        _require(
            value.get("implementation_digests") == inspection_implementation_digests(),
            "binding_implementation_is_stale",
        )
        TypeAdapter(CommitId).validate_python(value.get("head_commit"))
        TypeAdapter(RepositoryPath).validate_python(value.get("contract_ref"))
        rebuilt = rebuild_binding(repo, value["head_commit"], value["contract_ref"])
        _require(value == rebuilt, "binding_does_not_match_committed_sources")
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ArtifactIntegrityError("Malformed binding JSON or fields") from error
    return rebuilt
