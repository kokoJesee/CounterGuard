"""Fixture-only reviewed Docker capture, minimal Guard checks, and exact-snapshot replay.

No Registry, learner, production Scope, external purpose, or local executor route.
An anchor supplied by the trusted operator is required each time a session opens.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError, GuardReplayIntegrityError
from counterguard.execution import PytestRunRequest, _execute_with_adapter, verify_run_record
from counterguard.models import CaseOutcome, Digest, RunOutcome, RunRecord, RunRole, TargetRef
from counterguard.project_config import reject_links, repository_path
from counterguard.repository import RepositoryProblem
from counterguard.runners.docker import (
    DockerPolicyV1,
    ExecutionInputPin,
    _AdmittedDockerProcess,
    _docker_executable,
    _require_image_identity,
)
from counterguard.snapshot_admission import (
    JSON_LIMIT,
    read_value,
    require,
    seal,
    verify_snapshot_review,
)
from counterguard.snapshot_models import (
    ZERO,
    SnapshotAuthorization,
    SnapshotEvidence,
    SnapshotExecution,
    SnapshotGuard,
    SnapshotReplay,
)
from counterguard.snapshot_repository import read_snapshot
from counterguard.standalone_capture import _request_digest, _verify_run_envelope
from counterguard.standalone_contracts import strict_json
from counterguard.standalone_models import EvidenceId, GuardId
from counterguard.standalone_test import (
    CONTRACT_REF,
    TEST_REF,
    _render_literal_test,
    runtime_case_id,
)


def render_snapshot_test(contract, case_ids=None):
    cases = contract.cases
    if case_ids is not None:
        require(case_ids and len(set(case_ids)) == len(case_ids), "snapshot_guard_cases_required")
        selected = tuple(case for case in cases if case.case_id in case_ids)
        require(
            tuple(case.case_id for case in selected) == tuple(case_ids),
            "snapshot_guard_case_order_mismatch",
        )
        contract = contract.model_copy(update={"cases": selected})
    return _render_literal_test(contract, message_cases=True, generator="research-snapshot-test.v1")


def _reproduction(buggy, fixed, contract):
    """RunRecord sorts transport IDs; contracts preserve original assertion/row order."""
    expected = tuple(sorted(runtime_case_id(c.case_id) for c in contract.cases))
    reasons = []
    if buggy.outcome is not RunOutcome.TEST_FAILED or buggy.pytest_exit_code != 1:
        reasons.append("buggy_did_not_produce_real_test_failure")
    if fixed.outcome is not RunOutcome.PASSED or fixed.pytest_exit_code != 0:
        reasons.append("fixed_did_not_pass")
    for role, run in (("buggy", buggy), ("fixed", fixed)):
        if tuple(c.case_id for c in run.case_results) != expected:
            reasons.append(role + "_case_set_mismatch")
    observed = {c.case_id for c in buggy.case_results if c.outcome is CaseOutcome.FAILED}
    failed = tuple(c.case_id for c in contract.cases if runtime_case_id(c.case_id) in observed)
    if not failed:
        reasons.append("no_failed_cases")
    return failed, tuple(reasons)


@dataclass(frozen=True)
class SnapshotSession:
    repo: Path
    workspace: Path
    binding_path: Path
    review_path: Path
    trusted_digest: str

    # Closed concrete session classes select their own artifact namespace. No
    # artifact, CLI flag or constructor parameter can change these authorities.
    _AUTHORIZATION = SnapshotAuthorization
    _EVIDENCE = SnapshotEvidence
    _GUARD = SnapshotGuard
    _REPLAY_RESULT = SnapshotReplay
    _CAPTURE = "fixture_capture"
    _GUARD_CHECK = "fixture_guard_check"
    _REPLAY = "fixture_replay"
    _PURPOSES = frozenset({_CAPTURE, _GUARD_CHECK, _REPLAY})
    _FAILURE_SCHEMA = "research-snapshot-failure.v1"

    def __post_init__(self):
        for path in (self.repo, self.workspace, self.binding_path, self.review_path):
            reject_links(path)
            require(
                path.is_absolute() and path == path.resolve(),
                "snapshot_session_requires_canonical_paths",
            )
        TypeAdapter(Digest).validate_python(self.trusted_digest)

    def context(self):
        return verify_snapshot_review(
            self.repo, self.binding_path, self.review_path, trusted_digest=self.trusted_digest
        )

    def _output(self, output):
        path = Path(output)
        path = path if path.is_absolute() else self.workspace / path
        reject_links(path)
        path = path.resolve()
        require(
            path.is_relative_to(self.workspace)
            and path != self.workspace
            and not path.is_relative_to(self.repo.resolve())
            and not path.exists(),
            "snapshot_output_must_be_new_child_outside_repository",
        )
        repository_path(path.relative_to(self.workspace).as_posix())
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _ref(self, path):
        path = path.resolve()
        require(path.is_relative_to(self.workspace), "snapshot_reference_outside_workspace")
        return repository_path(path.relative_to(self.workspace).as_posix())

    def _source(self, binding, role):
        manifest, files = read_snapshot(
            self.repo, binding.trees[role].commit, budget=binding.budget
        )
        require(manifest == binding.trees[role], "snapshot_tree_changed")
        return files

    def _payload(self, binding, role, case_ids):
        files = self._source(binding, role)
        _, head = read_snapshot(self.repo, binding.head_commit, budget=binding.budget)
        require(
            digest_bytes(head[binding.contract_ref]) == binding.contract_digest,
            "snapshot_head_contract_changed",
        )
        payload = {ref: files[ref] for ref in binding.package_refs[role]}
        payload[CONTRACT_REF] = head[binding.contract_ref]
        payload[TEST_REF] = render_snapshot_test(binding.contract, case_ids)
        return payload

    def _request(self, runtime, binding, review, role, case_ids, *, run_id, purpose):
        contract = binding.contract
        source = next(p for p in binding.trees[role].files if p.path == contract.source_ref)
        return PytestRunRequest(
            role=(
                RunRole.REPLAY
                if purpose == self._REPLAY
                else {"buggy": RunRole.BUGGY, "fixed": RunRole.FIXED}[role]
            ),
            contract_id=contract.contract_id,
            contract_digest=binding.contract_digest,
            target=TargetRef(
                module=contract.target_module,
                symbol=contract.target_symbol,
                source_ref=contract.source_ref,
            ),
            target_digest=source.content_digest,
            test_path=runtime / TEST_REF,
            contract_path=runtime / CONTRACT_REF,
            known_case_ids=tuple(runtime_case_id(c) for c in case_ids),
            cwd=runtime,
            artifact_root=runtime / "r",
            timeout_seconds=review.timeout_seconds,
            run_id=run_id,
        )

    def _authorize(self, request, binding, review, role, case_ids, purpose):
        require(
            purpose in self._PURPOSES,
            "snapshot_purpose_forbidden",
        )
        payload = self._payload(binding, role, case_ids)
        expected = self._request(
            request.cwd, binding, review, role, case_ids, run_id=request.run_id, purpose=purpose
        )
        require(request == expected, "snapshot_request_mismatch")
        require(
            request.cwd.resolve().is_relative_to(self.workspace)
            and not request.cwd.resolve().is_relative_to(self.repo.resolve()),
            "snapshot_runtime_path_forbidden",
        )
        reject_links(request.cwd)
        pins = []
        for ref, data in sorted(payload.items()):
            path = request.cwd / ref
            reject_links(path)
            require(
                path.is_file()
                and path.stat().st_nlink == 1
                and path.stat().st_size == len(data)
                and digest_bytes(path.read_bytes()) == digest_bytes(data),
                "snapshot_runtime_input_changed",
            )
            # Generated controls are explicit tool inputs; package bytes retain Git object identity.
            if ref == TEST_REF:
                continue  # Canonical generated test has its own explicit digest, not a fake Git ID.
            source = next(
                p
                for p in binding.trees["head" if ref == CONTRACT_REF else role].files
                if p.path == (binding.contract_ref if ref == CONTRACT_REF else ref)
            )
            pins.append(
                ExecutionInputPin(
                    path=ref,
                    object_id=source.object_id,
                    content_digest=digest_bytes(data),
                )
            )
        return seal(
            self._AUTHORIZATION(
                purpose=purpose,
                review_digest=review.artifact_digest,
                binding_digest=binding.artifact_digest,
                target_manifest_digest=binding.trees[role].artifact_digest,
                implementation_digests=inspection_implementation_digests(),
                image_digest=review.runner.image_digest,
                policy_digest=review.policy_digest,
                request_digest=_request_digest(request),
                input_pins=tuple(pins),
                import_root=binding.contract.import_root,
                test_ref=TEST_REF,
                test_digest=digest_bytes(payload[TEST_REF]),
                artifact_digest=ZERO,
            )
        )

    def _execute(self, directory, *, role, case_ids, purpose):
        binding, review = self.context()
        directory.mkdir(parents=True, exist_ok=False)
        for ref, data in self._payload(binding, role, case_ids).items():
            write_immutable(directory / ref, data)
        request = self._request(
            directory, binding, review, role, case_ids, run_id="run_snapshot", purpose=purpose
        )
        authorization = self._authorize(request, binding, review, role, case_ids, purpose)
        write_immutable(directory / "authorization.json", canonical_json_bytes(authorization))
        executor = _SnapshotExecutor(self, authorization, role, tuple(case_ids), purpose)
        run = executor.execute(request)
        item = SnapshotExecution(
            workspace_ref=self._ref(directory),
            authorization_ref=self._ref(directory / "authorization.json"),
            record_ref=self._ref(directory / "r/record.json"),
            run=run,
        )
        self._verify_execution(item, binding, review, role, tuple(case_ids), purpose)
        return item

    def _verify_execution(self, item, binding, review, role, case_ids, purpose):
        runtime = self.workspace / item.workspace_ref
        require(
            item.authorization_ref == item.workspace_ref + "/authorization.json"
            and item.record_ref == item.workspace_ref + "/r/record.json",
            "snapshot_execution_layout_mismatch",
        )
        request = self._request(
            runtime, binding, review, role, case_ids, run_id="run_snapshot", purpose=purpose
        )
        authorization = read_value(self.workspace / item.authorization_ref, self._AUTHORIZATION)
        require(
            authorization == self._authorize(request, binding, review, role, case_ids, purpose),
            "snapshot_run_authorization_mismatch",
        )
        record_path = self.workspace / item.record_ref
        reject_links(record_path)
        require(
            record_path.is_file()
            and record_path.stat().st_nlink == 1
            and record_path.stat().st_size <= JSON_LIMIT,
            "snapshot_record_budget_or_link",
        )
        raw = record_path.read_bytes()
        strict_json(raw, limit=JSON_LIMIT)
        stored = RunRecord.model_validate_json(raw)
        require(
            stored == item.run
            and stored.run_id == request.run_id
            and stored.role == request.role
            and stored.target == request.target
            and stored.target_digest == request.target_digest
            and stored.contract_id == request.contract_id
            and stored.contract_digest == request.contract_digest
            and stored.timeout_seconds == request.timeout_seconds
            and stored.cwd == ".",
            "snapshot_record_identity_mismatch",
        )
        _verify_run_envelope(stored, request, review, import_root=binding.contract.import_root)
        for ref in (stored.stdout_ref, stored.stderr_ref, stored.junit_ref):
            reject_links(runtime / ref)
            stat = (runtime / ref).stat()
            require(
                stat.st_nlink == 1
                and stat.st_size
                <= (
                    DockerPolicyV1().junit_limit_bytes
                    if ref == stored.junit_ref
                    else DockerPolicyV1().stdout_limit_bytes
                ),
                "snapshot_log_budget_or_link",
            )
        verify_run_record(stored, cwd=runtime, known_case_ids=request.known_case_ids)

    def capture(self, *, evidence_id, output):
        TypeAdapter(EvidenceId).validate_python(evidence_id)
        binding, review = self.context()
        directory = self._output(output)
        ids = tuple(c.case_id for c in binding.contract.cases)
        try:
            buggy = self._execute(
                directory / "b", role="buggy", case_ids=ids, purpose=self._CAPTURE
            )
            fixed = self._execute(
                directory / "f", role="fixed", case_ids=ids, purpose=self._CAPTURE
            )
            failed, reasons = _reproduction(buggy.run, fixed.run, binding.contract)
            value = seal(
                self._EVIDENCE(
                    evidence_id=evidence_id,
                    created_at=datetime.now(UTC),
                    binding_digest=binding.artifact_digest,
                    review_digest=review.artifact_digest,
                    contract_digest=binding.contract_digest,
                    buggy=buggy,
                    fixed=fixed,
                    failing_case_ids=failed,
                    reproduced=not reasons,
                    rejection_reasons=reasons,
                    artifact_digest=ZERO,
                )
            )
            write_immutable(directory / "evidence.json", canonical_json_bytes(value))
            return self.verify_evidence(directory / "evidence.json")
        except (ArtifactIntegrityError, OSError, ValueError, RepositoryProblem) as error:
            self._failure(directory, "capture", error)
            raise

    def _failure(self, directory, operation, error):
        # Preserve every completed raw run. Do not re-sign it as a successful result.
        value = {
            "schema_version": self._FAILURE_SCHEMA,
            "operation": operation,
            "execution_status": "incomplete_or_rejected",
            "error_type": type(error).__name__,
            "completed_record_refs": sorted(self._ref(p) for p in directory.rglob("record.json")),
            "implementation_digests": inspection_implementation_digests(),
        }
        value["artifact_digest"] = digest_json_artifact(value)
        write_immutable(directory / "failure.json", canonical_json_bytes(value))

    def verify_evidence(self, path):
        binding, review = self.context()
        value = read_value(path, self._EVIDENCE)
        require(
            value.binding_digest == binding.artifact_digest
            and value.review_digest == review.artifact_digest
            and value.contract_digest == binding.contract_digest,
            "snapshot_evidence_source_mismatch",
        )
        directory = self._ref(Path(path).resolve().parent)
        ids = tuple(c.case_id for c in binding.contract.cases)
        for role, item in (("buggy", value.buggy), ("fixed", value.fixed)):
            require(
                item.workspace_ref == directory + ("/b" if role == "buggy" else "/f"),
                "snapshot_evidence_run_layout",
            )
            self._verify_execution(item, binding, review, role, ids, self._CAPTURE)
        failed, reasons = _reproduction(value.buggy.run, value.fixed.run, binding.contract)
        require(
            (value.failing_case_ids, value.rejection_reasons, value.reproduced)
            == (failed, reasons, not reasons),
            "snapshot_evidence_claims_mismatch",
        )
        return value

    def compile(self, evidence_path, *, guard_id, output):
        TypeAdapter(GuardId).validate_python(guard_id)
        evidence = self.verify_evidence(evidence_path)
        require(evidence.reproduced, "snapshot_evidence_not_reproduced")
        directory = self._output(output)
        try:
            binding, review = self.context()
            ids = evidence.failing_case_ids
            buggy = self._execute(
                directory / "b", role="buggy", case_ids=ids, purpose=self._GUARD_CHECK
            )
            fixed = self._execute(
                directory / "f", role="fixed", case_ids=ids, purpose=self._GUARD_CHECK
            )
            selected = binding.contract.model_copy(
                update={"cases": tuple(c for c in binding.contract.cases if c.case_id in ids)}
            )
            failed, reasons = _reproduction(buggy.run, fixed.run, selected)
            require(not reasons and failed == ids, "snapshot_minimal_guard_self_check_failed")
            guard = seal(
                self._GUARD(
                    guard_id=guard_id,
                    created_at=datetime.now(UTC),
                    evidence_digest=evidence.artifact_digest,
                    binding_digest=binding.artifact_digest,
                    review_digest=review.artifact_digest,
                    case_ids=ids,
                    test_digest=digest_bytes(render_snapshot_test(binding.contract, ids)),
                    buggy_check=buggy,
                    fixed_check=fixed,
                    artifact_digest=ZERO,
                )
            )
            write_immutable(directory / "guard.json", canonical_json_bytes(guard))
            return self.verify_guard(directory / "guard.json", evidence_path=evidence_path)
        except (ArtifactIntegrityError, OSError, ValueError, RepositoryProblem) as error:
            self._failure(directory, "compile", error)
            raise

    def verify_guard(self, path, *, evidence_path):
        evidence = self.verify_evidence(evidence_path)
        binding, review = self.context()
        guard = read_value(path, self._GUARD)
        require(
            evidence.reproduced
            and guard.evidence_digest == evidence.artifact_digest
            and guard.binding_digest == binding.artifact_digest
            and guard.review_digest == review.artifact_digest
            and guard.case_ids == evidence.failing_case_ids
            and guard.test_digest
            == digest_bytes(render_snapshot_test(binding.contract, guard.case_ids)),
            "snapshot_guard_provenance_or_minimality_mismatch",
        )
        directory = self._ref(Path(path).resolve().parent)
        for role, item in (("buggy", guard.buggy_check), ("fixed", guard.fixed_check)):
            require(
                item.workspace_ref == directory + ("/b" if role == "buggy" else "/f"),
                "snapshot_guard_run_layout",
            )
            self._verify_execution(item, binding, review, role, guard.case_ids, self._GUARD_CHECK)
        selected = binding.contract.model_copy(
            update={
                "cases": tuple(c for c in binding.contract.cases if c.case_id in guard.case_ids)
            }
        )
        failed, reasons = _reproduction(guard.buggy_check.run, guard.fixed_check.run, selected)
        require(
            not reasons and failed == guard.case_ids, "snapshot_guard_self_check_claims_mismatch"
        )
        return guard

    def replay(self, guard_path, *, evidence_path, role, output):
        guard = self.verify_guard(guard_path, evidence_path=evidence_path)
        require(role in {"buggy", "fixed"}, "snapshot_only_exact_reviewed_source_replay")
        directory = self._output(output)
        try:
            binding, review = self.context()
            item = self._execute(
                directory / "run", role=role, case_ids=guard.case_ids, purpose=self._REPLAY
            )
            value = seal(
                self._REPLAY_RESULT(
                    guard_digest=guard.artifact_digest,
                    evidence_digest=guard.evidence_digest,
                    review_digest=review.artifact_digest,
                    binding_digest=binding.artifact_digest,
                    source_role=role,
                    target_manifest_digest=binding.trees[role].artifact_digest,
                    execution=item,
                    artifact_digest=ZERO,
                )
            )
            write_immutable(directory / "replay.json", canonical_json_bytes(value))
            return self.verify_replay(
                directory / "replay.json", guard_path=guard_path, evidence_path=evidence_path
            )
        except (ArtifactIntegrityError, OSError, ValueError, RepositoryProblem) as error:
            self._failure(directory, "replay", error)
            raise

    def verify_replay(self, path, *, guard_path, evidence_path):
        guard = self.verify_guard(guard_path, evidence_path=evidence_path)
        binding, review = self.context()
        value = read_value(path, self._REPLAY_RESULT)
        require(
            value.guard_digest == guard.artifact_digest
            and value.evidence_digest == guard.evidence_digest
            and value.review_digest == review.artifact_digest
            and value.binding_digest == binding.artifact_digest
            and value.target_manifest_digest == binding.trees[value.source_role].artifact_digest
            and value.execution.workspace_ref == self._ref(Path(path).resolve().parent) + "/run",
            "snapshot_replay_source_or_layout_mismatch",
        )
        self._verify_execution(
            value.execution, binding, review, value.source_role, guard.case_ids, self._REPLAY
        )
        return value


@dataclass(frozen=True)
class _SnapshotExecutor:
    session: SnapshotSession
    authorization: SnapshotAuthorization
    role: str
    case_ids: tuple[str, ...]
    purpose: str
    policy: DockerPolicyV1 = DockerPolicyV1()

    def verify(self, request):
        binding, review = self.session.context()
        require(
            self.policy == DockerPolicyV1()
            and self.authorization
            == self.session._authorize(
                request, binding, review, self.role, self.case_ids, self.purpose
            ),
            "snapshot_executor_authorization_stale",
        )

    def execute(self, request):
        self.verify(request)
        executable = _docker_executable()
        _require_image_identity(executable, self.authorization.image_digest, self.policy)
        record = _execute_with_adapter(request, _AdmittedDockerProcess(self, executable))
        write_immutable(request.artifact_root / "record.json", canonical_json_bytes(record))
        try:
            self.verify(request)
        except (ArtifactIntegrityError, OSError, ValueError, RepositoryProblem) as error:
            raise GuardReplayIntegrityError(
                "snapshot_inputs_changed_after_execution", record
            ) from error
        return record
