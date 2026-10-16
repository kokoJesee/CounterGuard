"""Fetch a pinned public candidate without checkout, hooks, install, import or execution."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from evidenceguard.artifacts import write_immutable
from evidenceguard.digests import canonical_json_bytes, digest_json_artifact
from evidenceguard.repository import read_repository

URL = "https://github.com/python-validators/validators"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Fetch only; record proposed HEAD/parent for manifest review.",
    )
    args = parser.parse_args()
    if args.dest.exists():
        raise ValueError("Pilot destination exists; use a new version directory")
    if bool(args.manifest) == args.discover:
        parser.error("choose --manifest or --discover")
    manifest = json.loads(args.manifest.read_bytes()) if args.manifest else None
    if manifest and digest_json_artifact(manifest) != manifest["artifact_digest"]:
        raise ValueError("Pilot manifest digest mismatch")
    if manifest and (
        manifest["repository_url"] != URL
        or any(
            not re.fullmatch(r"[0-9a-f]{40}", manifest[field]) for field in ("base_sha", "head_sha")
        )
    ):
        raise ValueError("Manifest must freeze the selected URL and full base/head SHA")
    git = shutil.which("git")
    if git is None:
        raise OSError("Git is unavailable")
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    }
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_NO_LAZY_FETCH="1",
    )
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    command = [
        git,
        "-c",
        "core.hooksPath=" + os.devnull,
        "-c",
        "credential.helper=",
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
        "clone",
        "--no-checkout",
        "--no-recurse-submodules",
        "--",
        URL,
        str(args.dest),
    ]
    try:
        subprocess.run(command, env=env, capture_output=True, check=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        failure = {
            "schema_version": "pilot-preparation-failure.v1",
            "repository_url": URL,
            "stage": "clone_without_checkout",
            "error_type": type(error).__name__,
            "returncode": getattr(error, "returncode", None),
            "repository_execution_count": 0,
        }
        failure["artifact_digest"] = digest_json_artifact(failure)
        write_immutable(
            args.dest.parent / (args.dest.name + "-failure.json"), canonical_json_bytes(failure)
        )
        print(json.dumps(failure, sort_keys=True))
        return 4
    base, head = (
        ("HEAD~1", "HEAD")
        if args.discover
        else (
            manifest["base_sha"],
            manifest["head_sha"],
        )
    )
    snapshot = read_repository(args.dest, base, head)
    result = {
        "schema_version": "pilot-preparation.v1",
        "repository_url": URL,
        "base_sha": snapshot.base_commit,
        "head_sha": snapshot.head_commit,
        "snapshot": snapshot.model_dump(mode="json"),
        "checkout_performed": False,
        "repository_execution_count": 0,
    }
    result["artifact_digest"] = digest_json_artifact(result)
    write_immutable(
        args.dest.parent / (args.dest.name + "-preparation.json"), canonical_json_bytes(result)
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if snapshot.status == "ready" else 4


if __name__ == "__main__":
    raise SystemExit(main())
