"""Advance artifact namespace without rewriting the owner commit or old manifest."""

import argparse
import json
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes
from counterguard.pilot_inputs import read_fact, signed
from counterguard.repository_contracts import EVIDENCE_ID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if args.manifest.exists() or args.output_root.exists():
        raise ValueError("Use a fresh manifest and output namespace")
    root = Path.cwd().resolve(strict=True)
    output = args.output_root.absolute().relative_to(root).as_posix()
    previous = read_fact(args.source)
    value = {
        **previous,
        "output_root_ref": output,
        "workspace_root_ref": output + "/ws",
        "registry_root_ref": output + "/registry",
        "scope_ref": output + "/scope.json",
        "evidence_id": EVIDENCE_ID,
        "supersedes_manifest": {
            "ref": args.source.as_posix(),
            "artifact_digest": previous["artifact_digest"],
        },
        "recapture_reason": args.reason,
    }
    write_immutable(args.manifest, canonical_json_bytes(signed(value)))
    print(
        json.dumps(
            {
                "manifest": str(args.manifest),
                "head_unchanged": value["head_sha"],
                "evidence_id": EVIDENCE_ID,
            }
        )
    )


if __name__ == "__main__":
    main()
