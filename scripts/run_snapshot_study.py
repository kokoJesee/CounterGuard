"""Explicit tool-owned snapshot study commands; never infer external or holdout authority."""

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from counterguard.digests import canonical_json_bytes, digest_bytes
from counterguard.errors import ArtifactIntegrityError, FeatureExtractionError
from counterguard.models import Digest, FrozenModel
from counterguard.project_config import Identifier, RepositoryPath, reject_links
from counterguard.repository import RepositoryProblem
from counterguard.snapshot_admission import require
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_study_evaluation import SnapshotStudyEvaluationSession
from counterguard.snapshot_study_fit import SnapshotStudyFitSession
from counterguard.snapshot_study_replay import SnapshotStudyReplaySession
from counterguard.snapshot_study_replay_models import SnapshotStudyPlan
from counterguard.standalone_capture import _model
from counterguard.standalone_contracts import strict_json
from counterguard.study_data import StudyNotReady, repository_identity


class FixtureSessionSpec(FrozenModel):
    row_id: Identifier
    source_repo: RepositoryPath
    target_repo: RepositoryPath
    source_binding: RepositoryPath
    source_review: RepositoryPath
    source_review_digest: Digest
    fit_review_digest: Digest
    execution_review_digest: Digest
    repositories: Annotated[tuple[RepositoryPath, ...], Field(max_length=32)] = ()


class FixtureRoster(FrozenModel):
    schema_version: Literal["snapshot-study-cli-roster.v1"] = "snapshot-study-cli-roster.v1"
    purpose: Literal["tool_owned_snapshot_study_only"] = "tool_owned_snapshot_study_only"
    sessions: Annotated[tuple[FixtureSessionSpec, ...], Field(min_length=1, max_length=32)]


def load_sessions(workspace, roster_ref, trusted_digest):
    path = workspace / roster_ref
    reject_links(path)
    require(path.resolve().is_relative_to(workspace), "snapshot_study_roster_path_escape")
    require(
        path.is_file() and path.stat().st_nlink == 1 and path.stat().st_size <= 4194304,
        "snapshot_study_roster_file_invalid",
    )
    raw = path.read_bytes()
    require(digest_bytes(raw) == trusted_digest, "snapshot_study_roster_anchor_changed")
    strict_json(raw, limit=4194304)
    roster = FixtureRoster.model_validate_json(raw)
    sessions = {}
    for item in roster.sessions:
        require(item.row_id not in sessions, "snapshot_study_duplicate_roster_row")
        source = SnapshotSession(
            (workspace / item.source_repo).resolve(strict=True),
            workspace,
            workspace / item.source_binding,
            workspace / item.source_review,
            item.source_review_digest,
        )
        fit = SnapshotStudyFitSession(
            source,
            {repository_identity(workspace / ref): workspace / ref for ref in item.repositories},
            item.fit_review_digest,
        )
        sessions[item.row_id] = SnapshotStudyReplaySession(
            source,
            (workspace / item.target_repo).resolve(strict=True),
            item.execution_review_digest,
            fit,
        )
    return sessions


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "fit":
        # Explicit sibling command, not a parser fallback or artifact-version guess.
        if __package__:
            from .fit_snapshot_study import main as fit_main
        else:
            from fit_snapshot_study import main as fit_main
        return fit_main(argv)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fit", help="Use the strict train-only fit command (fit --help)")
    for name in ("audit", "replay", "evaluate", "verify", "compare", "report", "export"):
        command = sub.add_parser(name)
        command.add_argument("--workspace", type=Path, required=True)
        command.add_argument("--roster", type=Path, required=True)
        command.add_argument("--roster-digest", required=True)
        command.add_argument("--row")
        command.add_argument("--kind", choices=("replay", "evaluation"), default="replay")
        command.add_argument("--evaluation-review-digest")
        if name in {"audit", "replay", "evaluate"}:
            command.add_argument("--plan", required=True)
        else:
            command.add_argument("--result", type=Path, required=True)
        if name in {"evaluate", "audit"}:
            command.add_argument("--review")
        if name in {"replay", "evaluate", "compare", "report", "export"}:
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    evaluation = (
        args.command in {"evaluate", "compare", "report", "export"} or args.kind == "evaluation"
    )
    if evaluation and not args.evaluation_review_digest:
        parser.error("evaluation commands require --evaluation-review-digest")
    if evaluation and args.command in {"audit", "evaluate"} and not args.review:
        parser.error("evaluation audit/evaluate requires --review")
    if not evaluation and not args.row:
        parser.error("replay audit/replay/verify requires --row")
    if args.command == "replay" and evaluation:
        parser.error("replay only accepts --kind replay")
    try:
        workspace = args.workspace.resolve(strict=True)
        sessions = load_sessions(workspace, args.roster, args.roster_digest)
        if evaluation:
            engine = SnapshotStudyEvaluationSession(
                workspace, sessions, args.evaluation_review_digest
            )
            if args.command == "audit":
                result = engine.audit(args.plan, args.review)
            elif args.command == "evaluate":
                result = engine.evaluate(args.plan, args.review, output=args.output)
            elif args.command == "verify":
                result = engine.verify(args.result)
            else:
                result = getattr(engine, args.command)(args.result, output=args.output)
        else:
            require(args.row in sessions, "snapshot_study_roster_row_missing")
            engine = sessions[args.row]
            if args.command == "verify":
                result = engine.verify(args.result)
            else:
                plan = _model(workspace, args.plan, SnapshotStudyPlan)
                result = (
                    engine.audit(plan)
                    if args.command == "audit"
                    else engine.run(plan, output=args.output)
                )
    except (StudyNotReady, FeatureExtractionError) as error:
        print(
            json.dumps(
                {
                    "status": "unknown",
                    "reason_code": str(error)
                    if isinstance(error, StudyNotReady)
                    else "snapshot_study_features_unsupported",
                }
            )
        )
        return 4
    except (ArtifactIntegrityError, RepositoryProblem, OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "rejected", "reason_code": "snapshot_study_input_invalid"}))
        return 5
    print(canonical_json_bytes(result).decode())
    if not evaluation and args.command in {"audit", "replay"}:
        decision = result.decision if args.command == "audit" else result.admission.decision
        if decision == "unknown":
            return 4
        if args.command == "replay" and result.outcome in {
            "infrastructure_error",
            "integrity_error",
        }:
            return 3
    if args.command == "evaluate" and getattr(result, "execution_failures", 0):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
