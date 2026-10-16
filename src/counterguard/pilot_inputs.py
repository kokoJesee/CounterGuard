"""Rebuild pilot admission from committed objects, not repository assertions."""

from __future__ import annotations

import json
import re
from pathlib import Path

from counterguard.change_analysis import inspect_repository, inspection_implementation_digests
from counterguard.digests import (
    canonical_json_bytes,
    digest_bytes,
    digest_file,
    digest_json_artifact,
)
from counterguard.errors import ArtifactIntegrityError
from counterguard.preflight import inspect_execution_requirements
from counterguard.project_config import load_project_config, reject_links, repository_path
from counterguard.repository import read_commit_metadata, read_committed_files
from counterguard.repository_contracts import (
    BASE,
    CONFIG_REF,
    CONTRACT_REF,
    FIXED,
    FORK_URL,
    GUARD_ID,
    SOURCE_REF,
    TEST_REF,
    UPSTREAM_URL,
    extract_mac_contract,
    read_contract,
)

ZERO = "sha256:" + "0" * 64
TOOL_FILES = (CONFIG_REF, CONTRACT_REF, "contracts/provenance.json")


def resolve_ref(workspace: Path, ref: str, *, exists=True) -> Path:
    repository_path(ref)
    candidate = workspace / ref
    reject_links(candidate)
    resolved = candidate.resolve(strict=exists)
    if not resolved.is_relative_to(workspace.resolve(strict=True)):
        raise ArtifactIntegrityError("Pilot reference escapes workspace")
    if exists and (not resolved.is_file() or resolved.stat().st_nlink != 1):
        raise ArtifactIntegrityError("Pilot reference must be an unlinked regular file")
    return resolved


def read_fact(path: Path) -> dict:
    reject_links(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ArtifactIntegrityError("Pilot fact exceeds byte limit")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict) or value.get("artifact_digest") != digest_json_artifact(value):
        raise ArtifactIntegrityError("Pilot fact digest mismatch")
    return value


def signed(value: dict) -> dict:
    return {**value, "artifact_digest": digest_json_artifact(value)}


def closure_digest(files: dict[str, bytes], refs: tuple[str, ...]) -> str:
    return digest_json_artifact({ref: digest_bytes(files[ref]) for ref in refs})


