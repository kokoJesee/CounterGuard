"""Record actual four-fixture acceptance, bound to the new runner lock and image."""

import argparse
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from record_runner_build import verify

from evidenceguard.artifacts import write_immutable
from evidenceguard.digests import canonical_json_bytes, digest_file
from evidenceguard.pilot_inputs import signed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Acceptance output exists")
    lock = verify(args.runner_lock)
    environment = dict(
        os.environ, EVIDENCEGUARD_RUNNER_IMAGE_DIGEST=lock["image_id"], PYTHONIOENCODING="utf-8"
    )
    command = ["uv", "run", "pytest", "tests/integration/test_docker_runner.py", "-q"]
    started_at, started = datetime.now(UTC).isoformat(), time.monotonic()
    result = subprocess.run(command, env=environment, capture_output=True, timeout=120)
    log = result.stdout + result.stderr
    log_path = args.output / "docker-tests.txt"
    write_immutable(log_path, log)
    text = log.decode("utf-8", errors="replace")
    accepted = (
        result.returncode == 0
        and bool(re.search(r"\b4 passed\b", text))
        and not re.search(r"\b\d+ (?:failed|skipped|error)", text)
    )
    receipt = signed(
        {
            "schema_version": "runner-attack-acceptance.v1",
            "accepted": accepted,
            "image_id": lock["image_id"],
            "runner_lock_digest": lock["artifact_digest"],
            "command": command,
            "started_at": started_at,
            "duration_seconds": time.monotonic() - started,
            "exit_code": result.returncode,
            "passed": 4 if accepted else None,
            "log_ref": log_path.as_posix(),
            "log_digest": digest_file(log_path),
            "scope": "Original four W3-B Docker attack fixtures against the new image",
        }
    )
    write_immutable(args.output / "acceptance.json", canonical_json_bytes(receipt))
    print(text.strip())
    return 0 if accepted else 4


if __name__ == "__main__":
    raise SystemExit(main())
