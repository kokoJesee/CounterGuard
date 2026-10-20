"""Finite diagnostics for explicit experimental study commands."""

import json

from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.repository import RepositoryProblem
from counterguard.standalone_capture import _model, _ref
from counterguard.study_data import StudyNotReady
from counterguard.study_models import StudyReplayPlan
from counterguard.study_replay import StudySession, replay_exit_code


def execute_study_command(args):
    try:
        session = StudySession(
            args.source_repo, args.target_repo, args.workspace, args.review_digest
        )
        if args.command == "verify":
            result = session.verify(args.result)
            code = 0
        else:
            plan = _model(session.workspace, _ref(args.plan, session.workspace), StudyReplayPlan)
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
