"""Export only the new experimental research schemas; never rewrite old schemas."""

import argparse
import json
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.study_models import (
    StudyAdmission,
    StudyAuthorization,
    StudyCallMap,
    StudyReplay,
    StudyReplayPlan,
    StudyReview,
    StudySource,
    StudyTarget,
    StudyWitness,
)

MODELS = (
    StudySource,
    StudyTarget,
    StudyCallMap,
    StudyWitness,
    StudyReview,
    StudyReplayPlan,
    StudyAdmission,
    StudyAuthorization,
    StudyReplay,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1] / "schemas/research-v1"
    for model in MODELS:
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        raw = (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode()
        name = model.model_fields["schema_version"].default + ".schema.json"
        if args.check:
            if (root / name).read_bytes() != raw:
                raise ValueError("Research schema differs from its strict runtime model")
        else:
            write_immutable(root / name, raw)
    print(
        f"{len(MODELS)} research schemas match"
        if args.check
        else f"{len(MODELS)} research schemas exported"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
