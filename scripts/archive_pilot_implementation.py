"""Preserve exact implementation bytes, including uncommitted code, without a fake Git version."""

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from evidenceguard.artifacts import write_immutable
from evidenceguard.change_analysis import inspection_implementation_digests
from evidenceguard.digests import canonical_json_bytes, digest_file, digest_json_artifact
from evidenceguard.pilot_inputs import signed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Implementation archive output exists")
    root = Path.cwd().resolve(strict=True)
    args.output.absolute().relative_to(root)
    before = inspection_implementation_digests()
    refs = sorted(
        {
            *Path("src/evidenceguard").rglob("*.py"),
            *Path("scripts").glob("*.py"),
            Path("pyproject.toml"),
            Path("uv.lock"),
            Path("containers/python-runner/Dockerfile"),
            Path("containers/python-runner/entrypoint.py"),
        }
    )
    args.output.mkdir(parents=True)
    archive = args.output / "implementation.zip"
    digests = {ref.as_posix(): digest_file(ref) for ref in refs}
    with ZipFile(archive, "x", compression=ZIP_DEFLATED) as output:
        for ref in refs:
            output.write(ref, ref.as_posix())
    if before != inspection_implementation_digests() or any(
        digest_file(ref) != value for ref, value in digests.items()
    ):
        raise ValueError("Implementation changed during archival")
    value = signed(
        {
            "schema_version": "implementation-archive.v1",
            "recorded_at": datetime.now(UTC).isoformat(),
            "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"])),
            "implementation_version": digest_json_artifact(before),
            "implementation_digests": before,
            "archive_ref": archive.as_posix(),
            "archive_digest": digest_file(archive),
            "files": digests,
        }
    )
    write_immutable(args.output / "receipt.json", canonical_json_bytes(value))
    print(
        json.dumps(
            {"implementation_version": value["implementation_version"], "archive": str(archive)}
        )
    )


if __name__ == "__main__":
    main()
