"""Freeze an accepted runner as an exact, offline-restorable image and inventory."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes, digest_file, digest_json_artifact

INVENTORY = r"""
import base64, hashlib, importlib.metadata as m, json, platform
packages = []
for dist in m.distributions():
    files = []
    checked = 0
    for item in sorted(dist.files or [], key=str):
        path = dist.locate_file(item)
        if not path.is_file():
            raise RuntimeError("missing distribution file: " + str(item))
        raw = path.read_bytes()
        if item.hash:
            actual = base64.urlsafe_b64encode(
                hashlib.new(item.hash.mode, raw).digest()
            ).decode().rstrip("=")
            if actual != item.hash.value:
                raise RuntimeError("RECORD mismatch: " + str(item))
            checked += 1
        files.append([str(item), hashlib.sha256(raw).hexdigest()])
    packages.append({"name": dist.metadata["Name"], "version": dist.version,
                     "record_hashes_checked": checked, "files": files})
print(json.dumps({"python": platform.python_version(),
                  "packages": sorted(packages, key=lambda p: p["name"].lower())},
                 sort_keys=True))
"""


def docker(*args: str, timeout: int = 120) -> bytes:
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, timeout=timeout
    ).stdout


def inventory(image_id: str) -> dict:
    return json.loads(
        docker(
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--user=65532:65532",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true",
            "--memory=256m",
            "--pids-limit=64",
            "--entrypoint=python",
            image_id,
            "-I",
            "-c",
            INVENTORY,
        )
    )


def verify(record: Path) -> dict:
    value = json.loads(record.read_bytes())
    if digest_json_artifact(value) != value["artifact_digest"]:
        raise ValueError("Runner lock digest mismatch")
    for ref, expected in value["files"].items():
        if digest_file(Path(ref)) != expected:
            raise ValueError(f"Runner build input/output changed: {ref}")
    actual = json.loads(docker("image", "inspect", value["image_id"]))[0]
    if actual["Id"] != value["image_id"] or actual["RootFS"] != value["rootfs"]:
        raise ValueError("Runner image identity changed")
    if inventory(value["image_id"]) != value["inventory"]:
        raise ValueError("Runner installed distribution inventory changed")
    return value


def write_receipt(value: dict, record: Path, receipt_path: Path) -> None:
    installed = value["inventory"]
    receipt = {
        "schema_version": "runner-build-receipt.v1",
        "image_id": value["image_id"],
        "base_registry_digests": value["base_registry_digests"],
        "lock_ref": record.as_posix(),
        "lock_digest": value["artifact_digest"],
        "inventory_digest": digest_json_artifact(installed),
        "packages": [
            {key: package[key] for key in ("name", "version", "record_hashes_checked")}
            for package in installed["packages"]
        ],
        "python": installed["python"],
        "files": value["files"],
        "lock_scope": value["lock_scope"],
    }
    receipt["artifact_digest"] = digest_json_artifact(receipt)
    write_immutable(receipt_path, canonical_json_bytes(receipt))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--image", default="counterguard-runner:w3b-formal-v1")
    parser.add_argument("--base", default="python:3.13-slim-bookworm")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.verify:
        value = verify(args.verify)
        if args.receipt:
            write_receipt(value, args.verify, args.receipt)
        print(json.dumps({"verified": True, "image_id": value["image_id"]}))
        return
    if args.output is None:
        parser.error("--output is required for a new lock")
    args.output.mkdir(parents=True, exist_ok=False)
    image = json.loads(docker("image", "inspect", args.image))[0]
    base = json.loads(docker("image", "inspect", args.base))[0]
    if not base["RepoDigests"]:
        raise ValueError("Base image has no registry digest")
    layers = base["RootFS"]["Layers"]
    if image["RootFS"]["Layers"][: len(layers)] != layers:
        raise ValueError("Runner layers do not derive from the selected base")
    installed = inventory(image["Id"])
    archive = args.output / "runner.tar"
    docker("image", "save", "--output", str(archive), image["Id"], timeout=300)
    value = {
        "schema_version": "runner-build-lock.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "image_id": image["Id"],
        "image_descriptor": image.get("Descriptor"),
        "base_image_id": base["Id"],
        "base_registry_digests": base["RepoDigests"],
        "base_rootfs": base["RootFS"],
        "rootfs": image["RootFS"],
        "inventory": installed,
        "files": {
            ref: digest_file(Path(ref))
            for ref in (
                "containers/python-runner/Dockerfile",
                "containers/python-runner/entrypoint.py",
                archive.as_posix(),
            )
        },
        "restore": f"docker image load --input {archive.as_posix()}",
        "lock_scope": "exact accepted image bytes and installed dependencies; "
        "future source builds must create and validate a new lock",
    }
    value["artifact_digest"] = digest_json_artifact(value)
    record = args.output / "runner-lock.json"
    write_immutable(record, canonical_json_bytes(value))
    verify(record)
    if args.receipt:
        write_receipt(value, record, args.receipt)
    print(
        json.dumps(
            {
                "record": record.as_posix(),
                "image_id": image["Id"],
                "base_registry_digests": base["RepoDigests"],
                "verified": True,
            }
        )
    )


if __name__ == "__main__":
    main()
