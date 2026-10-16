"""Scope-aware replay with explicit skipped, unknown, integrity, and execution states."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from counterguard.artifacts import write_immutable
from counterguard.baselines import ClauseTrace, ScopeDecision, ScopePredicate, decide_scope
from counterguard.compiler import run_guard, verify_guard
from counterguard.digests import (
    canonical_json_bytes,
    digest_file,
    digest_json_artifact,
)
from counterguard.errors import (
    ArtifactIntegrityError,
    FeatureExtractionError,
    GuardReplayIntegrityError,
)
from counterguard.evidence import parse_target_ref, verify_evidence
from counterguard.execution import verify_run_record
from counterguard.features import FeatureContext, FeatureRecord, extract_feature_record
from counterguard.models import (
    ArtifactRef,
    CaseOutcome,
    Digest,
    FrozenModel,
    NonEmptyText,
    RunOutcome,
    RunRecord,
    RunRole,
    TargetRef,
    UtcDateTime,
)
from counterguard.module_context import SCOPE_V1_CONTEXT_DIGEST, load_module_context
from counterguard.path_limits import require_replay_directory
from counterguard.predicates import VOCABULARY_DIGEST, FeatureVector
from counterguard.protocol import _load_model, _path, _read_samples, verify_protocol
from counterguard.scope import (
    SCOPE_V1_PROTOCOL_DIGEST,
    FitManifest,
    ScopeLearningResult,
    TrainingExample,
    learn_scope,
)


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    guard_path: Path
    scope_path: Path
    target: str
    contract_path: Path | None
    cwd: Path
    artifact_root: Path = Path("artifacts")
    protocol_path: Path = Path("experiments/scope_v1.json")
    module_context_path: Path = Path("benchmarks/context/scope_v1.json")
    fit_manifest_path: Path | None = None
    timeout_seconds: float = 30.0


class ReplayResult(FrozenModel):
    schema_version: Literal["replay-result.v1"] = "replay-result.v1"
    replay_id: NonEmptyText
    created_at: UtcDateTime
    guard_id: NonEmptyText
    guard_digest: Digest
    guard_ref: ArtifactRef
    scope_id: NonEmptyText
    scope_digest: Digest
    scope_ref: ArtifactRef
    protocol_digest: Digest
    protocol_ref: ArtifactRef
    module_context_ref: ArtifactRef
    fit_manifest_ref: ArtifactRef | None
    fit_manifest_digest: Digest | None
    target: TargetRef
    target_digest: Digest
    declared_contract_ref: ArtifactRef | None
    feature_ref: ArtifactRef | None
    feature_digest: Digest | None
    feature_vector: FeatureVector | None
    scope_decision: Literal["applicable", "inapplicable", "unknown"]
    decision_trace: tuple[ClauseTrace, ...]
    verdict: Literal[
        "pass",
        "violation",
        "skipped_inapplicable",
        "skipped_unknown",
        "collection_error",
        "execution_error",
        "timeout",
        "stale",
    ]
    violated_case_ids: tuple[str, ...]
    run: RunRecord | None
    error_detail: str | None
    artifact_digest: Digest

    @model_validator(mode="after")
    def state_invariants(self) -> Self:
        if not self.replay_id.startswith("rpl_"):
            raise ValueError("Replay identity requires rpl_ prefix")
        if self.scope_decision != "applicable":
            expected = (
                "skipped_unknown" if self.scope_decision == "unknown" else "skipped_inapplicable"
            )
            if self.verdict != expected or self.run is not None or self.violated_case_ids:
                raise ValueError("Skipped decisions must retain their own verdict and run=null")
        elif self.verdict.startswith("skipped_") or (self.run is None and self.verdict != "stale"):
            raise ValueError("Applicable execution requires a run or explicit integrity failure")
        if self.scope_decision == "unknown" and not self.error_detail:
            raise ValueError("Unknown must explain missing or unsupported information")
        if self.scope_decision == "unknown" and self.feature_vector is not None:
            raise ValueError("A complete trusted FeatureVector cannot be disguised as unknown")
        if self.scope_decision != "unknown" and self.feature_vector is None:
            raise ValueError("Known scope decisions require complete automatic features")
        if (self.feature_ref is None) != (self.feature_digest is None):
            raise ValueError("Feature reference and digest must be provided together")
        if (self.fit_manifest_ref is None) != (self.fit_manifest_digest is None):
            raise ValueError("Fit reference and digest must be provided together")
        if self.run is not None:
            if self.run.role is not RunRole.REPLAY:
                raise ValueError("Replay execution must use the replay role")
            if self.run.target != self.target or self.run.target_digest != self.target_digest:
                raise ValueError("Replay and execution target identities disagree")
            outcome = self.run.outcome
            if self.verdict == "pass" and outcome is not RunOutcome.PASSED:
                raise ValueError("Only a passed execution may be reported as pass")
            if self.verdict == "violation" and outcome is not RunOutcome.TEST_FAILED:
                raise ValueError("Only a real assertion failure may be a violation")
            expected_verdict = _execution_verdict(self.run)
            if self.verdict != "stale" and self.verdict != expected_verdict:
                raise ValueError("Execution outcome and verdict disagree")
        failed = (
            tuple(
                sorted(
                    case.case_id
                    for case in self.run.case_results
                    if case.outcome is CaseOutcome.FAILED
                )
            )
            if self.run
            else ()
        )
        if self.verdict == "violation":
            if not failed or self.violated_case_ids != failed:
                raise ValueError("Violations must name exactly the failed regression cases")
        elif self.violated_case_ids:
            raise ValueError("Only confirmed violation may publish failed case IDs")
        return self


def verify_scope_binding(
    scope_path: Path,
    guard_path: Path,
    *,
    cwd: Path,
    protocol_path: Path,
    fit_manifest_path: Path | None = None,
) -> tuple[ScopePredicate, FitManifest | None]:
    """Audit the existing bundle; no hidden capture, refit, or pytest execution."""
    workspace = cwd.resolve(strict=True)
    guard = verify_guard(guard_path, cwd=workspace)
    scope_file = _path(scope_path, workspace)
    scope = _load_model(scope_file, ScopePredicate)
    protocol, split, guards = verify_protocol(protocol_path, cwd=workspace)
    if (
        protocol.artifact_digest != SCOPE_V1_PROTOCOL_DIGEST
        or scope.protocol_digest != protocol.artifact_digest
        or scope.guard_id != guard.guard_id
        or scope.guard_digest != guard.artifact_digest
        or guard.guard_id not in guards
    ):
        raise ArtifactIntegrityError("Guard/Scope/protocol binding is stale or mismatched")
    if scope.strategy != "learned_conjunction":
        expected = (
            ()
            if scope.strategy == "always"
            else (("interface_kind", "eq", guard.target_interface.interface_kind),)
        )
        if (
            tuple((clause.field, clause.op, clause.value) for clause in scope.clauses) != expected
            or scope.learner_version != "baseline.v1"
        ):
            raise ArtifactIntegrityError("Baseline scope differs from the frozen definition")
        return scope, None
    manifest_file = (
        _path(fit_manifest_path, workspace)
        if fit_manifest_path
        else scope_file.parent / "fit-manifest.json"
    )
    manifest = _load_model(manifest_file, FitManifest)
    if (
        manifest.protocol_digest != protocol.artifact_digest
        or manifest.split_digest != split.artifact_digest
        or manifest.module_context_digest != SCOPE_V1_CONTEXT_DIGEST
        or load_module_context(_path(Path(manifest.module_context_ref), workspace)).artifact_digest
        != manifest.module_context_digest
        or manifest.train_file_digests
        != {file.path: file.content_digest for file in split.files if file.split == "train"}
    ):
        raise ArtifactIntegrityError("Fit manifest dependencies are stale")
    try:
        audit = json.loads(_path(Path(manifest.feature_audit_ref), workspace).read_bytes())
    except (OSError, ValueError) as error:
        raise ArtifactIntegrityError("Missing or invalid fitted feature audit") from error
    expected_ids = set().union(
        *(
            set(part.initial + part.refinement_additions + part.holdout)
            for part in split.phases.values()
        )
    )
    if (
        digest_json_artifact(audit) != manifest.feature_audit_digest
        or audit.get("artifact_digest") != manifest.feature_audit_digest
        or audit.get("schema_version") != "feature-audit.v2"
        or audit.get("vocabulary_digest") != VOCABULARY_DIGEST
        or audit.get("module_context_digest") != SCOPE_V1_CONTEXT_DIGEST
        or audit.get("errors") != 0
        or audit.get("mismatched") != 0
        or audit.get("matched") != len(expected_ids)
        or audit.get("dataset_digests") != {file.path: file.content_digest for file in split.files}
        or {row.get("sample_id") for row in audit.get("entries", [])} != expected_ids
    ):
        raise ArtifactIntegrityError("Fit feature audit is incomplete or changed")
    rows = {row["sample_id"]: row for row in audit["entries"]}
    samples = {
        sample.sample_id: sample
        for item in split.files
        if item.split == "train"
        for sample in _read_samples(_path(Path(item.path), workspace))
    }
    for group in manifest.groups:
        if (
            group.guard_id not in guards
            or group.guard_digest != guards[group.guard_id].artifact_digest
        ):
            raise ArtifactIntegrityError("Fitted Guard provenance mismatch")
        phase = split.phases[group.guard_id]
        expected_members = (
            phase.initial
            if manifest.phase == "initial"
            else phase.initial + phase.refinement_additions
        )
        if group.training_sample_ids != tuple(sorted(expected_members)) or set(
            group.training_sample_ids
        ) & set(phase.holdout):
            raise ArtifactIntegrityError("Fit membership changed or leaked holdout")
        fitted_scope = _load_model(_path(Path(group.scope_ref), workspace), ScopePredicate)
        learning = _load_model(_path(Path(group.learning_ref), workspace), ScopeLearningResult)
        evidence = verify_evidence(guards[group.guard_id].source_evidence_ref, cwd=workspace)
        for sample_id, expected_target in (
            (group.source_bug_sample_id, evidence.buggy_target),
            (group.fixed_sample_id, evidence.fixed_target),
        ):
            selected_sample = samples[sample_id]
            if not selected_sample.labels.guard_applicable or (
                selected_sample.target.module,
                selected_sample.target.symbol,
            ) != (expected_target.module, expected_target.symbol):
                raise ArtifactIntegrityError("Fitted source-bug/fixed identity proof changed")
        if not any(
            not samples[sid].labels.guard_applicable and samples[sid].labels.contract_compliant
            for sid in group.training_sample_ids
        ):
            raise ArtifactIntegrityError("Fitted legal counterexample proof is missing")
        examples = []
        for sample_id in group.training_sample_ids:
            sample = samples[sample_id]
            row = rows[sample_id]
            record = _load_model(_path(Path(row["feature_ref"]), workspace), FeatureRecord)
            fresh = extract_feature_record(
                FeatureContext(
                    target=f"{sample.target.module}:{sample.target.symbol}",
                    contract_path=Path(sample.contract_ref),
                    cwd=workspace,
                    module_context_path=Path(manifest.module_context_ref),
                )
            )
            if record != fresh or record.artifact_digest != row["feature_digest"]:
                raise ArtifactIntegrityError("Training FeatureRecord is stale")
            examples.append(
                TrainingExample(
                    features=record.features, guard_applicable=sample.labels.guard_applicable
                )
            )
        recomputed = learn_scope(tuple(examples))
        count_matches = (
            learning.candidate_count == recomputed.combination_count
            if learning.schema_version == "scope-learning.v1"
            else (
                learning.predicate_count == recomputed.predicate_count
                and learning.combination_count == recomputed.combination_count
            )
        )
        if (
            learning.artifact_digest != group.learning_digest
            or not count_matches
            or learning.clauses != recomputed.clauses
            or learning.training_confusion != recomputed.training_confusion
            or learning.training_dataset_digest != recomputed.training_dataset_digest
            or group.training_dataset_digest != recomputed.training_dataset_digest
            or fitted_scope.artifact_digest != group.scope_digest
            or fitted_scope.guard_id != group.guard_id
            or fitted_scope.guard_digest != group.guard_digest
            or fitted_scope.protocol_digest != manifest.protocol_digest
            or fitted_scope.clauses != learning.clauses
            or fitted_scope.training_confusion != learning.training_confusion
            or fitted_scope.training_dataset_digest != group.training_dataset_digest
            or fitted_scope.training_sample_ids != group.training_sample_ids
            or fitted_scope.scope_id != f"scp_scope_v1_{manifest.phase}_{group.guard_id}"
            or fitted_scope.learner_version != learning.learner_version
        ):
            raise ArtifactIntegrityError("Fitted scope/rule/learning binding mismatch")
    group = next((group for group in manifest.groups if group.guard_id == guard.guard_id), None)
    if (
        group is None
        or _path(Path(group.scope_ref), workspace) != scope_file
        or group.scope_digest != scope.artifact_digest
    ):
        raise ArtifactIntegrityError("Requested scope does not belong to the fitted bundle")
    return scope, manifest


def replay_guard(request: ReplayRequest) -> ReplayResult:
    if (
        type(request.timeout_seconds) not in (float, int)
        or not math.isfinite(request.timeout_seconds)
        or request.timeout_seconds <= 0
    ):
        raise ValueError("Replay timeout must be positive and finite")
    workspace = request.cwd.resolve(strict=True)
    root = _path(request.artifact_root, workspace)
    scope, manifest = verify_scope_binding(
        request.scope_path,
        request.guard_path,
        cwd=workspace,
        protocol_path=request.protocol_path,
        fit_manifest_path=request.fit_manifest_path,
    )
    guard = verify_guard(request.guard_path, cwd=workspace)
    target, target_digest = parse_target_ref(request.target, cwd=workspace, validate_symbol=False)
    replay_id = "rpl_" + uuid.uuid4().hex
    directory = root / "replays" / replay_id
    require_replay_directory(directory)
    feature = None
    feature_ref = None
    error = None
    try:
        if request.contract_path is None:
            raise FeatureExtractionError("Target contract metadata was not provided")
        feature = extract_feature_record(
            FeatureContext(
                request.target, request.contract_path, workspace, request.module_context_path
            )
        )
        if feature.module_context_digest != (
            manifest.module_context_digest if manifest else SCOPE_V1_CONTEXT_DIGEST
        ):
            raise ArtifactIntegrityError(
                "Target context does not match the Scope's audited context"
            )
        if feature.target != target or feature.target_digest != target_digest:
            raise ArtifactIntegrityError("Replay target changed during feature extraction")
        feature_path = directory / "feature.json"
        write_immutable(feature_path, canonical_json_bytes(feature))
        feature_ref = feature_path.relative_to(workspace).as_posix()
        if feature.features.contract_family != guard.target_interface.contract_family:
            decision = ScopeDecision(
                decision="inapplicable",
                trace=(
                    ClauseTrace(
                        field="contract_family",
                        op="eq",
                        expected=guard.target_interface.contract_family,
                        actual=feature.features.contract_family,
                        matched=False,
                    ),
                ),
                reason="Trusted family prefilter excludes this Guard",
            )
        else:
            decision = decide_scope(scope, feature.features.model_dump(mode="json"))
    except FeatureExtractionError as failure:
        error = str(failure)
        decision = ScopeDecision(
            decision="unknown",
            reason=error,
            trace=tuple(
                ClauseTrace(
                    field=clause.field,
                    op=clause.op,
                    expected=clause.value,
                    actual=None,
                    matched=None,
                )
                for clause in scope.clauses
            ),
        )
    run = None
    if decision.decision == "applicable":
        # Recheck actual inputs immediately before crossing the execution boundary.
        verify_guard(request.guard_path, cwd=workspace)
        if digest_file(workspace / target.source_ref) != target_digest:
            raise ArtifactIntegrityError("Replay target changed before execution")
        try:
            run = run_guard(
                request.guard_path,
                request.target,
                cwd=workspace,
                artifact_root=directory,
                timeout_seconds=request.timeout_seconds,
            )
            verdict = _execution_verdict(run)
            after_scope, after_manifest = verify_scope_binding(
                request.scope_path,
                request.guard_path,
                cwd=workspace,
                protocol_path=request.protocol_path,
                fit_manifest_path=request.fit_manifest_path,
            )
            if after_scope != scope or after_manifest != manifest:
                raise ArtifactIntegrityError("Scope dependencies changed during execution")
            try:
                after_feature = extract_feature_record(
                    FeatureContext(
                        request.target,
                        request.contract_path,
                        workspace,
                        request.module_context_path,
                    )
                )
            except FeatureExtractionError as failure:
                raise ArtifactIntegrityError(
                    "Target feature dependencies changed during execution"
                ) from failure
            if after_feature != feature:
                raise ArtifactIntegrityError(
                    "Declared target contract/context changed during execution"
                )
        except GuardReplayIntegrityError as failure:
            run, verdict, error = failure.run, "stale", str(failure)
        except ArtifactIntegrityError as failure:
            verdict, error = "stale", str(failure)
        except (ValueError, OSError) as failure:
            verdict, error = "stale", f"Previously validated execution inputs changed: {failure}"
        if run and verdict not in {"pass", "violation"}:
            error = error or run.error_detail or f"Execution outcome: {run.outcome.value}"
        if run and (
            run.contract_id != guard.contract_id or run.contract_digest != guard.contract_digest
        ):
            raise ArtifactIntegrityError("Execution used a different Guard contract identity")
    else:
        verdict = "skipped_unknown" if decision.decision == "unknown" else "skipped_inapplicable"
        error = error or decision.reason
    violated = (
        tuple(
            sorted(case.case_id for case in run.case_results if case.outcome is CaseOutcome.FAILED)
        )
        if run and verdict == "violation"
        else ()
    )
    manifest_path = (
        _path(request.fit_manifest_path, workspace)
        if request.fit_manifest_path
        else _path(request.scope_path, workspace).parent / "fit-manifest.json"
    )
    draft = ReplayResult(
        replay_id=replay_id,
        created_at=datetime.now(UTC),
        guard_id=guard.guard_id,
        guard_digest=guard.artifact_digest,
        scope_id=scope.scope_id,
        scope_digest=scope.artifact_digest,
        guard_ref=_path(request.guard_path, workspace).relative_to(workspace).as_posix(),
        scope_ref=_path(request.scope_path, workspace).relative_to(workspace).as_posix(),
        protocol_ref=_path(request.protocol_path, workspace).relative_to(workspace).as_posix(),
        module_context_ref=_path(request.module_context_path, workspace)
        .relative_to(workspace)
        .as_posix(),
        protocol_digest=scope.protocol_digest,
        fit_manifest_ref=manifest_path.relative_to(workspace).as_posix() if manifest else None,
        fit_manifest_digest=manifest.artifact_digest if manifest else None,
        target=target,
        target_digest=target_digest,
        declared_contract_ref=_path(request.contract_path, workspace)
        .relative_to(workspace)
        .as_posix()
        if request.contract_path
        else None,
        feature_ref=feature_ref,
        feature_digest=feature.artifact_digest if feature else None,
        feature_vector=feature.features if feature else None,
        scope_decision=decision.decision,
        decision_trace=decision.trace,
        verdict=verdict,
        violated_case_ids=violated,
        run=run,
        error_detail=error,
        artifact_digest="sha256:" + "0" * 64,
    )
    result = ReplayResult.model_validate_json(
        canonical_json_bytes(
            {**draft.model_dump(mode="json"), "artifact_digest": digest_json_artifact(draft)}
        )
    )
    write_immutable(directory / "result.json", canonical_json_bytes(result))
    return result


def _execution_verdict(run: RunRecord) -> str:
    return {
        RunOutcome.PASSED: "pass",
        RunOutcome.TEST_FAILED: "violation",
        RunOutcome.NO_TESTS_COLLECTED: "collection_error",
        RunOutcome.TIMEOUT: "timeout",
    }.get(run.outcome, "execution_error")


def replay_exit_code(result: ReplayResult) -> int:
    return {
        "pass": 0,
        "skipped_inapplicable": 0,
        "violation": 1,
        "skipped_unknown": 4,
        "stale": 5,
    }.get(result.verdict, 3)


def verify_replay(path: str | Path, *, cwd: str | Path) -> ReplayResult:
    workspace = Path(cwd).resolve(strict=True)
    result_path = _path(Path(path), workspace)
    result = _load_model(result_path, ReplayResult)
    if result_path.name != "result.json" or result_path.parent.name != result.replay_id:
        raise ArtifactIntegrityError("Replay path and identity mismatch")
    scope, manifest = verify_scope_binding(
        Path(result.scope_ref),
        Path(result.guard_ref),
        cwd=workspace,
        protocol_path=Path(result.protocol_ref),
        fit_manifest_path=Path(result.fit_manifest_ref) if result.fit_manifest_ref else None,
    )
    guard = verify_guard(result.guard_ref, cwd=workspace)
    try:
        current_target, target_digest = parse_target_ref(
            f"{result.target.module}:{result.target.symbol}", cwd=workspace, validate_symbol=False
        )
    except (OSError, ValueError) as error:
        raise ArtifactIntegrityError("Replay target binding is unavailable") from error
    if (
        scope.artifact_digest != result.scope_digest
        or guard.artifact_digest != result.guard_digest
        or guard.guard_id != result.guard_id
        or scope.scope_id != result.scope_id
        or scope.protocol_digest != result.protocol_digest
        or (manifest.artifact_digest if manifest else None) != result.fit_manifest_digest
        or current_target != result.target
        or target_digest != result.target_digest
        or (
            result.run is not None
            and (
                result.run.contract_id != guard.contract_id
                or result.run.contract_digest != guard.contract_digest
            )
        )
    ):
        raise ArtifactIntegrityError("Replay input bindings are stale")
    load_module_context(_path(Path(result.module_context_ref), workspace))
    if result.feature_ref:
        feature = _load_model(_path(Path(result.feature_ref), workspace), FeatureRecord)
        fresh = extract_feature_record(
            FeatureContext(
                f"{result.target.module}:{result.target.symbol}",
                Path(feature.contract_ref),
                workspace,
                Path(result.module_context_ref),
            )
        )
        if (
            fresh != feature
            or feature.artifact_digest != result.feature_digest
            or feature.features != result.feature_vector
            or feature.target != result.target
            or feature.target_digest != result.target_digest
            or feature.contract_ref != result.declared_contract_ref
        ):
            raise ArtifactIntegrityError("Replay features changed")
        if result.scope_decision != "unknown":
            if feature.features.contract_family != guard.target_interface.contract_family:
                expected_decision = ScopeDecision(
                    decision="inapplicable",
                    trace=(
                        ClauseTrace(
                            field="contract_family",
                            op="eq",
                            expected=guard.target_interface.contract_family,
                            actual=feature.features.contract_family,
                            matched=False,
                        ),
                    ),
                )
            else:
                expected_decision = decide_scope(scope, feature.features.model_dump(mode="json"))
            if (expected_decision.decision, expected_decision.trace) != (
                result.scope_decision,
                result.decision_trace,
            ):
                raise ArtifactIntegrityError(
                    "Replay decision/trace does not follow its stored scope"
                )
    unknown_reason = "Target contract metadata was not provided"
    if result.scope_decision == "unknown" and result.declared_contract_ref:
        try:
            extract_feature_record(
                FeatureContext(
                    f"{result.target.module}:{result.target.symbol}",
                    Path(result.declared_contract_ref),
                    workspace,
                    Path(result.module_context_ref),
                )
            )
        except FeatureExtractionError as failure:
            unknown_reason = str(failure)
        else:
            raise ArtifactIntegrityError(
                "Previously unknown target information has changed; replay again"
            )
    if result.scope_decision == "unknown":
        expected_trace = tuple(
            ClauseTrace(
                field=clause.field, op=clause.op, expected=clause.value, actual=None, matched=None
            )
            for clause in scope.clauses
        )
        if result.decision_trace != expected_trace or result.error_detail != unknown_reason:
            raise ArtifactIntegrityError(
                "Unknown Replay reason/trace differs from available inputs"
            )
    if result.run:
        verify_run_record(
            result.run, cwd=workspace, known_case_ids=tuple(case.case_id for case in guard.cases)
        )
    return result


def render_replay_report(report: dict) -> str:
    labels = {
        "pass": "通过",
        "violation": "确认违规",
        "skipped_inapplicable": "不适用，未运行",
        "skipped_unknown": "信息不足，未运行",
        "collection_error": "收集错误",
        "execution_error": "执行错误",
        "timeout": "超时",
        "stale": "完整性错误",
    }
    lines = ["# 训练集作用域重放", "", "| 样本 | 作用域 | 结果 | pytest |", "|---|---|---|---|"]
    for row in report["results"]:
        result = row["result"]
        status = labels[result["verdict"]]
        execution = "已运行" if result["run"] else "未运行"
        lines.append(
            f"| {row['sample_id']} | {result['scope_decision']} | {status} | {execution} |"
        )
    return "\n".join(lines) + "\n"


def replay_train_benchmark(
    path: str | Path,
    *,
    phase: str,
    fitted: str | Path,
    cwd: str | Path,
    artifact_root: str | Path = "artifacts",
    split: str = "train",
) -> dict:
    if split != "train" or phase not in {"initial", "refined"}:
        raise ValueError(
            "Replay accepts initial/refined training scopes only; "
            "holdout is reserved for evaluation"
        )
    workspace = Path(cwd).resolve(strict=True)
    protocol, manifest, _ = verify_protocol(path, cwd=workspace)
    fitted_root = _path(Path(fitted), workspace)
    fit = _load_model(fitted_root / "fit-manifest.json", FitManifest)
    if fit.phase != phase:
        raise ArtifactIntegrityError("Requested phase differs from fitted phase")
    results = []
    bindings = {binding.guard_id: binding for binding in protocol.guards}
    groups = {group.guard_id: group for group in fit.groups}
    samples = sorted(
        [
            sample
            for item in manifest.files
            if item.split == "train"
            for sample in _read_samples(_path(Path(item.path), workspace))
        ],
        key=lambda sample: sample.sample_id,
    )
    for sample in samples:
        group = groups[sample.labels.guard_id]
        result = replay_guard(
            ReplayRequest(
                guard_path=Path(bindings[sample.labels.guard_id].guard_ref),
                scope_path=Path(group.scope_ref),
                target=f"{sample.target.module}:{sample.target.symbol}",
                contract_path=Path(sample.contract_ref),
                cwd=workspace,
                artifact_root=Path(artifact_root),
                protocol_path=Path(path),
                module_context_path=Path(fit.module_context_ref),
                fit_manifest_path=fitted_root / "fit-manifest.json",
            )
        )
        results.append({"sample_id": sample.sample_id, "result": result.model_dump(mode="json")})
    counts = {
        verdict: sum(row["result"]["verdict"] == verdict for row in results)
        for verdict in (
            "pass",
            "violation",
            "skipped_inapplicable",
            "skipped_unknown",
            "collection_error",
            "execution_error",
            "timeout",
            "stale",
        )
    }
    report = {
        "schema_version": "train-replay-report.v1",
        "protocol_digest": protocol.artifact_digest,
        "phase": phase,
        "split": "train",
        "sample_count": len(results),
        "counts": counts,
        "execution_count": sum(row["result"]["run"] is not None for row in results),
        "results": results,
    }
    report["artifact_digest"] = digest_json_artifact(report)
    output = _path(Path(artifact_root), workspace) / f"experiments/scope-v1/train-replays/{phase}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_bytes(canonical_json_bytes(report))
    (output / "report.md").write_text(render_replay_report(report), encoding="utf-8")
    return report
