"""Export the pure fixture metrics contracts without changing old schemas."""

import argparse
import json
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.study_metrics import StudyMetricInput, StudyMetricSummary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1] / "schemas/study-metrics-v1"
    for model in (StudyMetricInput, StudyMetricSummary):
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        raw = (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode()
        path = root / (model.model_fields["schema_version"].default + ".schema.json")
        if args.check:
            if path.read_bytes() != raw:
                raise ValueError("Metrics schema differs from the closed runtime model")
        else:
            write_immutable(path, raw)
    print("2 study metric schemas match" if args.check else "2 study metric schemas exported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
