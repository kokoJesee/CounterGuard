"""Create a fresh runner-bound manifest using the existing owner commit unchanged."""

import argparse
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes, digest_file
from counterguard.pilot_inputs import load_inputs, read_fact, signed
from counterguard.runner_catalog import resolve_runner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--runner-lock", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    args = parser.parse_args()
    if args.manifest.exists() or args.output_root.exists():
        raise ValueError("Use a fresh manifest and output namespace")
    source, lock, acceptance = map(read_fact, (args.source, args.runner_lock, args.acceptance))
    review = resolve_runner(runner_id="validators-pytest9", image_digest=None)
    if (
        lock["artifact_digest"] != review.lock_digest
        or acceptance["artifact_digest"] != review.attack_receipt_digest
    ):
        raise ValueError("New manifest requires the catalog's reviewed runner lock/acceptance")
    workspace = Path.cwd().resolve(strict=True)
    output = args.output_root.absolute().relative_to(workspace).as_posix()
    prerequisites = (
        args.acceptance,
        Path(review.build_receipt_ref),
        Path("docs/results/w3c-v1/registry-tests.txt"),
    )
    value = signed(
        {
            **source,
            "schema_version": "pilot-manifest.v3",
            "profile": "validators-existing-owner-head.v1",
            "output_root_ref": output,
            "workspace_root_ref": output + "/ws",
            "registry_root_ref": output + "/registry",
            "scope_ref": output + "/scope.json",
            "runner_lock_ref": args.runner_lock.as_posix(),
            "runner_lock_digest": lock["artifact_digest"],
            "image_id": lock["image_id"],
            "docker_acceptance_ref": args.acceptance.as_posix(),
            "prerequisite_receipts": {ref.as_posix(): digest_file(ref) for ref in prerequisites},
            "supersedes_manifest": {
                "ref": args.source.as_posix(),
                "artifact_digest": source["artifact_digest"],
            },
            "recapture_reason": (
                "Current implementation and reviewed renamed runner; existing owner head unchanged"
            ),
        }
    )
    write_immutable(args.manifest, canonical_json_bytes(value))
    facts = load_inputs(args.manifest.absolute(), workspace)
    print(
        canonical_json_bytes(
            {
                "manifest_digest": value["artifact_digest"],
                "head_sha": value["head_sha"],
                "owner_commit_created": False,
                "inspection_status": facts["inspection"].status,
            }
        ).decode()
    )


if __name__ == "__main__":
    main()