def load_inputs(manifest_path: Path, workspace: Path) -> dict:
    """Full, read-only admission; callers must perform this again after execution."""
    workspace = workspace.resolve(strict=True)
    manifest_path = resolve_ref(workspace, manifest_path.relative_to(workspace).as_posix())
    manifest = read_fact(manifest_path)
    config_ref = CONFIG_REF
    tool_files = TOOL_FILES
    if manifest.get("schema_version") == "pilot-manifest.v3":
        if manifest.get("profile") != "validators-existing-owner-head.v1":
            raise ArtifactIntegrityError("Unknown repository owner-head profile")
        config_ref = "evidenceguard.yaml"
        tool_files = (config_ref, CONTRACT_REF, "contracts/provenance.json")
    if (
        manifest.get("schema_version") not in {"pilot-manifest.v2", "pilot-manifest.v3"}
        or manifest.get("repository_url") != FORK_URL
        or manifest.get("upstream_url") != UPSTREAM_URL
        or manifest.get("base_sha") != BASE
        or manifest.get("fixed_sha") != FIXED
        or not re.fullmatch(r"[0-9a-f]{40}", manifest.get("head_sha", ""))
        or manifest.get("tool_files") != list(tool_files)
        or manifest.get("unknown_is_execution_success") is not False
    ):
        raise ArtifactIntegrityError("Manifest is not the reviewed fork pilot profile")
    output_ref = repository_path(manifest["output_root_ref"])
    if not output_ref.startswith("artifacts/pilot/"):
        raise ArtifactIntegrityError("Pilot outputs must use an artifact namespace")
    expected_layout = {
        "workspace_root_ref": output_ref + "/ws",
        "registry_root_ref": output_ref + "/registry",
        "scope_ref": output_ref + "/scope.json",
        "config_ref": manifest["repository_ref"] + "/" + config_ref,
        "contract_ref": manifest["repository_ref"] + "/" + CONTRACT_REF,
    }
    if any(manifest[key] != expected for key, expected in expected_layout.items()):
        raise ArtifactIntegrityError("Manifest paths do not use the reviewed source/output layout")
    resolve_ref(workspace, output_ref, exists=False)
    repo = workspace / repository_path(manifest["repository_ref"])
    reject_links(repo)
    commits = {"b": BASE, "f": FIXED, "h": manifest["head_sha"]}
    trees, pins = {}, {}
    for key, revision in commits.items():
        actual, files, file_pins = read_committed_files(repo, revision)
        if actual != revision:
            raise ArtifactIntegrityError("Repository revision did not resolve exactly")
        trees[key], pins[key] = files, file_pins
        if [pin.model_dump(mode="json") for pin in file_pins] != manifest["tree_pins"][key]:
            raise ArtifactIntegrityError("Committed tree differs from frozen manifest")
    head_meta = read_commit_metadata(repo, commits["h"])
    fixed_meta = read_commit_metadata(repo, FIXED)
    if (
        head_meta["parents"] != (FIXED,)
        or "NOT upstream" not in head_meta["message"]
        or fixed_meta["parents"] != (BASE,)
    ):
        raise ArtifactIntegrityError("Pilot must have exactly one identifiable tooling commit")
    fixed, head = trees["f"], trees["h"]
    if (
        manifest["license"]
        != {
            "spdx": "MIT",
            "ref": "LICENSE.txt",
            "content_digest": digest_bytes(fixed["LICENSE.txt"]),
        }
        or digest_file(resolve_ref(workspace, manifest["owner_bundle_ref"]))
        != manifest["owner_bundle_digest"]
    ):
        raise ArtifactIntegrityError("License provenance or owner commit bundle differs")
    if set(head) - set(fixed) != set(tool_files) or any(head.get(p) != b for p, b in fixed.items()):
        raise ArtifactIntegrityError("Tooling commit changed upstream files")
    runtime_refs = tuple(sorted(ref for ref in fixed if ref.startswith("src/validators/")))
    if list(runtime_refs) != manifest["runtime_refs"] or len(runtime_refs) > 64:
        raise ArtifactIntegrityError("Runtime closure must pin the complete reviewed package")
    contract = read_contract(head[CONTRACT_REF])
    if contract != extract_mac_contract(fixed[TEST_REF]):
        raise ArtifactIntegrityError(
            "Head contract does not reproduce the upstream test projection"
        )
    if head["contracts/provenance.json"] != canonical_json_bytes(
        {
            "origin": "NOT upstream",
            "upstream_commit": FIXED,
            "upstream_test_ref": TEST_REF,
            "upstream_test_digest": contract.upstream_test_digest,
            "extraction_version": contract.extraction_version,
            "upstream_case_count": 35,
            "selected_case_count": 10,
        }
    ):
        raise ArtifactIntegrityError("Tooling provenance changed")
    origins = {
        ref: {
            "origin": "tool" if ref in tool_files else "upstream",
            "commit": commits["h"] if ref in tool_files else FIXED,
            "content_digest": digest_bytes(body),
        }
        for ref, body in sorted(head.items())
    }
    if origins != manifest["file_origins"]:
        raise ArtifactIntegrityError("File origin declaration contradicts committed bytes")
    config_path = resolve_ref(workspace, manifest["config_ref"])
    if config_path.read_bytes() != head[config_ref]:
        raise ArtifactIntegrityError("Configuration must come from head")
    config, config_digest = load_project_config(config_path)
    contract_path = resolve_ref(workspace, manifest["contract_ref"])
    if contract_path.read_bytes() != head[CONTRACT_REF]:
        raise ArtifactIntegrityError("Contract must come from head")
    if (
        config_digest != manifest["config_digest"]
        or digest_file(contract_path) != manifest["contract_digest"]
        or config.schema_version != "project-config.v2"
        or len(config.targets) != 1
    ):
        raise ArtifactIntegrityError("Configuration or contract binding differs")
    target = config.targets[0]
    if (
        target.source_ref != SOURCE_REF
        or target.module != contract.target_module
        or target.symbol != contract.target_symbol
        or target.import_root != "src"
        or target.contract_ref != CONTRACT_REF
        or target.guard_id != GUARD_ID
        or set(target.dependency_refs) != set(runtime_refs) - {SOURCE_REF}
        or set(config.audit_refs) != {config_ref, TEST_REF, "contracts/provenance.json"}
        or config.ignored_paths
    ):
        raise ArtifactIntegrityError("Pilot mapping exceeds the reviewed MAC profile")
    lock = read_fact(resolve_ref(workspace, manifest["runner_lock_ref"]))
    if (
        lock["artifact_digest"] != manifest["runner_lock_digest"]
        or lock["image_id"] != manifest["image_id"]
    ):
        raise ArtifactIntegrityError("Runner lock binding differs")
    for ref, expected in lock["files"].items():
        if digest_file(resolve_ref(workspace, ref)) != expected:
            raise ArtifactIntegrityError("Runner source or archive is stale")
    packages = {p["name"].lower(): p["version"] for p in lock["inventory"]["packages"]}
    if packages.get("pytest") != "9.0.3":
        raise ArtifactIntegrityError("Pilot requires accepted pytest 9.0.3 image")
    acceptance = read_fact(resolve_ref(workspace, manifest["docker_acceptance_ref"]))
    if (
        acceptance["accepted"] is not True
        or acceptance["passed"] != 4
        or acceptance["exit_code"] != 0
        or acceptance["image_id"] != lock["image_id"]
        or acceptance["runner_lock_digest"] != lock["artifact_digest"]
        or digest_file(resolve_ref(workspace, acceptance["log_ref"])) != acceptance["log_digest"]
    ):
        raise ArtifactIntegrityError("Four-fixture acceptance is missing or bound to another image")
    for ref, expected in manifest["prerequisite_receipts"].items():
        if digest_file(resolve_ref(workspace, ref)) != expected:
            raise ArtifactIntegrityError("Prerequisite receipt changed")
    preflights = {}
    for key, files in trees.items():
        result = inspect_execution_requirements(files, pytest_version="9.0.3", import_root="src")
        preflights[key] = result
        if result["status"] != "eligible_candidate":
            raise ArtifactIntegrityError(f"Static preflight {key}: {result['findings']}")
    inspection = inspect_repository(repo, BASE, commits["h"], config_path)
    if inspection.status != "ready" or inspection.unmapped_paths or inspection.reason_codes:
        raise ArtifactIntegrityError("Inspection must be ready without uncertainty")
    return {
        "manifest": manifest,
        "trees": trees,
        "pins": pins,
        "contract": contract,
        "config": config,
        "inspection": inspection,
        "preflights": preflights,
        "implementation_digests": inspection_implementation_digests(),
        "runtime_refs": runtime_refs,
    }
