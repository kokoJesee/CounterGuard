"""Create the one owner tooling commit; no repository Python or installation is run."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from evidenceguard.artifacts import write_immutable
from evidenceguard.digests import canonical_json_bytes, digest_bytes, digest_file
from evidenceguard.pilot_inputs import TOOL_FILES, read_fact, signed
from evidenceguard.repository import read_commit_metadata, read_committed_files
from evidenceguard.repository_contracts import (
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
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runner-lock", type=Path, required=True)
    parser.add_argument("--docker-acceptance", type=Path, required=True)
    args = parser.parse_args()
    workspace = Path.cwd().resolve(strict=True)
    root = args.output.absolute()
    root.relative_to(workspace)
    if root.exists() or args.manifest.exists():
        raise ValueError("Preparation is immutable; choose a new version directory")
    lock = read_fact(args.runner_lock)
    acceptance = read_fact(args.docker_acceptance)
    if (
        acceptance["accepted"] is not True
        or acceptance["passed"] != 4
        or acceptance["image_id"] != lock["image_id"]
        or acceptance["runner_lock_digest"] != lock["artifact_digest"]
    ):
        raise ValueError("Require real four-fixture acceptance receipt without skips/failures")
    git = shutil.which("git")
    if not git:
        raise OSError("Git is unavailable")
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    }
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_NO_LAZY_FETCH="1",
    )
    # Read the operator's existing identity, without copying their Git configuration.
    name = subprocess.check_output([git, "config", "user.name"], text=True).strip()
    email = subprocess.check_output([git, "config", "user.email"], text=True).strip()
    if not name or not email:
        raise ValueError("A configured local Git author identity is required")
    root.mkdir(parents=True)
    repo = root / "repo"
    prefix = [
        git,
        "-c",
        "core.hooksPath=" + os.devnull,
        "-c",
        "credential.helper=",
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
        "-c",
        "commit.gpgSign=false",
        "-c",
        "user.name=" + name,
        "-c",
        "user.email=" + email,
    ]

    def run(*command, timeout=30):
        result = subprocess.run(
            [*prefix, *command], env=env, capture_output=True, check=True, timeout=timeout
        )
        return result.stdout.decode("utf-8").strip()

    run("clone", "--no-checkout", "--no-recurse-submodules", "--", FORK_URL, str(repo), timeout=120)
    if read_commit_metadata(repo, FIXED)["parents"] != (BASE,):
        raise ValueError("The upstream fix/parent relationship changed")
    _, fixed, _ = read_committed_files(repo, FIXED)
    contract = extract_mac_contract(fixed[TEST_REF])
    runtime_refs = tuple(sorted(ref for ref in fixed if ref.startswith("src/validators/")))
    config = {
        "schema_version": "project-config.v2",
        "project_id": "validators-fork-pilot",
        "targets": [
            {
                "target_id": "mac-address",
                "guard_id": GUARD_ID,
                "source_ref": SOURCE_REF,
                "module": contract.target_module,
                "symbol": contract.target_symbol,
                "import_root": "src",
                "contract_ref": CONTRACT_REF,
                "dependency_refs": [ref for ref in runtime_refs if ref != SOURCE_REF],
            }
        ],
        "audit_refs": [CONFIG_REF, TEST_REF, "contracts/provenance.json"],
        "ignored_paths": [],
    }
    provenance = {
        "origin": "NOT upstream",
        "upstream_commit": FIXED,
        "upstream_test_ref": TEST_REF,
        "upstream_test_digest": contract.upstream_test_digest,
        "extraction_version": contract.extraction_version,
        "upstream_case_count": 35,
        "selected_case_count": 10,
    }
    # No checkout hooks or filters from user/global configuration are loaded.
    run("-C", str(repo), "checkout", "--detach", FIXED)
    for ref, value in (
        (CONFIG_REF, config),
        (CONTRACT_REF, contract),
        ("contracts/provenance.json", provenance),
    ):
        write_immutable(repo / ref, canonical_json_bytes(value))
    run("-C", str(repo), "add", "--", *TOOL_FILES)
    run(
        "-C",
        str(repo),
        "commit",
        "-m",
        "NOT upstream: add EvidenceGuard MAC pilot configuration and contracts",
    )
    head = run("-C", str(repo), "rev-parse", "HEAD")
    bundle = root / "owner-head.bundle"
    run("-C", str(repo), "bundle", "create", str(bundle), "HEAD")
    trees, tree_pins = {}, {}
    for key, revision in (("b", BASE), ("f", FIXED), ("h", head)):
        _, files, pins = read_committed_files(repo, revision)
        trees[key], tree_pins[key] = files, [pin.model_dump(mode="json") for pin in pins]
    if set(trees["h"]) - set(fixed) != set(TOOL_FILES) or any(
        trees["h"].get(ref) != body for ref, body in fixed.items()
    ):
        raise ValueError("Tooling commit must not change any upstream file")
    receipts = [
        args.docker_acceptance,
        Path(acceptance["log_ref"]),
        Path("docs/results/w3d-fork-v1/runner-receipt.json"),
        Path("docs/results/w3c-v1/registry-tests.txt"),
    ]
    output_ref = root.relative_to(workspace).as_posix()
    value = signed(
        {
            "schema_version": "pilot-manifest.v2",
            "repository_url": FORK_URL,
            "upstream_url": UPSTREAM_URL,
            "license": {
                "spdx": "MIT",
                "ref": "LICENSE.txt",
                "content_digest": digest_bytes(fixed["LICENSE.txt"]),
            },
            "base_sha": BASE,
            "fixed_sha": FIXED,
            "head_sha": head,
            "head_availability": "local_only; not pushed",
            "owner_bundle_ref": bundle.relative_to(workspace).as_posix(),
            "owner_bundle_digest": digest_file(bundle),
            "tool_files": list(TOOL_FILES),
            "repository_ref": (repo.relative_to(workspace)).as_posix(),
            "config_ref": (repo / CONFIG_REF).relative_to(workspace).as_posix(),
            "config_digest": digest_file(repo / CONFIG_REF),
            "contract_ref": (repo / CONTRACT_REF).relative_to(workspace).as_posix(),
            "contract_digest": digest_file(repo / CONTRACT_REF),
            "tree_pins": tree_pins,
            "runtime_refs": list(runtime_refs),
            "file_origins": {
                ref: {
                    "origin": "tool" if ref in TOOL_FILES else "upstream",
                    "commit": head if ref in TOOL_FILES else FIXED,
                    "content_digest": digest_bytes(body),
                }
                for ref, body in sorted(trees["h"].items())
            },
            "runner_lock_ref": args.runner_lock.as_posix(),
            "runner_lock_digest": lock["artifact_digest"],
            "image_id": lock["image_id"],
            "docker_acceptance_ref": args.docker_acceptance.as_posix(),
            "prerequisite_receipts": {ref.as_posix(): digest_file(ref) for ref in receipts},
            "output_root_ref": output_ref,
            "workspace_root_ref": output_ref + "/ws",
            "registry_root_ref": output_ref + "/registry",
            "scope_ref": output_ref + "/scope.json",
            "unknown_is_execution_success": False,
            "execution_success_requires": [
                "ready inspection",
                "verified enabled Registry Guard",
                "audited exact-snapshot scope",
                "Docker-only execution",
                "same-head repeat counts",
            ],
            "claim": "MAC 10-case projection only; audited scope; no learned generalization",
            "historical_capture": "contract from H; target from B/F; ordinary replay at H only",
        }
    )
    write_immutable(args.manifest, canonical_json_bytes(value))
    print(
        json.dumps(
            {
                "manifest": str(args.manifest),
                "head_sha": head,
                "upstream_files_unchanged": True,
                "repository_execution_count": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
