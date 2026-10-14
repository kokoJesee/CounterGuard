"""Export the public persistence contracts from their authoritative models."""

import json
from pathlib import Path

from evidenceguard.baselines import FeatureVector, ScopePredicate
from evidenceguard.models import Evidence, Guard, RunRecord
from evidenceguard.protocol import ExperimentProtocol, SplitManifest

MODELS = {
    "evidence": Evidence,
    "guard": Guard,
    "run-record": RunRecord,
    "feature-vector": FeatureVector,
    "scope-predicate": ScopePredicate,
    "experiment-protocol": ExperimentProtocol,
    "split-manifest": SplitManifest,
}

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "schemas"
    root.mkdir(exist_ok=True)
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (root / f"{name}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
