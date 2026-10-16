"""Freeze the selected candidate and a proposed oracle without executing project code."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from benchmark_fsck import _measure, _summary

from counterguard.artifacts import write_immutable
from counterguard.digests import (
    canonical_json_bytes,
    digest_bytes,
    digest_file,
    digest_json_artifact,
)
from counterguard.project_config import ProjectConfig
from counterguard.repository import read_committed_files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    preparation = json.loads(args.preparation.read_bytes())
    if digest_json_artifact(preparation) != preparation["artifact_digest"]:
        raise ValueError("Preparation digest mismatch")
    base, head = preparation["base_sha"], preparation["head_sha"]
    commit, files, pins = read_committed_files(args.repo, head)
    if commit != head or b"MIT" not in files["LICENSE.txt"]:
        raise ValueError("Selected revision/license mismatch")
    contract = {
        "schema_version": "pilot-contract-proposal.v1",
        "contract_id": "validators-mac-complete-v1",
        "status": "proposal_not_admitted_as_counterguard_contract",
        "target": {
            "module": "src.validators.mac_address",
            "symbol": "mac_address",
            "source_ref": "src/validators/mac_address.py",
        },
        "calling_convention": "positional_only",
        "cases": [
            {
                "case_id": "mac-complete-colons",
                "positional_args": ["01:23:45:67:ab:CD"],
                "expected_return": {"kind": "literal_true"},
            },
            {
                "case_id": "mac-trailing-newline",
                "positional_args": ["01:23:45:67:ab:CD\n"],
                "expected_return": {"kind": "instance_of", "type": "validators.ValidationError"},
            },
        ],
        "oracle_source": {
            "commit": head,
            "path": "tests/test_complete_values.py",
            "content_digest": digest_bytes(files["tests/test_complete_values.py"]),
        },
        "limitations": [
            "No dual-run bug/fix evidence has been captured",
            "v1 Guard template uses keyword arguments and cannot assert this return class",
        ],
    }
    contract_ref = "integrations/pilot/contracts/validators-mac-complete-v1.json"
    config_ref = "integrations/pilot/project-config.json"
    package_refs = sorted(ref for ref in files if ref.startswith("src/validators/"))
    config = {
        "schema_version": "project-config.v1",
        "project_id": "validators-pilot-v1",
        "targets": [
            {
                "target_id": "validators-mac",
                "guard_id": "grd_validators_mac_complete_v1",
                **contract["target"],
                "contract_ref": "contracts/validators-mac-complete-v1.json",
                "dependency_refs": [
                    ref for ref in package_refs if ref != contract["target"]["source_ref"]
                ]
                + ["tests/test_complete_values.py"],
            }
        ],
        "ignored_paths": [],
    }
    ProjectConfig.model_validate_json(json.dumps(config))
    write_immutable(Path(contract_ref), canonical_json_bytes(contract))
    write_immutable(Path(config_ref), canonical_json_bytes(config))
    license_ref = "integrations/pilot/LICENSE.validators.txt"
    metadata_ref = "integrations/pilot/upstream-pyproject.toml"
    write_immutable(Path(license_ref), files["LICENSE.txt"])
    write_immutable(Path(metadata_ref), files["pyproject.toml"])
    measurement = _summary(_measure(shutil.which("git"), args.repo / ".git", base, head, 5))
    object_files = list((args.repo / ".git/objects").rglob("*"))
    storage_bytes = sum(path.stat().st_size for path in object_files if path.is_file())
    loose_count = sum(path.is_file() and len(path.parent.name) == 2 for path in object_files)
    value = {
        "schema_version": "pilot-manifest.v1",
        "repository_url": preparation["repository_url"],
        "license": {
            "spdx": "MIT",
            "upstream_ref": "LICENSE.txt",
            "local_ref": license_ref,
            "content_digest": digest_bytes(files["LICENSE.txt"]),
        },
        "base_sha": base,
        "head_sha": head,
        "candidate_contract": {
            "ref": contract_ref,
            "content_digest": digest_file(contract_ref),
            "admitted": False,
        },
        "config_ref": config_ref,
        "config_digest": digest_file(config_ref),
        "metadata_ref": metadata_ref,
        "metadata_digest": digest_file(metadata_ref),
        "complete_tree_pins": [pin.model_dump(mode="json") for pin in pins],
        "runner_receipt_ref": "docs/results/w3b-formal-v1/runner-receipt.json",
        "runner_receipt_digest": digest_file("docs/results/w3b-formal-v1/runner-receipt.json"),
        "prerequisite_receipts": {
            ref: digest_file(ref)
            for ref in (
                "docs/results/w3b-formal-v1/docker-tests.txt",
                "docs/results/w3c-v1/registry-tests.txt",
                "docs/results/w3c-v1/fast-tests.txt",
            )
        },
        "registry_root": ".counterguard",
        "prerequisites": {"w3b_commit": "1260b45", "w3c_commit": "abb2124"},
        "design_ref": "integrations/pilot/design.md",
        "design_digest": digest_file("integrations/pilot/design.md"),
        "size": {
            "committed_bytes": sum(map(len, files.values())),
            "files": len(files),
            "test_files": sum(
                ref.startswith("tests/")
                and Path(ref).name.startswith("test_")
                and ref.endswith(".py")
                for ref in files
            ),
            "object_storage_bytes": storage_bytes,
            "loose_objects": loose_count,
        },
        "fsck": measurement,
        "fsck_admitted": measurement["max_ms"] <= 2500
        and storage_bytes <= 64 * 1024 * 1024
        and loose_count < 10000,
        "execution_success_requires": [
            "ready inspection",
            "verified enabled Registry Guard",
            "audited applicable scope",
            "Docker-only execution",
            "same-commit repeated execution counts",
        ],
        "unknown_is_execution_success": False,
    }
    value["artifact_digest"] = digest_json_artifact(value)
    write_immutable(args.output, canonical_json_bytes(value))
    print(
        json.dumps(
            {
                "manifest": str(args.output),
                "commit": head,
                "size": value["size"],
                "fsck": measurement,
                "contract_admitted": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
