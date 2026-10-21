"""Export only fixture-only snapshot comparison schemas, never existing versions."""

import argparse
import json
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.snapshot_comparison_models import (
    SnapshotComparisonAdmission,
    SnapshotComparisonAuthorization,
    SnapshotComparisonMap,
    SnapshotComparisonPlan,
    SnapshotComparisonReplay,
    SnapshotComparisonReview,
    SnapshotComparisonTarget,
    SnapshotOwnWitness,
)

MODELS = (
    SnapshotComparisonTarget,
    SnapshotComparisonMap,
    SnapshotOwnWitness,
    SnapshotComparisonReview,
    SnapshotComparisonPlan,
    SnapshotComparisonAdmission,
    SnapshotComparisonAuthorization,
    SnapshotComparisonReplay,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "schemas/snapshot-comparison-v1"
    for model in MODELS:
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        raw = (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode()
        name = model.model_fields["schema_version"].default + ".schema.json"
        if args.check:
            if (root / name).read_bytes() != raw:
                raise ValueError("Comparison schema differs from strict runtime model")
        else:
            write_immutable(root / name, raw)
    print(f"{len(MODELS)} snapshot comparison schemas {'match' if args.check else 'exported'}")


if __name__ == "__main__":
    main()
