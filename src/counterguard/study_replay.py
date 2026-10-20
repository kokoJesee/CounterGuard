"""Research-only audit/replay/verify with separate authority and shared Docker transport."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

from pydantic import TypeAdapter

from counterguard.artifacts import write_immutable
from counterguard.bootstrap_binding import _new_output
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError, GuardReplayIntegrityError
from counterguard.execution import PytestRunRequest, _execute_with_adapter, verify_run_record
from counterguard.models import Digest, RunOutcome, RunRecord, RunRole, TargetRef
from counterguard.path_limits import require_paths, require_publication, require_run_directory
from counterguard.repository import RepositoryProblem, read_committed_files
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import (
    DockerPolicyV1,
    ExecutionInputPin,
    _AdmittedDockerProcess,
    _docker_executable,
    _require_image_identity,
)
from counterguard.standalone_capture import (
    ZERO,
    _file,
    _model,
    _ref,
    _request_digest,
    _require,
    _seal,
    _verify_run_envelope,
)
from counterguard.standalone_test import CONTRACT_REF, TEST_REF, runtime_case_id
from counterguard.study_data import StudyNotReady, load_facts, load_review, persist
from counterguard.study_models import (
    StudyAdmission,
    StudyAuthorization,
    StudyInputOrigin,
    StudyReplay,
    StudyReplayPlan,
)
from counterguard.study_test import render_study_test


def _outcome(run):
    return {
        RunOutcome.PASSED: "passed",
        RunOutcome.TEST_FAILED: "test_failed",
    }.get(run.outcome, "infrastructure_error")


def replay_exit_code(value):
    if value.integrity != "current":
        return 5
    if value.outcome == "infrastructure_error":
        return 3
    if value.outcome == "skipped_unknown":
        return 4
    return 0  # Completed observation, including test_failed, is not an applicability label.


@dataclass(frozen=True)
class StudySession:
    source_repo: Path
    target_repo: Path
    workspace: Path
    review_anchor: str
    _plan_model: ClassVar[type] = StudyReplayPlan
    _result_model: ClassVar[type] = StudyReplay
    _authorization_model: ClassVar[type] = StudyAuthorization

    def __post_init__(self):
        TypeAdapter(Digest).validate_python(self.review_anchor)
        for field in ("source_repo", "target_repo", "workspace"):
            from counterguard.project_config import reject_links

            path = getattr(self, field)
            reject_links(path)
            object.__setattr__(self, field, path.resolve(strict=True))

    def _checked_plan(self, plan):
        plan = self._plan_model.model_validate_json(canonical_json_bytes(plan))
        _require(plan.artifact_digest == digest_json_artifact(plan), "study_plan_digest_mismatch")
        return plan

    def _review(self, plan):
        return load_review(self.workspace, plan.review_ref, self.review_anchor)

    def _load(self, plan):
        plan = self._checked_plan(plan)
        loaded = load_facts(self.source_repo, self.target_repo, self.workspace, plan)
        source, target, mapping, witness, _, facts, _, _ = loaded
        review = self._review(plan)
        _require(
            (review.source_digest, review.target_digest, review.map_digest, review.witness_digest)
            == (
                source.artifact_digest,
                target.artifact_digest,
                mapping.artifact_digest,
                witness.artifact_digest if witness else None,
            ),
            "study_review_subject_mismatch",
        )
        _require(
            review.implementation_digests == inspection_implementation_digests(),
            "study_review_implementation_stale",
        )
        _require(
            review.policy_digest == digest_json_artifact(DockerPolicyV1()),
            "study_review_policy_mismatch",
        )
        runner = resolve_runner(runner_id=review.runner.runner_id, image_digest=None)
        _require(runner == review.runner == facts[2].runner, "study_runner_review_mismatch")
        _require(
            plan.timeout_seconds <= facts[2].timeout_seconds, "study_timeout_exceeds_source_budget"
        )
        return self._decide(plan, loaded, review), loaded, review

    def _decide(self, plan, loaded, review):
        source, target, mapping, witness, _, _, _, _ = loaded
        decision, reason = "applicable", "study_unscoped_method"
        if review.action != "approve":
            decision, reason = "unknown", "study_review_withdrawn"
        elif plan.method.startswith("learned_"):
            decision, reason = "unknown", "study_fit_interface_not_implemented"
        elif plan.lane == "witness" and (witness is None or plan.method != "b1_always"):
            decision, reason = "unknown", "study_witness_requires_reviewed_unscoped_plan"
        elif plan.method == "b2_interface":
            if review.source_interface == review.target_interface:
                reason = "study_fixture_interface_matches"
            else:
                decision, reason = "inapplicable", "study_fixture_interface_differs"
        admission = _seal(
            StudyAdmission(
                decision=decision,
                reason_code=reason,
                source_digest=source.artifact_digest,
                target_digest=target.artifact_digest,
                map_digest=mapping.artifact_digest,
                review_digest=review.artifact_digest,
                witness_digest=witness.artifact_digest if witness else None,
                method=plan.method,
                lane=plan.lane,
                artifact_digest=ZERO,
            )
        )
        return admission

    def _make_authorization(self, plan, admission, **payload):
        return _seal(self._authorization_model(**payload))

    def _make_result(self, **payload):
        return _seal(self._result_model(**payload))

    def _check_result_anchors(self, result):
        _require(result.review_anchor == self.review_anchor, "study_result_review_anchor_changed")

    def audit(self, plan):
        """No Docker discovery or target execution, including genuine unknown inputs."""
        return self._load(plan)[0]

    def _request(self, plan, runtime, loaded, run_id):
        source, target, _, witness, _, facts, _, mapped = loaded
        ids = tuple(c.case_id for c in (witness.cases if plan.lane == "witness" else mapped))
        return PytestRunRequest(
            role=RunRole.REPLAY,
            contract_id=facts[-1].contract_id,
            contract_digest=source.contract_digest,
            target=TargetRef(
                module=target.module, symbol=target.symbol, source_ref=target.source_ref
            ),
            target_digest=next(
                p.content_digest for p in target.tree_pins if p.path == target.source_ref
            ),
            test_path=runtime / TEST_REF,
            known_case_ids=tuple(runtime_case_id(c) for c in ids),
            cwd=runtime,
            artifact_root=runtime / "r",
            timeout_seconds=plan.timeout_seconds,
            run_id=run_id,
            contract_path=runtime / CONTRACT_REF,
        )

    def _authorize(self, plan, runtime, request):
        admission, loaded, review = self._load(plan)
        _require(admission.decision == "applicable", "study_execution_not_applicable")
        source, target, mapping, witness, _, facts, _, mapped = loaded
        _require(request.run_id is not None, "study_run_identity_required")
        _require(
            request == self._request(plan, runtime, loaded, request.run_id),
            "study_request_exceeds_reviewed_inputs",
        )
        _, _, _, binding, contract = facts
        test = render_study_test(
            contract, target, mapped, witness if plan.lane == "witness" else None
        )
        _require(_file(runtime, TEST_REF) == test, "study_test_not_canonical")
        head = {p["path"]: p for p in binding["trees"]["head"]["files"]}
        source_pin = head[source.contract_ref]
        origins = [
            StudyInputOrigin(
                path=CONTRACT_REF,
                origin="source_contract",
                repository_identity_digest=source.repository_identity_digest,
                revision=source.assertion_head,
                original_ref=source.contract_ref,
            )
        ]
        pins = [
            ExecutionInputPin(
                path=CONTRACT_REF,
                object_id=source_pin["object_id"],
                content_digest=source.contract_digest,
            )
        ]
        for pin in target.closure_pins:
            pins.append(pin)
            origins.append(
                StudyInputOrigin(
                    path=pin.path,
                    origin="target_source",
                    repository_identity_digest=target.repository_identity_digest,
                    revision=target.revision,
                    original_ref=pin.path,
                )
            )
        for pin in pins:
            _require(
                digest_bytes(_file(runtime, pin.path)) == pin.content_digest,
                "study_materialized_input_changed",
            )
        return self._make_authorization(
            plan,
            admission,
            source_head=source.assertion_head,
            target_revision=target.revision,
            source_digest=source.artifact_digest,
            target_digest=target.artifact_digest,
            map_digest=mapping.artifact_digest,
            review_digest=review.artifact_digest,
            witness_digest=witness.artifact_digest if witness else None,
            admission_digest=admission.artifact_digest,
            plan_digest=plan.artifact_digest,
            image_digest=review.runner.image_digest,
            runner_review_digest=review.runner.artifact_digest,
            policy_digest=review.policy_digest,
            implementation_digests=review.implementation_digests,
            request_digest=_request_digest(request),
            input_pins=tuple(sorted(pins, key=lambda p: p.path)),
            input_origins=tuple(sorted(origins, key=lambda p: p.path)),
            import_root=target.import_root,
            test_ref=TEST_REF,
            test_digest=digest_bytes(test),
            known_case_ids=request.known_case_ids,
            artifact_digest=ZERO,
        )

    def replay(self, plan, output):
        output = _new_output(self.source_repo, output, self.workspace)
        _require(not output.is_relative_to(self.target_repo), "study_output_inside_target")
        for name in ("result.json", "plan.json", "w/authorization.json", "w/r/record.json"):
            require_publication(output / name)
        plan_ref = (output / "plan.json").relative_to(self.workspace).as_posix()
        # Revalidate model_copy or directly constructed caller data before persisting a plan.
        plan = self._checked_plan(plan)
        persist(output / "plan.json", plan)
        admission, run, auth_ref, record_ref = None, None, None, None
        integrity = "current"
        try:
            admission, loaded, _ = self._load(plan)
            if admission.decision != "applicable":
                outcome = "skipped_" + admission.decision
                reason = admission.reason_code
            else:
                source, target, _, witness, _, facts, files, mapped = loaded
                runtime = output / "w"
                run_id = "run_" + uuid4().hex
                refs = [p.path for p in target.closure_pins] + [CONTRACT_REF, TEST_REF]
                for ref in refs:
                    require_publication(runtime / ref)
                    require_paths(runtime / "r/runs" / run_id / "sandbox-input" / ref)
                require_run_directory(runtime / "r/runs" / run_id)
                for pin in target.closure_pins:
                    write_immutable(runtime / pin.path, files[pin.path])
                # Preserve the exact source H blob, including its original source target.
                _, head_files, _ = read_committed_files(self.source_repo, source.assertion_head)
                _require(
                    digest_bytes(head_files[source.contract_ref]) == source.contract_digest,
                    "study_source_contract_changed",
                )
                write_immutable(runtime / CONTRACT_REF, head_files[source.contract_ref])
                write_immutable(
                    runtime / TEST_REF,
                    render_study_test(
                        facts[-1], target, mapped, witness if plan.lane == "witness" else None
                    ),
                )
                request = self._request(plan, runtime, loaded, run_id)
                auth = self._authorize(plan, runtime, request)
                auth_ref = (runtime / "authorization.json").relative_to(self.workspace).as_posix()
                record_ref = (runtime / "r/record.json").relative_to(self.workspace).as_posix()
                persist(runtime / "authorization.json", auth)
                executor = _StudyDockerExecutor(
                    auth, lambda request: self._authorize(plan, runtime, request), facts[2]
                )
                run = executor.execute(request)
                outcome, reason = _outcome(run), "study_observation_completed"
        except GuardReplayIntegrityError as error:
            run = error.run
            integrity, outcome, reason = (
                "stale",
                "integrity_error",
                "study_inputs_changed_after_execution",
            )
        except StudyNotReady as error:
            outcome, reason = "skipped_unknown", str(error)
        except (ArtifactIntegrityError, RepositoryProblem, OSError, ValueError, KeyError):
            integrity, outcome, reason = "invalid", "integrity_error", "study_inputs_invalid"
        if run is None:
            record_ref = None
        result = self._make_result(
            created_at=datetime.now(UTC),
            plan_ref=plan_ref,
            plan_digest=plan.artifact_digest,
            review_anchor=self.review_anchor,
            admission=admission,
            integrity=integrity,
            outcome=outcome,
            reason_code=reason,
            run=run,
            authorization_ref=auth_ref,
            record_ref=record_ref,
            artifact_digest=ZERO,
        )
        return persist(output / "result.json", result)

    def verify(self, path):
        ref = _ref(path, self.workspace)
        result = _model(self.workspace, ref, self._result_model)
        self._check_result_anchors(result)
        folder = Path(ref).parent.as_posix()
        _require(result.plan_ref == folder + "/plan.json", "study_result_plan_layout_changed")
        plan = _model(self.workspace, result.plan_ref, self._plan_model)
        _require(plan.artifact_digest == result.plan_digest, "study_result_plan_changed")
        admission, loaded, _ = self._load(plan)
        _require(
            result.integrity == "current" and result.admission == admission,
            "study_result_admission_stale",
        )
        if admission.decision != "applicable":
            _require(
                result.run is None
                and result.authorization_ref is None
                and result.record_ref is None
                and result.outcome == "skipped_" + admission.decision
                and result.reason_code == admission.reason_code,
                "study_skipped_result_not_rebuilt",
            )
            return result
        _require(result.run is not None, "study_applicable_result_missing_run")
        runtime = self.workspace / folder / "w"
        _require(
            result.record_ref == folder + "/w/r/record.json"
            and result.authorization_ref == folder + "/w/authorization.json",
            "study_result_execution_layout_changed",
        )
        request = self._request(plan, runtime, loaded, result.run.run_id)
        auth = _model(self.workspace, result.authorization_ref, self._authorization_model)
        _require(auth == self._authorize(plan, runtime, request), "study_authorization_not_rebuilt")
        stored = RunRecord.model_validate_json(_file(self.workspace, result.record_ref))
        _require(stored == result.run, "study_run_record_changed")
        _verify_study_run(stored, request, loaded[5][2], auth.import_root)
        _require(
            result.outcome == _outcome(stored)
            and result.reason_code == "study_observation_completed",
            "study_result_outcome_changed",
        )
        return result


def _verify_study_run(run, request, capture, import_root):
    _require(
        run.role is RunRole.REPLAY
        and run.target == request.target
        and run.target_digest == request.target_digest
        and run.contract_id == request.contract_id
        and run.contract_digest == request.contract_digest
        and run.run_id == request.run_id
        and run.cwd == "."
        and run.timeout_seconds == request.timeout_seconds,
        "study_run_identity_changed",
    )
    _verify_run_envelope(run, request, capture, import_root=import_root)
    for ref in (run.stdout_ref, run.stderr_ref, run.junit_ref):
        _file(request.cwd, ref)
    verify_run_record(run, cwd=request.cwd, known_case_ids=request.known_case_ids)


@dataclass(frozen=True)
class _StudyDockerExecutor:
    authorization: StudyAuthorization
    authorizer: object
    capture: object
    policy: DockerPolicyV1 = DockerPolicyV1()

    def execute(self, request):
        _require(self.policy == DockerPolicyV1(), "study_executor_policy_mismatch")
        _require(self.authorizer(request) == self.authorization, "study_authorization_stale")
        executable = _docker_executable()
        _require_image_identity(executable, self.authorization.image_digest, self.policy)
        run = _execute_with_adapter(request, _AdmittedDockerProcess(self, executable))
        write_immutable(request.artifact_root / "record.json", canonical_json_bytes(run))
        try:
            _require(self.authorizer(request) == self.authorization, "study_authorization_stale")
            _verify_study_run(run, request, self.capture, self.authorization.import_root)
        except (ArtifactIntegrityError, RepositoryProblem, OSError, ValueError) as error:
            raise GuardReplayIntegrityError("study_inputs_changed_after_execution", run) from error
        return run
