"""Export or check the strict scope_v2 readiness schema."""

import argparse
import json
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.scope_v2_readiness import ScopeV2Readiness


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    path = Path(__file__).resolve().parents[1] / "schemas/scope-v2-readiness.schema.json"
    schema = ScopeV2Readiness.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    raw = (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode()
    if args.check:
        if path.read_bytes() != raw:
            raise ValueError("scope_v2 readiness schema differs from runtime model")
    else:
        write_immutable(path, raw)
    print("scope_v2 readiness schema " + ("matches" if args.check else "exported"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
