"""Rebuild immutable snapshot declarations from Git; separate locally anchored reviews."""

import ast
import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from counterguard.admission import STDLIB
from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.project_config import reject_links, repository_path
from counterguard.repository import read_commit_metadata
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import DockerPolicyV1
from counterguard.snapshot_models import (
    ZERO,
    SnapshotBinding,
    SnapshotContract,
    SnapshotOrigin,
    SnapshotReview,
)
from counterguard.snapshot_projection import project_snapshot_test
from counterguard.snapshot_repository import SNAPSHOT_BUDGET, read_snapshot
from counterguard.standalone_contracts import CONTRACT_LIMIT, strict_json

FIXTURE_REF = "counterguard-fixture.txt"
FIXTURE_MARKER = b"CounterGuard tool-owned research snapshot fixture v1\n"
JSON_LIMIT = 4 * 1024 * 1024


def _compatible_python(text):
    if not isinstance(text, str) or len(text) > 256:
        return False
    for clause in text.split(","):
        match = re.fullmatch(r"\s*(>=|<=|==|!=|>|<)\s*(\d{1,3}(?:\.\d{1,3}){0,2})\s*", clause)
        if not match:
            return False
        op, number = match.groups()
        version = tuple(map(int, number.split(".")))
        version += (0,) * (3 - len(version))
        runner = (3, 13, 16)
        if not {
            ">=": runner >= version,
            "<=": runner <= version,
            ">": runner > version,
            "<": runner < version,
            "==": runner == version,
            "!=": runner != version,
        }[op]:
            return False
    return True


def require(condition, code):
    if not condition:
        raise ArtifactIntegrityError(code)


def seal(value):
    return value.model_copy(update={"artifact_digest": digest_json_artifact(value)})


def read_value(path, model, *, expected_digest=None):
    path = Path(path)
    reject_links(path)
    require(
        path.is_file() and path.stat().st_nlink == 1 and path.stat().st_size <= JSON_LIMIT,
        "snapshot_artifact_must_be_bounded_unlinked_file",
    )
    raw = path.read_bytes()
    strict_json(raw, limit=JSON_LIMIT)
    value = model.model_validate_json(raw)
    require(
        value.artifact_digest == digest_json_artifact(value), "snapshot_artifact_digest_mismatch"
    )
    if expected_digest is not None:
        require(value.artifact_digest == expected_digest, "snapshot_trusted_anchor_mismatch")
    return value


def _projection(files, manifest, *, test_ref, test_function, target_module, target_symbol):
    require(test_ref in files, "snapshot_test_missing")
    result = project_snapshot_test(
        files[test_ref],
        test_function=test_function,
        target_module=target_module,
        target_symbol=target_symbol,
    )
    require(
        not result["unsupported"]
        and result["cases"]
        and result["source_assertions"] == result["represented_assertions"],
        "snapshot_requires_complete_original_projection",
    )
    pin = next(p for p in manifest.files if p.path == test_ref)
    origin = SnapshotOrigin(
        test_ref=test_ref,
        test_function=test_function,
        test_object_id=pin.object_id,
        test_digest=pin.content_digest,
        projection_digest=digest_json_artifact(result),
    )
    return origin, result["cases"]


