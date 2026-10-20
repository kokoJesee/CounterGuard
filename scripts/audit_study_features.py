"""Static tool-owned fixture features; does not import or execute target Python."""

import argparse
import json
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError, FeatureExtractionError
from counterguard.predicates import FeatureVector
from counterguard.project_config import reject_links, repository_path
from counterguard.standalone_capture import _file, _model, _ref
from counterguard.standalone_contracts import strict_json
from counterguard.study_features import (
    MAX_SOURCE_BYTES,
    StudyFeatureContext,
    audit_study_features,
    extract_study_features,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--context-digest", required=True, help="Separate trusted context anchor.")
    parser.add_argument("--expected", type=Path, help="Independent manual FeatureVector JSON.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        reject_links(args.workspace)
        workspace = args.workspace.resolve(strict=True)
        context = _model(workspace, _ref(args.context, workspace), StudyFeatureContext)
        source = _file(workspace, context.source_ref, limit=MAX_SOURCE_BYTES)
        if args.expected:
            expected_raw = _file(workspace, _ref(args.expected, workspace), limit=65536)
            expected = FeatureVector.model_validate_json(
                canonical_json_bytes(strict_json(expected_raw, limit=65536))
            )
            result = audit_study_features(
                source, context, expected, context_anchor=args.context_digest
            )
            code = 0 if result.matched else 4
        else:
            result = extract_study_features(source, context, context_anchor=args.context_digest)
            code = 0
        output = args.output if args.output.is_absolute() else workspace / args.output
        reject_links(output)
        relative = output.resolve().relative_to(workspace).as_posix()
        repository_path(relative)
        write_immutable(workspace / relative, canonical_json_bytes(result))
    except FeatureExtractionError:
        print(json.dumps({"status": "unknown", "reason_code": "study_feature_syntax_unsupported"}))
        return 4
    except (ArtifactIntegrityError, OSError, ValueError, KeyError, TypeError, RecursionError):
        print(json.dumps({"status": "rejected", "reason_code": "study_feature_input_invalid"}))
        return 5
    print(canonical_json_bytes(result).decode())
    return code


if __name__ == "__main__":
    raise SystemExit(main())
