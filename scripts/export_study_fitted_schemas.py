"""Export only fit-aware research replay schemas; never rewrite old versions."""

import argparse
import json
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.study_fitted_models import (
    StudyFittedAdmission,
    StudyFittedAuthorization,
    StudyFittedPlan,
    StudyFittedReplay,
    StudyFittedReview,
)

MODELS = (
    StudyFittedPlan,
    StudyFittedReview,
    StudyFittedAdmission,
    StudyFittedAuthorization,
    StudyFittedReplay,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1] / "schemas/research-v2"
    for model in MODELS:
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        raw = (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode()
        path = root / (model.model_fields["schema_version"].default + ".schema.json")
        if args.check:
            if path.read_bytes() != raw:
                raise ValueError("Research v2 schema differs from strict runtime model")
        else:
            write_immutable(path, raw)
    print(f"{len(MODELS)} research v2 schemas {'match' if args.check else 'exported'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