def _package(files, contract):
    """Whole declared top-level package, including data; no lexical closure claims."""
    prefix = "" if contract.import_root == "." else "src/"
    root = contract.target_module.split(".")[0]
    package = prefix + root
    require(package + "/__init__.py" in files, "snapshot_requires_regular_package")
    refs = tuple(sorted(ref for ref in files if ref.startswith(package + "/")))
    require(contract.source_ref in refs, "snapshot_entry_missing")
    reserved = {"cg_control", "pytest", "sitecustomize", "usercustomize", "conftest"}
    require(root not in reserved | STDLIB, "snapshot_reserved_package")
    for ref in refs:
        parts = Path(ref).parts
        require(
            Path(ref).suffix.casefold() not in {".so", ".pyd", ".dll", ".dylib", ".pyc", ".pyo"},
            "snapshot_native_or_bytecode_input_forbidden",
        )
        require(
            not any(
                part.casefold() in {"conftest.py", "sitecustomize.py", "usercustomize.py"}
                for part in parts
            ),
            "snapshot_package_bootstrap_file_forbidden",
        )
        if ref.endswith(".py"):
            require(len(files[ref]) <= 1024 * 1024, "snapshot_python_ast_byte_budget")
            try:
                tree = ast.parse(files[ref])
            except (ValueError, SyntaxError, UnicodeError, RecursionError) as error:
                raise ArtifactIntegrityError("snapshot_unparseable_python") from error
            require(sum(1 for _ in ast.walk(tree)) <= 50000, "snapshot_python_ast_node_budget")
            for node in ast.walk(tree):
                imports = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                    if isinstance(node, ast.ImportFrom) and not node.level
                    else []
                )
                for name in imports:
                    require(
                        name.split(".")[0] in STDLIB | {root},
                        "snapshot_uninstalled_static_import:" + name,
                    )
    try:
        metadata = tomllib.loads(files.get("pyproject.toml", b"").decode())
        project = metadata["project"]
        require(isinstance(project.get("name"), str), "snapshot_project_metadata_required")
        require(
            isinstance(project.get("dynamic", []), list)
            and "dependencies" not in project.get("dynamic", [])
            and project.get("dependencies", []) == [],
            "snapshot_no_dependency_installation",
        )
        require(
            "setup.py" not in files and "setup.cfg" not in files,
            "snapshot_legacy_install_unsupported",
        )
        # Existing checker, but no original pytest/plugin configuration is executed.
        require(
            _compatible_python(project.get("requires-python")),
            "snapshot_runner_python_requirement_unproven",
        )
    except (KeyError, ValueError, UnicodeError, TypeError, AttributeError) as error:
        raise ArtifactIntegrityError("snapshot_invalid_project_metadata") from error
    return refs


def prepare_snapshot_contract(
    repo,
    *,
    buggy,
    fixed,
    test_ref,
    test_function,
    target_module,
    target_symbol,
    source_ref,
    import_root,
    contract_id,
    output,
    budget=SNAPSHOT_BUDGET,
):
    """Write review-only data. Never create owner H or execute candidate code."""
    manifest, files = read_snapshot(repo, fixed, budget=budget)
    require(
        read_commit_metadata(repo, fixed)["parents"] == (buggy,),
        "snapshot_fix_requires_direct_parent",
    )
    origin, cases = _projection(
        files,
        manifest,
        test_ref=test_ref,
        test_function=test_function,
        target_module=target_module,
        target_symbol=target_symbol,
    )
    contract = SnapshotContract(
        contract_id=contract_id,
        buggy_commit=buggy,
        fixed_commit=fixed,
        target_module=target_module,
        target_symbol=target_symbol,
        source_ref=source_ref,
        import_root=import_root,
        test_origin=origin,
        cases=cases,
    )
    _package(files, contract)
    raw = canonical_json_bytes(contract)
    require(len(raw) <= CONTRACT_LIMIT, "snapshot_contract_budget_exceeded")
    write_immutable(Path(output), raw)
    return contract


def rebuild_snapshot_binding(
    repo, *, head, contract_ref, budget=SNAPSHOT_BUDGET, tool_additions=None
):
    contract_ref = repository_path(contract_ref)
    hm, hf = read_snapshot(repo, head, budget=budget)
    require(contract_ref in hf, "snapshot_contract_missing_from_head")
    strict_json(hf[contract_ref], limit=CONTRACT_LIMIT)
    contract = SnapshotContract.model_validate_json(hf[contract_ref])
    fm, ff = read_snapshot(repo, contract.fixed_commit, budget=budget)
    bm, bf = read_snapshot(repo, contract.buggy_commit, budget=budget)
    require(
        read_commit_metadata(repo, contract.fixed_commit)["parents"] == (contract.buggy_commit,),
        "snapshot_fix_requires_direct_parent",
    )
    require(
        read_commit_metadata(repo, head)["parents"] == (contract.fixed_commit,),
        "snapshot_owner_head_requires_contract_child",
    )
    additions = tuple(sorted(tool_additions or (contract_ref,)))
    require(
        contract_ref.startswith("contracts/")
        and contract_ref.endswith(".json")
        and contract_ref in additions
        and len(set(additions)) == len(additions)
        and all(ref in {contract_ref, "counterguard.yaml"} for ref in additions),
        "snapshot_tool_addition_boundary_invalid",
    )
    require(
        set(hf) - set(ff) == set(additions)
        and all(hf.get(ref) == body for ref, body in ff.items()),
        "snapshot_owner_head_changed_upstream_files",
    )
    origin, cases = _projection(
        ff,
        fm,
        test_ref=contract.test_origin.test_ref,
        test_function=contract.test_origin.test_function,
        target_module=contract.target_module,
        target_symbol=contract.target_symbol,
    )
    require(
        contract.test_origin == origin and contract.cases == cases,
        "snapshot_contract_projection_mismatch",
    )
    refs = {
        role: _package(files, contract)
        for role, files in (("buggy", bf), ("fixed", ff), ("head", hf))
    }
    require(
        any(bf.get(ref) != ff.get(ref) for ref in set(refs["buggy"]) | set(refs["fixed"])),
        "snapshot_package_did_not_change",
    )
    value = SnapshotBinding(
        head_commit=head,
        contract_ref=contract_ref,
        contract_digest=digest_bytes(hf[contract_ref]),
        contract=contract,
        trees={"buggy": bm, "fixed": fm, "head": hm},
        package_refs=refs,
        tool_additions=additions,
        upstream_refs=tuple(sorted(ff)),
        budget=budget,
        implementation_digests=inspection_implementation_digests(),
        artifact_digest=ZERO,
    )
    return seal(value)


