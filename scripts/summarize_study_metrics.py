"""Summarize/verify arithmetic on a closed tool-owned fixture matrix; no execution mode."""

import argparse
import json
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.study_metrics import (
    StudyMetricInput,
    StudyMetricSummary,
    summarize_study_metrics,
    verify_study_metrics,
)

LIMIT = 4 * 1024 * 1024


def _read(path, model):
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("Metrics byte budget exceeded")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("Non-finite JSON number")

    json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    return model.model_validate_json(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("summarize", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--input", type=Path, required=True)
        command.add_argument(
            "--output" if name == "summarize" else "--result", type=Path, required=True
        )
    args = parser.parse_args(argv)
    try:
        inputs = _read(args.input, StudyMetricInput)
        if args.command == "verify":
            result = verify_study_metrics(inputs, _read(args.result, StudyMetricSummary))
        else:
            result = summarize_study_metrics(inputs)
            raw = canonical_json_bytes(result)
            if len(raw) > LIMIT:
                raise ValueError("Metrics result byte budget exceeded")
            write_immutable(args.output, raw)
    except (ArtifactIntegrityError, OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({"status": "rejected", "reason_code": "study_metrics_input_invalid"}))
        return 5
    print(canonical_json_bytes(result).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
