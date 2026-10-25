"""Verify the formal scope_v2 readiness artifact and its pinned public facts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from counterguard.scope_v2_readiness import ReadinessError, verify_readiness


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--readiness", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = verify_readiness(args.root, args.readiness)
    except (OSError, ValueError, ReadinessError):
        print(json.dumps({"status": "rejected", "reason_code": "scope_v2_readiness_invalid"}))
        return 5
    print(
        json.dumps(
            {
                "status": "verified",
                "outcome": value.outcome,
                "next_phase_allowed": value.next_phase_allowed,
                "formal_scenarios": value.counts.formally_admitted_scenarios,
                "artifact_digest": value.artifact_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0 if value.next_phase_allowed else 4


if __name__ == "__main__":
    raise SystemExit(main())