def bind_snapshot(repo, *, head, contract_ref, output, budget=SNAPSHOT_BUDGET, tool_additions=None):
    value = rebuild_snapshot_binding(
        repo, head=head, contract_ref=contract_ref, budget=budget, tool_additions=tool_additions
    )
    write_immutable(Path(output), canonical_json_bytes(value))
    return value


def verify_snapshot_binding(repo, path):
    value = read_value(path, SnapshotBinding)
    require(
        value.implementation_digests == inspection_implementation_digests(),
        "snapshot_implementation_stale",
    )
    rebuilt = rebuild_snapshot_binding(
        repo,
        head=value.head_commit,
        contract_ref=value.contract_ref,
        budget=value.budget,
        tool_additions=value.tool_additions,
    )
    require(value == rebuilt, "snapshot_binding_not_reconstructable")
    return value


def issue_snapshot_review(
    repo, binding_path, *, kind, reason, output, runner_id="root-pytest8", timeout=10.0
):
    binding = verify_snapshot_binding(repo, binding_path)
    require(reason.strip(), "snapshot_review_reason_required")
    # A deliberately explicit fixture-only authority. This marker is an operator
    # attestation, not repository ownership authentication or a signature.
    for manifest in binding.trees.values():
        _, files = read_snapshot(repo, manifest.commit, budget=binding.budget)
        require(
            files.get(FIXTURE_REF) == FIXTURE_MARKER, "snapshot_only_tool_owned_fixtures_authorized"
        )
    runner = resolve_runner(runner_id=runner_id, image_digest=None)
    require(runner.profile == "root-pytest8.v1", "snapshot_runner_profile_mismatch")
    review = seal(
        SnapshotReview(
            review_kind=kind,
            created_at=datetime.now(UTC),
            reason=reason,
            binding_digest=binding.artifact_digest,
            runner=runner,
            budget=binding.budget,
            timeout_seconds=timeout,
            policy_digest=digest_json_artifact(DockerPolicyV1()),
            implementation_digests=inspection_implementation_digests(),
            artifact_digest=ZERO,
        )
    )
    write_immutable(Path(output), canonical_json_bytes(review))
    return review


def verify_snapshot_review(repo, binding_path, review_path, *, trusted_digest, kind="execution"):
    require(trusted_digest is not None, "snapshot_independent_trusted_anchor_required")
    binding = verify_snapshot_binding(repo, binding_path)
    review = read_value(review_path, SnapshotReview, expected_digest=trusted_digest)
    require(
        review.review_kind == kind
        and review.binding_digest == binding.artifact_digest
        and review.budget == binding.budget
        and review.implementation_digests == inspection_implementation_digests()
        and review.policy_digest == digest_json_artifact(DockerPolicyV1()),
        "snapshot_review_context_mismatch",
    )
    require(
        resolve_runner(runner_id=review.runner.runner_id, image_digest=None) == review.runner,
        "snapshot_runner_review_changed",
    )
    for manifest in binding.trees.values():
        _, files = read_snapshot(repo, manifest.commit, budget=binding.budget)
        require(
            files.get(FIXTURE_REF) == FIXTURE_MARKER, "snapshot_only_tool_owned_fixtures_authorized"
        )
    return binding, review
