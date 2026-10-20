"""Finite diagnostics for explicit experimental study commands."""

import json

from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.repository import RepositoryProblem
from counterguard.standalone_capture import _file, _model, _ref
from counterguard.standalone_contracts import strict_json
from counterguard.study_data import StudyNotReady, repository_identity
from counterguard.study_replay import StudySession, replay_exit_code


def execute_study_command(args):
    try:
        workspace = args.workspace.resolve(strict=True)
        path = args.result if args.command == "verify" else args.plan
        ref = _ref(path, workspace)
        version = strict_json(_file(workspace, ref), limit=4 * 1024 * 1024)["schema_version"]
        if version in {"study-replay.v2", "study-replay-plan.v2"}:
            from counterguard.study_fit import StudyFitSession
            from counterguard.study_fitted import StudyFittedSession

            fit_session = StudyFitSession(
                args.source_repo,
                workspace,
                {repository_identity(p): p for p in getattr(args, "training_repository", [])},
                getattr(args, "fit_review_digest", None),
            )
            session = StudyFittedSession(
                args.source_repo, args.target_repo, workspace, args.review_digest, fit_session
            )
        elif version in {"study-replay.v1", "study-replay-plan.v1"}:
            if getattr(args, "fit_review_digest", None) or getattr(args, "training_repository", []):
                raise ValueError("C1 inputs cannot consume new fit trust arguments")
            session = StudySession(
                args.source_repo, args.target_repo, workspace, args.review_digest
            )
        else:
            raise ValueError("Unsupported study version")
        if args.command == "verify":
            result = session.verify(args.result)
            code = 0
        else:
            plan = _model(session.workspace, ref, session._plan_model)
            if args.command == "audit":
                result = session.audit(plan)
                code = 4 if result.decision == "unknown" else 0
            else:
                result = session.replay(plan, args.output)
                code = replay_exit_code(result)
    except StudyNotReady as error:
        print(json.dumps({"status": "unknown", "reason_code": str(error)}))
        return 4
    except (ArtifactIntegrityError, RepositoryProblem, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "rejected", "reason_code": "study_input_invalid"}))
        return 5
    print(canonical_json_bytes(result).decode())
    return code
