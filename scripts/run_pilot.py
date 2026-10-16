"""Run a reviewed fork pilot in ordered, fail-closed phases; never execute locally."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from evidenceguard.artifacts import write_immutable
from evidenceguard.digests import canonical_json_bytes, digest_file
from evidenceguard.pilot import compare_replays, run_phase
from evidenceguard.pilot_inputs import read_fact, signed
from evidenceguard.project_config import reject_links


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--phase", choices=["preflight", "build-guard", "replay", "compare"], required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first", type=Path)
    parser.add_argument("--second", type=Path)
    args = parser.parse_args()
    workspace = Path.cwd().resolve(strict=True)
    output = args.output.absolute()
    output.relative_to(workspace)
    reject_links(output)
    output.mkdir(parents=True, exist_ok=False)
    started_at, started = datetime.now(UTC).isoformat(), time.monotonic()
    launcher_digest = digest_file(Path(__file__))
    try:
        if args.phase == "compare":
            if not args.first or not args.second:
                raise ValueError("Compare requires --first and --second")
            expected_manifest = read_fact(args.manifest)["artifact_digest"]
            if any(
                read_fact(path)["manifest_digest"] != expected_manifest
                for path in (args.first, args.second)
            ):
                raise ValueError("Reports do not belong to the requested manifest")
            value = compare_replays(args.first, args.second)
            value["manifest_digest"] = expected_manifest
        else:
            value = run_phase(args.manifest.absolute(), workspace, output, args.phase)
    except Exception as error:
        value = signed(
            {
                "schema_version": "pilot-failure.v2",
                "accepted": False,
                "phase": args.phase,
                "error_type": type(error).__name__,
                "reason": str(error),
                "local_fallback_count": 0,
                "next_stage_allowed": False,
                "run": error.run.model_dump(mode="json") if hasattr(error, "run") else None,
                "note": "No fallback. Completed process logs remain in immutable run directories.",
            }
        )
    value = signed(
        {
            **value,
            "launcher_digest": launcher_digest,
            "phase_started_at": started_at,
            "phase_duration_seconds": time.monotonic() - started,
        }
    )
    write_immutable(output / "report.json", canonical_json_bytes(value))
    print(
        json.dumps(
            {
                "accepted": value["accepted"],
                "phase": args.phase,
                "report": str(output / "report.json"),
                "reason": value.get("reason"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if value["accepted"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
