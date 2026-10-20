"""Fit/verify reviewed tool-owned training fixtures; no holdout or execution mode."""

import argparse
import json
from pathlib import Path

from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError, FeatureExtractionError
from counterguard.repository import RepositoryProblem
from counterguard.study_data import StudyNotReady, repository_identity
from counterguard.study_fit import StudyFitSession


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fit", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--workspace", type=Path, required=True)
        command.add_argument("--source-repo", type=Path, required=True)
        command.add_argument("--repository", type=Path, action="append", default=[])
        command.add_argument("--review-digest", required=True)
        if name == "fit":
            command.add_argument("--protocol", required=True)
            command.add_argument("--review", required=True)
            command.add_argument("--phase", choices=("initial", "refined"), required=True)
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--result", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        session = StudyFitSession(
            args.source_repo,
            args.workspace,
            {repository_identity(p): p for p in args.repository},
            args.review_digest,
        )
        result = (
            session.verify(args.result)
            if args.command == "verify"
            else session.fit(args.protocol, args.review, phase=args.phase, output=args.output)
        )
    except (StudyNotReady, FeatureExtractionError) as error:
        code = str(error) if isinstance(error, StudyNotReady) else "study_fit_features_unsupported"
        print(json.dumps({"status": "unknown", "reason_code": code}))
        return 4
    except (ArtifactIntegrityError, RepositoryProblem, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "rejected", "reason_code": "study_fit_input_invalid"}))
        return 5
    print(canonical_json_bytes(result).decode())
    return 0 if args.command == "verify" or result.status == "fitted" else 4


if __name__ == "__main__":
    raise SystemExit(main())
