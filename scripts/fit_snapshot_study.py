"""Fit/verify tool-owned complete snapshots; no external, holdout or execution mode."""

import argparse
import json
from pathlib import Path

from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError, FeatureExtractionError
from counterguard.project_config import repository_path
from counterguard.repository import RepositoryProblem
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_study_fit import SnapshotStudyFitSession
from counterguard.study_data import StudyNotReady, repository_identity


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fit", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--workspace", type=Path, required=True)
        command.add_argument("--source-repo", type=Path, required=True)
        command.add_argument("--source-binding", required=True)
        command.add_argument("--source-review", required=True)
        command.add_argument("--source-review-digest", required=True)
        command.add_argument("--repository", type=Path, action="append", default=[])
        command.add_argument("--fit-review-digest", required=True)
        if name == "fit":
            command.add_argument("--protocol", required=True)
            command.add_argument("--review", required=True)
            command.add_argument("--phase", choices=("initial", "refined"), required=True)
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--result", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        workspace = args.workspace.resolve(strict=True)
        source = SnapshotSession(
            args.source_repo.resolve(strict=True),
            workspace,
            workspace / repository_path(args.source_binding),
            workspace / repository_path(args.source_review),
            args.source_review_digest,
        )
        session = SnapshotStudyFitSession(
            source,
            {repository_identity(p): p for p in args.repository},
            args.fit_review_digest,
        )
        result = (
            session.verify(args.result)
            if args.command == "verify"
            else session.fit(args.protocol, args.review, phase=args.phase, output=args.output)
        )
    except (StudyNotReady, FeatureExtractionError) as error:
        code = (
            str(error)
            if isinstance(error, StudyNotReady)
            else "snapshot_study_features_unsupported"
        )
        print(json.dumps({"status": "unknown", "reason_code": code}))
        return 4
    except (ArtifactIntegrityError, RepositoryProblem, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "rejected", "reason_code": "snapshot_study_input_invalid"}))
        return 5
    print(canonical_json_bytes(result).decode())
    return 0 if args.command == "verify" or result.status == "fitted" else 4


if __name__ == "__main__":
    raise SystemExit(main())
