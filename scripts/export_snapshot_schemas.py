"""Export only the independent research snapshot schemas, never old versions."""

import argparse
import json
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.snapshot_models import (
    SnapshotAuthorization,
    SnapshotBinding,
    SnapshotContract,
    SnapshotEvidence,
    SnapshotGuard,
    SnapshotReplay,
    SnapshotReview,
)
from counterguard.snapshot_repository import SnapshotManifest

MODELS = (
    SnapshotManifest,
    SnapshotContract,
    SnapshotBinding,
    SnapshotReview,
    SnapshotAuthorization,
    SnapshotEvidence,
    SnapshotGuard,
    SnapshotReplay,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "schemas/research-snapshot-v1"
    for model in MODELS:
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        raw = (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode()
        name = model.model_fields["schema_version"].default + ".schema.json"
        if args.check:
            if (root / name).read_bytes() != raw:
                raise ValueError("Snapshot schema differs from its strict runtime model")
        else:
            write_immutable(root / name, raw)
    print(f"{len(MODELS)} research snapshot schemas {'match' if args.check else 'exported'}")


if __name__ == "__main__":
    main()
