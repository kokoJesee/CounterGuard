"""Export independent external-observation schemas without rewriting old versions."""

import argparse
import json
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.external_snapshot_models import (
    ExternalComparisonAdmission,
    ExternalComparisonAuthorization,
    ExternalComparisonPlan,
    ExternalComparisonReplay,
    ExternalComparisonReview,
    ExternalSnapshotAuthorization,
    ExternalSnapshotEvidence,
    ExternalSnapshotGuard,
    ExternalSnapshotMap,
    ExternalSnapshotReview,
    ExternalSnapshotTarget,
    ExternalSnapshotWitness,
)

MODELS = (
    ExternalSnapshotReview,
    ExternalSnapshotAuthorization,
    ExternalSnapshotEvidence,
    ExternalSnapshotGuard,
    ExternalSnapshotTarget,
    ExternalSnapshotMap,
    ExternalSnapshotWitness,
    ExternalComparisonReview,
    ExternalComparisonPlan,
    ExternalComparisonAdmission,
    ExternalComparisonAuthorization,
    ExternalComparisonReplay,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "schemas/external-snapshot-v1"
    for model in MODELS:
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        raw = (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode()
        path = root / (model.model_fields["schema_version"].default + ".schema.json")
        if args.check:
            if path.read_bytes() != raw:
                raise ValueError("External schema differs from runtime model")
        else:
            write_immutable(path, raw)
    print(f"{len(MODELS)} external snapshot schemas {'match' if args.check else 'exported'}")


if __name__ == "__main__":
    main()
