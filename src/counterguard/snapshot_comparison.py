"""Fixture-only full-snapshot comparison using the existing closed Docker transport."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError, GuardReplayIntegrityError
from counterguard.execution import PytestRunRequest, _execute_with_adapter, verify_run_record
from counterguard.models import Digest, RunOutcome, RunRecord, RunRole, TargetRef
from counterguard.path_limits import require_paths, require_publication, require_run_directory
from counterguard.project_config import reject_links
from counterguard.repository import RepositoryProblem
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import (
    DockerPolicyV1,
    ExecutionInputPin,
    _AdmittedDockerProcess,
    _docker_executable,
    _require_image_identity,
)
from counterguard.snapshot_admission import JSON_LIMIT, read_value, require, seal
from counterguard.snapshot_comparison_data import load_comparison_facts
from counterguard.snapshot_comparison_models import (
    SnapshotComparisonAdmission,
    SnapshotComparisonAuthorization,
    SnapshotComparisonPlan,
    SnapshotComparisonReplay,
    SnapshotComparisonReview,
)
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_models import ZERO
from counterguard.standalone_capture import _request_digest, _verify_run_envelope
from counterguard.standalone_contracts import strict_json
from counterguard.standalone_test import (
    CONTRACT_REF,
    TEST_REF,
    _render_literal_test,
    runtime_case_id,
)


@dataclass(frozen=True)
class _CallView:
    target_module: str
    target_symbol: str
    cases: tuple


def render_comparison_test(facts, lane):
    require(
        lane == "guard" or lane == "own_contract" and facts.witness is not None,
        "comparison_oracle_lane_unavailable",
    )
    cases = facts.cases if lane == "guard" else facts.witness.cases
    view = _CallView(facts.target.entry.target_module, facts.target.entry.target_symbol, cases)
    return _render_literal_test(view, message_cases=True, generator="snapshot-comparison-test.v1")


def decide_comparison(plan, facts, review):
    decision, reason = "applicable", "comparison_unscoped_method"
    if review.action != "approve":
        decision, reason = "unknown", "comparison_review_withdrawn"
    elif plan.method.startswith("learned_"):
        decision, reason = "unknown", "comparison_snapshot_fit_not_bound"
    elif plan.lane == "own_contract" and (facts.witness is None or plan.method != "b1_always"):
        decision, reason = "unknown", "comparison_own_lane_requires_reviewed_b1_witness"
    elif plan.method == "b2_interface":
        if review.source_interface == facts.target.interface_kind:
            reason = "comparison_interface_matches"
        else:
            decision, reason = "inapplicable", "comparison_interface_differs"
    return seal(
        SnapshotComparisonAdmission(
            plan_digest=plan.artifact_digest,
            guard_digest=facts.guard.artifact_digest,
            target_digest=facts.target.artifact_digest,
            map_digest=facts.mapping.artifact_digest,
            review_digest=review.artifact_digest,
            witness_digest=facts.witness.artifact_digest if facts.witness else None,
            method=plan.method,
            lane=plan.lane,
            decision=decision,
            reason_code=reason,
            artifact_digest=ZERO,
        )
    )


def _outcome(run):
    return {RunOutcome.PASSED: "passed", RunOutcome.TEST_FAILED: "test_failed"}.get(
        run.outcome, "infrastructure_error"
    )


@dataclass(frozen=True)
class SnapshotComparisonSession:
    source: SnapshotSession
    target_repo: Path
    review_anchor: str

    def __post_init__(self):
        reject_links(self.target_repo)
        require(
            self.target_repo.is_absolute() and self.target_repo == self.target_repo.resolve(),
            "comparison_canonical_target_repository_required",
        )
        require(
            self.target_repo != self.source.repo, "comparison_target_must_be_separate_repository"
        )
        TypeAdapter(Digest).validate_python(self.review_anchor)

    def _checked_plan(self, value):
        value = SnapshotComparisonPlan.model_validate_json(canonical_json_bytes(value))
        require(
            value.artifact_digest == digest_json_artifact(value), "comparison_plan_digest_mismatch"
        )
        return value

    def _load(self, plan):
        plan = self._checked_plan(plan)
        review = read_value(
            self.source.workspace / plan.review_ref,
            SnapshotComparisonReview,
            expected_digest=self.review_anchor,
        )
        require(
            review.source_review_digest == self.source.trusted_digest,
            "comparison_source_review_anchor_changed",
        )
        require(
            review.implementation_digests == inspection_implementation_digests()
            and review.policy_digest == digest_json_artifact(DockerPolicyV1()),
            "comparison_implementation_or_policy_stale",
        )
        facts = load_comparison_facts(self.source, self.target_repo, plan)
        require(
            (
                review.source_guard_digest,
                review.source_binding_digest,
                review.target_digest,
                review.map_digest,
                review.witness_digest,
            )
            == (
                facts.guard.artifact_digest,
                facts.binding.artifact_digest,
                facts.target.artifact_digest,
                facts.mapping.artifact_digest,
                facts.witness.artifact_digest if facts.witness else None,
            ),
            "comparison_review_subject_mismatch",
        )
        require(
            review.source_interface_basis_ref in facts.binding.package_refs["fixed"],
            "comparison_source_interface_basis_missing",
        )
        require(
            resolve_runner(runner_id=review.runner.runner_id, image_digest=None)
            == review.runner
            == facts.source_review.runner,
            "comparison_runner_changed",
        )
        require(
            plan.timeout_seconds <= review.timeout_seconds <= facts.source_review.timeout_seconds,
            "comparison_timeout_exceeds_reviewed_budget",
        )
        return decide_comparison(plan, facts, review), facts, review

    def audit(self, plan):
        return self._load(plan)[0]

    def _payload(self, plan, facts):
        result = {ref: facts.target_files[ref] for ref in facts.target.package_refs}
        require(
            CONTRACT_REF not in result and TEST_REF not in result, "comparison_control_collision"
        )
        result[CONTRACT_REF] = facts.source_contract
        result[TEST_REF] = render_comparison_test(facts, plan.lane)
        return result

    def _request(self, plan, runtime, facts):
        entry = facts.target.entry
        pin = next(p for p in facts.target.manifest.files if p.path == entry.source_ref)
        return PytestRunRequest(
            role=RunRole.REPLAY,
            contract_id=facts.binding.contract.contract_id,
            contract_digest=facts.binding.contract_digest,
            target=TargetRef(
                module=entry.target_module, symbol=entry.target_symbol, source_ref=entry.source_ref
            ),
            target_digest=pin.content_digest,
            test_path=runtime / TEST_REF,
            contract_path=runtime / CONTRACT_REF,
            known_case_ids=tuple(runtime_case_id(c.case_id) for c in facts.cases),
            cwd=runtime,
            artifact_root=runtime / "r",
            timeout_seconds=plan.timeout_seconds,
            run_id="run_comparison",
        )

    def _authorize(self, plan, request, loaded):
        admission, facts, review = loaded
        require(admission.decision == "applicable", "comparison_execution_not_applicable")
        require(request == self._request(plan, request.cwd, facts), "comparison_request_changed")
        runtime = request.cwd.resolve()
        reject_links(runtime)
        require(
            runtime.is_relative_to(self.source.workspace)
            and runtime != self.source.workspace
            and not runtime.is_relative_to(self.source.repo)
            and not runtime.is_relative_to(self.target_repo),
            "comparison_runtime_path_forbidden",
        )
        payload = self._payload(plan, facts)
        pins = []
        tree = {p.path: p for p in facts.target.manifest.files}
        source_pin = next(
            p for p in facts.binding.trees["head"].files if p.path == facts.binding.contract_ref
        )
        for ref, data in sorted(payload.items()):
            path = runtime / ref
            reject_links(path)
            require(
                path.is_file()
                and path.stat().st_nlink == 1
                and path.stat().st_size == len(data)
                and path.read_bytes() == data,
                "comparison_runtime_input_changed",
            )
            if ref != TEST_REF:
                pin = source_pin if ref == CONTRACT_REF else tree[ref]
                pins.append(
                    ExecutionInputPin(
                        path=ref, object_id=pin.object_id, content_digest=digest_bytes(data)
                    )
                )
        return seal(
            SnapshotComparisonAuthorization(
                source_head=facts.binding.head_commit,
                target_revision=facts.target.manifest.commit,
                source_review_digest=self.source.trusted_digest,
                comparison_review_digest=self.review_anchor,
                source_binding_digest=facts.binding.artifact_digest,
                source_guard_digest=facts.guard.artifact_digest,
                target_digest=facts.target.artifact_digest,
                target_manifest_digest=facts.target.manifest.artifact_digest,
                map_digest=facts.mapping.artifact_digest,
                witness_digest=facts.witness.artifact_digest if facts.witness else None,
                plan_digest=plan.artifact_digest,
                admission_digest=admission.artifact_digest,
                image_digest=review.runner.image_digest,
                policy_digest=review.policy_digest,
                implementation_digests=inspection_implementation_digests(),
                request_digest=_request_digest(request),
                input_pins=tuple(pins),
                import_root=facts.target.entry.import_root,
                test_ref=TEST_REF,
                test_digest=digest_bytes(payload[TEST_REF]),
                artifact_digest=ZERO,
            )
        )

    def _preflight_paths(self, directory, plan, facts):
        require_publication(directory / "plan.json")
        require_publication(directory / "replay.json")
        require_publication(directory / "authorization.json")
        runtime = directory / "runtime"
        run_dir = runtime / "r/runs/run_comparison"
        require_run_directory(run_dir)
        for ref in self._payload(plan, facts):
            require_publication(runtime / ref)
            require_paths(run_dir / "sandbox-input" / ref)

    def _output(self, output):
        path = Path(output)
        path = path if path.is_absolute() else self.source.workspace / path
        reject_links(path)
        require(
            not path.resolve().is_relative_to(self.target_repo), "comparison_output_inside_target"
        )
        return self.source._output(path)

    def _result(self, plan, directory, admission, *, run=None, stale=False):
        executed = run is not None
        outcome = (
            "integrity_error"
            if stale
            else _outcome(run)
            if executed
            else "skipped_" + admission.decision
        )
        return seal(
            SnapshotComparisonReplay(
                created_at=datetime.now(UTC),
                plan_ref=self.source._ref(directory / "plan.json"),
                plan_digest=plan.artifact_digest,
                source_review_digest=self.source.trusted_digest,
                comparison_review_digest=self.review_anchor,
                admission=admission,
                integrity="stale" if stale else "current",
                outcome=outcome,
                reason_code="comparison_changed_after_execution"
                if stale
                else admission.reason_code,
                workspace_ref=self.source._ref(directory / "runtime") if executed else None,
                authorization_ref=self.source._ref(directory / "authorization.json")
                if executed
                else None,
                record_ref=self.source._ref(directory / "runtime/r/record.json")
                if executed
                else None,
                run=run,
                artifact_digest=ZERO,
            )
        )

    def run(self, plan, *, output):
        plan = self._checked_plan(plan)
        loaded = self._load(plan)
        admission, facts, _ = loaded
        # Preflight paths before creating output or discovering Docker.
        candidate = Path(output) if Path(output).is_absolute() else self.source.workspace / output
        if admission.decision == "applicable":
            self._preflight_paths(candidate, plan, facts)
        else:
            require_publication(candidate / "plan.json")
            require_publication(candidate / "replay.json")
        directory = self._output(output)
        write_immutable(directory / "plan.json", canonical_json_bytes(plan))
        if admission.decision != "applicable":
            result = self._result(plan, directory, admission)
        else:
            runtime = directory / "runtime"
            for ref, body in self._payload(plan, facts).items():
                write_immutable(runtime / ref, body)
            request = self._request(plan, runtime, facts)
            auth = self._authorize(plan, request, loaded)
            write_immutable(directory / "authorization.json", canonical_json_bytes(auth))
            try:
                run = _ComparisonDockerExecutor(self, plan, auth).execute(request)
            except GuardReplayIntegrityError as error:
                result = self._result(plan, directory, admission, run=error.run, stale=True)
            else:
                result = self._result(plan, directory, admission, run=run)
        write_immutable(directory / "replay.json", canonical_json_bytes(result))
        return result

    def _verify_run(self, run, request, review, facts):
        require(
            run.run_id == request.run_id
            and run.role is RunRole.REPLAY
            and run.target == request.target
            and run.target_digest == request.target_digest
            and run.contract_id == request.contract_id
            and run.contract_digest == request.contract_digest
            and run.timeout_seconds == request.timeout_seconds
            and run.cwd == ".",
            "comparison_run_identity_mismatch",
        )
        _verify_run_envelope(run, request, review, import_root=facts.target.entry.import_root)
        for ref, limit in (
            (run.stdout_ref, 1048576),
            (run.stderr_ref, 1048576),
            (run.junit_ref, 4194304),
        ):
            path = request.cwd / ref
            reject_links(path)
            require(
                path.is_file() and path.stat().st_nlink == 1 and path.stat().st_size <= limit,
                "comparison_log_budget_or_link",
            )
        verify_run_record(run, cwd=request.cwd, known_case_ids=request.known_case_ids)

    def verify(self, path):
        path = Path(path)
        path = path if path.is_absolute() else self.source.workspace / path
        value = read_value(path, SnapshotComparisonReplay)
        directory = path.resolve().parent
        require(
            value.plan_ref == self.source._ref(directory / "plan.json")
            and value.source_review_digest == self.source.trusted_digest
            and value.comparison_review_digest == self.review_anchor,
            "comparison_result_layout_or_anchor_changed",
        )
        plan = read_value(directory / "plan.json", SnapshotComparisonPlan)
        admission, facts, review = self._load(plan)
        require(
            value.plan_digest == plan.artifact_digest
            and value.admission == admission
            and value.integrity == "current",
            "comparison_result_claims_or_integrity_mismatch",
        )
        if admission.decision != "applicable":
            require(
                value.outcome == "skipped_" + admission.decision
                and value.run is None
                and value.workspace_ref is None
                and value.authorization_ref is None
                and value.record_ref is None,
                "comparison_skipped_result_contains_execution",
            )
        else:
            require(
                value.run is not None
                and value.workspace_ref == self.source._ref(directory / "runtime")
                and value.authorization_ref == self.source._ref(directory / "authorization.json")
                and value.record_ref == self.source._ref(directory / "runtime/r/record.json"),
                "comparison_execution_layout_mismatch",
            )
            request = self._request(plan, directory / "runtime", facts)
            authorization = read_value(
                directory / "authorization.json", SnapshotComparisonAuthorization
            )
            require(
                authorization == self._authorize(plan, request, (admission, facts, review)),
                "comparison_authorization_not_reconstructable",
            )
            record = directory / "runtime/r/record.json"
            reject_links(record)
            require(
                record.is_file()
                and record.stat().st_nlink == 1
                and record.stat().st_size <= JSON_LIMIT,
                "comparison_record_budget_or_link",
            )
            raw = record.read_bytes()
            strict_json(raw, limit=JSON_LIMIT)
            require(
                RunRecord.model_validate_json(raw) == value.run
                and value.outcome == _outcome(value.run),
                "comparison_record_or_outcome_changed",
            )
            self._verify_run(value.run, request, review, facts)
        require(value.reason_code == admission.reason_code, "comparison_result_reason_changed")
        return value


@dataclass(frozen=True)
class _ComparisonDockerExecutor:
    session: SnapshotComparisonSession
    plan: SnapshotComparisonPlan
    authorization: SnapshotComparisonAuthorization
    policy: DockerPolicyV1 = DockerPolicyV1()

    def execute(self, request):
        require(self.policy == DockerPolicyV1(), "comparison_executor_policy_changed")
        loaded = self.session._load(self.plan)
        require(
            self.authorization == self.session._authorize(self.plan, request, loaded),
            "comparison_authorization_changed_before_execution",
        )
        executable = _docker_executable()
        _require_image_identity(executable, self.authorization.image_digest, self.policy)
        run = _execute_with_adapter(request, _AdmittedDockerProcess(self, executable))
        write_immutable(request.artifact_root / "record.json", canonical_json_bytes(run))
        try:
            loaded = self.session._load(self.plan)
            require(
                self.authorization == self.session._authorize(self.plan, request, loaded),
                "comparison_authorization_changed_after_execution",
            )
            self.session._verify_run(run, request, loaded[2], loaded[1])
        except (ArtifactIntegrityError, OSError, ValueError, RepositoryProblem) as error:
            raise GuardReplayIntegrityError("comparison_changed_after_execution", run) from error
        return run
