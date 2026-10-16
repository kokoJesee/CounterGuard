"""Evaluate four frozen methods without refitting, then audit immutable results."""

from __future__ import annotations

import math
import platform
import time
import uuid
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from counterguard.artifacts import write_immutable
from counterguard.baselines import ScopePredicate, decide_scope, make_baseline
from counterguard.digests import (
    canonical_json_bytes,
    digest_bytes,
    digest_file,
    digest_json_artifact,
)
from counterguard.errors import ArtifactIntegrityError
from counterguard.evaluation_metrics import (
    METHOD_ORDER,
    EvaluationMetrics,
    Method,
    compute_metrics,
    paired_refinement,
    prediction_from_replay,
)
from counterguard.execution import _classify_completed_run
from counterguard.models import ArtifactRef, Digest, FrozenModel, Guard, NonEmptyText, UtcDateTime
from counterguard.path_limits import require_evaluation_directory, require_publication
from counterguard.protocol import _load_model, _path, _read_samples, verify_protocol
from counterguard.replay import (
    ReplayRequest,
    ReplayResult,
    replay_guard,
    verify_replay,
    verify_scope_binding,
)
from counterguard.scope import SCOPE_V1_PROTOCOL_DIGEST, FitManifest

EXPECTED_HOLDOUT = {
    "b1_always": {"tp": 2, "fp": 4, "tn": 0, "fn": 0},
    "b2_interface": {"tp": 2, "fp": 2, "tn": 2, "fn": 0},
    "learned_initial": {"tp": 2, "fp": 2, "tn": 2, "fn": 0},
    "learned_refined": {"tp": 2, "fp": 0, "tn": 4, "fn": 0},
}


class ReplayRow(FrozenModel):
    method: Method
    guard_id: NonEmptyText
    sample_id: NonEmptyText
    replay_ref: ArtifactRef
    result: ReplayResult


class EvaluationReport(FrozenModel):
    schema_version: Literal["evaluation-report.v1"] = "evaluation-report.v1"
    evaluation_id: NonEmptyText
    started_at: UtcDateTime
    completed_at: UtcDateTime
    duration_ms: int = Field(ge=0)
    protocol_ref: ArtifactRef
    protocol_digest: Digest
    split_ref: ArtifactRef
    split_digest: Digest
    split: Literal["holdout"] = "holdout"
    metric_version: Literal["scope-v1-metrics.v1"] = "scope-v1-metrics.v1"
    fit_refs: dict[str, ArtifactRef]
    fit_digests: dict[str, Digest]
    scope_refs: dict[Method, dict[str, ArtifactRef]]
    scope_digests: dict[Method, dict[str, Digest]]
    code_file_digests: dict[ArtifactRef, Digest]
    code_digest: Digest
    environment: dict[str, str]
    sample_count: int = Field(ge=1)
    prediction_count: int = Field(ge=1)
    execution_count: int = Field(ge=0)
    source_check_execution_count: int = Field(ge=0)
    files: dict[ArtifactRef, Digest]
    accepted: bool
    acceptance_failures: tuple[str, ...]
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent_identity_and_time(self) -> Self:
        if not self.evaluation_id.startswith("eval_") or self.completed_at < self.started_at:
            raise ValueError("Evaluation requires a namespaced identity and actual ordered times")
        if self.accepted == bool(self.acceptance_failures):
            raise ValueError("Acceptance status and failure reasons disagree")
        return self


def _jsonl(rows) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def _read_jsonl(path: Path, model):
    return tuple(model.model_validate_json(line) for line in path.read_bytes().splitlines() if line)


CODE_MODULES = (
    "__init__",
    "__main__",
    "artifacts",
    "baselines",
    "change_analysis",
    "cli",
    "compiler",
    "contracts",
    "diagnostics",
    "digests",
    "errors",
    "evaluation",
    "evaluation_metrics",
    "evidence",
    "execution",
    "features",
    "models",
    "module_context",
    "path_limits",
    "predicates",
    "preflight",
    "project_config",
    "protocol",
    "replay",
    "repository",
    "report",
    "registry",
    "registry_cli",
    "runners/__init__",
    "runners/base",
    "runners/docker",
    "runners/local",
    "scope",
    "storage/__init__",
    "storage/sqlite",
)


def _code_files(workspace: Path) -> dict[str, str]:
    # Hash the implementation actually imported by this process, including in
    # tests whose trusted source workspace is a temporary fixture copy.
    package = Path(__file__).parent
    return {
        f"src/counterguard/{name}.py": digest_file(package / f"{name}.py") for name in CODE_MODULES
    }


def _fit_paths(root: Path) -> dict[str, Path]:
    return {
        phase: (
            root / "learning-v2" / phase / "fit-manifest.json"
            if (root / "learning-v2" / phase / "fit-manifest.json").exists()
            else root / phase / "fit-manifest.json"
        )
        for phase in ("initial", "refined")
    }


def _acceptance(metrics: EvaluationMetrics, paired: dict, source_checks: tuple[ReplayRow, ...]):
    failures = []
    for method in METHOD_ORDER:
        current = metrics.methods[method].micro
        if current.confusion.model_dump() != EXPECTED_HOLDOUT[method]:
            failures.append(f"{method}: frozen holdout confusion differs")
        if any(
            current.verdict_counts[key]
            for key in ("collection_error", "execution_error", "timeout", "stale")
        ):
            failures.append(f"{method}: execution or integrity failure")
    totals = paired["totals"]
    if totals["corrected_false_applications"] != 2 or totals["retained_applicable_cases"] != 2:
        failures.append(
            "Refinement did not correct two false applications and retain two positives"
        )
    if totals["new_false_rejections"] or totals["new_false_applications"]:
        failures.append("Refinement introduced a new scope error")
    if (
        totals["delta_false_application_rate"] is None
        or totals["delta_false_application_rate"] >= 0
    ):
        failures.append("False application rate did not decrease")
    if totals["delta_recall"] is None or totals["delta_recall"] < 0:
        failures.append("Scope recall decreased or is undefined")
    if len(source_checks) != 4 or any(
        row.result.scope_decision != "applicable" or row.result.verdict != "violation"
        for row in source_checks
    ):
        failures.append("Original source bugs are not covered and detected in both learned phases")
    return tuple(failures)


def evaluate_methods(
    path: str | Path,
    *,
    fitted: str | Path,
    output: str | Path,
    cwd: str | Path,
    split: str = "holdout",
    timeout_seconds: float = 30.0,
) -> EvaluationReport:
    if split != "holdout":
        raise ValueError("Only the frozen holdout split can be evaluated.")
    if timeout_seconds <= 0 or not math.isfinite(timeout_seconds):
        raise ValueError("Evaluation timeout must be positive and finite")
    workspace = Path(cwd).resolve(strict=True)
    destination = _path(Path(output), workspace)
    if (destination / "manifest.json").exists():
        existing = verify_evaluation(destination, cwd=workspace)
        requested_fits = _fit_paths(_path(Path(fitted), workspace))
        if (
            existing.protocol_ref != _path(Path(path), workspace).relative_to(workspace).as_posix()
            or any(
                existing.fit_refs[phase] != value.relative_to(workspace).as_posix()
                for phase, value in requested_fits.items()
            )
            or existing.environment["timeout_seconds"] != str(float(timeout_seconds))
        ):
            raise ArtifactIntegrityError("Existing evaluation has different immutable inputs")
        return existing
    if destination.exists() and any(destination.iterdir()):
        raise ArtifactIntegrityError(
            "Evaluation directory is not empty; choose a new output version"
        )
    require_evaluation_directory(destination)
    protocol, manifest, guards = verify_protocol(path, cwd=workspace)
    if protocol.artifact_digest != SCOPE_V1_PROTOCOL_DIGEST:
        raise ArtifactIntegrityError("Evaluation requires the original frozen scope_v1 protocol")
    fits = _fit_paths(_path(Path(fitted), workspace))
    loaded = {phase: _load_model(file, FitManifest) for phase, file in fits.items()}
    bindings = {item.guard_id: item for item in protocol.guards}
    for phase, fit in loaded.items():
        if fit.phase != phase:
            raise ArtifactIntegrityError("Evaluation fit phase mismatch")
        for group in fit.groups:
            verify_scope_binding(
                Path(group.scope_ref),
                Path(bindings[group.guard_id].guard_ref),
                cwd=workspace,
                protocol_path=Path(path),
                fit_manifest_path=fits[phase],
            )
    samples = tuple(
        sorted(
            (
                sample
                for file in manifest.files
                if file.split == "holdout"
                for sample in _read_samples(_path(Path(file.path), workspace))
            ),
            key=lambda sample: (sample.labels.guard_id, sample.sample_id),
        )
    )
    training = {
        sample.sample_id: sample
        for file in manifest.files
        if file.split == "train"
        for sample in _read_samples(_path(Path(file.path), workspace))
    }
    scope_paths = {}
    scopes = {}
    for method in METHOD_ORDER:
        scopes[method] = {}
        for guard_id, guard in sorted(guards.items()):
            if method.startswith("learned_"):
                phase = method.removeprefix("learned_")
                group = next(group for group in loaded[phase].groups if group.guard_id == guard_id)
                scope_path = _path(Path(group.scope_ref), workspace)
                scope = _load_model(scope_path, ScopePredicate)
            else:
                scope_path = destination / "scopes" / method / f"{guard_id}.json"
                scope = make_baseline(
                    guard,
                    method,
                    interface_kind=bindings[guard_id].frozen_interface_kind,
                    protocol_digest=protocol.artifact_digest,
                )
            scope_paths[(method, guard_id)] = scope_path
            if not method.startswith("learned_"):
                require_publication(scope_path)
            scopes[method][guard_id] = scope
    code_files = _code_files(workspace)
    started_at, clock = datetime.now(UTC), time.monotonic()
    evaluation_id = "eval_" + uuid.uuid4().hex
    replays, source_checks, predictions = [], [], []
    try:
        for method in ("b1_always", "b2_interface"):
            for guard_id, scope in scopes[method].items():
                write_immutable(scope_paths[(method, guard_id)], canonical_json_bytes(scope))

        def execute(method, sample):
            guard_id = sample.labels.guard_id
            phase = method.removeprefix("learned_") if method.startswith("learned_") else None
            result = replay_guard(
                ReplayRequest(
                    guard_path=Path(bindings[guard_id].guard_ref),
                    scope_path=scope_paths[(method, guard_id)],
                    target=f"{sample.target.module}:{sample.target.symbol}",
                    contract_path=Path(sample.contract_ref),
                    cwd=workspace,
                    artifact_root=destination / "runtime",
                    protocol_path=Path(path),
                    fit_manifest_path=fits[phase] if phase else None,
                    timeout_seconds=timeout_seconds,
                )
            )
            return ReplayRow(
                method=method,
                guard_id=guard_id,
                sample_id=sample.sample_id,
                replay_ref=(destination / "runtime/replays" / result.replay_id / "result.json")
                .relative_to(workspace)
                .as_posix(),
                result=result,
            )

        for method in METHOD_ORDER:
            for sample in samples:
                row = execute(method, sample)
                replays.append(row)
                predictions.append(
                    prediction_from_replay(method, sample.sample_id, sample.labels, row.result)
                )
        # Source probes are training members, outside all holdout metric denominators.
        for phase, fit in loaded.items():
            for group in sorted(fit.groups, key=lambda group: group.guard_id):
                source_checks.append(
                    execute(f"learned_{phase}", training[group.source_bug_sample_id])
                )
        final_protocol, final_split, _ = verify_protocol(path, cwd=workspace)
        if (
            final_protocol != protocol
            or final_split != manifest
            or _code_files(workspace) != code_files
        ):
            raise ArtifactIntegrityError(
                "Evaluation inputs or implementation changed during execution"
            )
        metrics = compute_metrics(tuple(predictions))
        paired = paired_refinement(tuple(predictions), metrics)
        failures = _acceptance(metrics, paired, tuple(source_checks))
        payloads = {
            "predictions.jsonl": _jsonl(predictions),
            "replays.jsonl": _jsonl(replays),
            "source-checks.jsonl": _jsonl(source_checks),
            "metrics.json": canonical_json_bytes(metrics),
            "paired-refinement.json": canonical_json_bytes(paired),
        }
        from counterguard.report import render_evaluation

        payloads["report.md"] = render_evaluation(metrics, paired, not failures).encode("utf-8")
        for name, content in payloads.items():
            write_immutable(destination / name, content)
        draft = EvaluationReport(
            evaluation_id=evaluation_id,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=int((time.monotonic() - clock) * 1000),
            protocol_ref=_path(Path(path), workspace).relative_to(workspace).as_posix(),
            protocol_digest=protocol.artifact_digest,
            split_ref=protocol.split_ref,
            split_digest=manifest.artifact_digest,
            fit_refs={
                phase: file.relative_to(workspace).as_posix() for phase, file in fits.items()
            },
            fit_digests={phase: fit.artifact_digest for phase, fit in loaded.items()},
            scope_refs={
                method: {
                    gid: scope_paths[(method, gid)].relative_to(workspace).as_posix()
                    for gid in scopes[method]
                }
                for method in METHOD_ORDER
            },
            scope_digests={
                method: {gid: scope.artifact_digest for gid, scope in scopes[method].items()}
                for method in METHOD_ORDER
            },
            code_file_digests=code_files,
            code_digest=digest_bytes(canonical_json_bytes(code_files)),
            environment={
                "python": platform.python_version(),
                "pytest": version("pytest"),
                "pydantic": version("pydantic"),
                "typer": version("typer"),
                "platform": platform.system(),
                "executor": "trusted_local",
                "timeout_seconds": str(float(timeout_seconds)),
            },
            sample_count=len(samples),
            prediction_count=len(predictions),
            execution_count=sum(row.result.run is not None for row in replays),
            source_check_execution_count=sum(row.result.run is not None for row in source_checks),
            files={name: digest_bytes(content) for name, content in payloads.items()},
            accepted=not failures,
            acceptance_failures=failures,
            artifact_digest="sha256:" + "0" * 64,
        )
        result = draft.model_copy(update={"artifact_digest": digest_json_artifact(draft)})
        write_immutable(destination / "manifest.json", canonical_json_bytes(result))
        return result
    except (ArtifactIntegrityError, ValueError, OSError) as error:
        write_immutable(
            destination / "failure.json",
            canonical_json_bytes(
                {
                    "schema_version": "evaluation-failure.v1",
                    "evaluation_id": evaluation_id,
                    "started_at": started_at.isoformat(),
                    "failed_at": datetime.now(UTC).isoformat(),
                    "error_type": type(error).__name__,
                    "detail": str(error),
                    "completed_replays": [row.model_dump(mode="json") for row in replays],
                    "completed_source_checks": [
                        row.model_dump(mode="json") for row in source_checks
                    ],
                }
            ),
        )
        raise


def verify_evaluation(path: str | Path, *, cwd: str | Path) -> EvaluationReport:
    """Rebuild all metrics from raw records without executing targets or refitting."""
    workspace = Path(cwd).resolve(strict=True)
    directory = _path(Path(path), workspace)
    report = _load_model(directory / "manifest.json", EvaluationReport)
    if set(report.files) != {
        "predictions.jsonl",
        "replays.jsonl",
        "source-checks.jsonl",
        "metrics.json",
        "paired-refinement.json",
        "report.md",
    }:
        raise ArtifactIntegrityError("Evaluation file membership changed")
    for ref, expected in report.files.items():
        if digest_file(_path(directory / ref, workspace)) != expected:
            raise ArtifactIntegrityError(f"Evaluation file digest mismatch: {ref}")
    protocol, split, _ = verify_protocol(report.protocol_ref, cwd=workspace)
    if (
        protocol.artifact_digest != SCOPE_V1_PROTOCOL_DIGEST
        or protocol.artifact_digest != report.protocol_digest
        or split.artifact_digest != report.split_digest
        or protocol.split_ref != report.split_ref
    ):
        raise ArtifactIntegrityError("Evaluation protocol/split changed")
    guard_ids = {binding.guard_id for binding in protocol.guards}
    if (
        set(report.scope_refs) != set(METHOD_ORDER)
        or set(report.scope_digests) != set(METHOD_ORDER)
        or any(set(report.scope_refs[method]) != guard_ids for method in METHOD_ORDER)
        or any(set(report.scope_digests[method]) != guard_ids for method in METHOD_ORDER)
    ):
        raise ArtifactIntegrityError("Evaluation scope membership changed")
    if report.code_file_digests != _code_files(workspace) or report.code_digest != digest_bytes(
        canonical_json_bytes(report.code_file_digests)
    ):
        raise ArtifactIntegrityError(
            "Evaluation implementation changed; keep history and run a new version"
        )
    fits = {
        phase: _load_model(_path(Path(ref), workspace), FitManifest)
        for phase, ref in report.fit_refs.items()
    }
    if set(fits) != {"initial", "refined"} or any(
        fit.phase != phase or fit.artifact_digest != report.fit_digests.get(phase)
        for phase, fit in fits.items()
    ):
        raise ArtifactIntegrityError("Evaluation fitted provenance changed")
    samples = {
        sample.sample_id: sample
        for item in split.files
        for sample in _read_samples(_path(Path(item.path), workspace))
    }
    expected_holdout = {
        (sample.labels.guard_id, sid)
        for sid, sample in samples.items()
        if any(sid in phase.holdout for phase in split.phases.values())
    }
    replays = _read_jsonl(directory / "replays.jsonl", ReplayRow)
    probes = _read_jsonl(directory / "source-checks.jsonl", ReplayRow)
    expected_probes = {
        (f"learned_{phase}", group.guard_id, group.source_bug_sample_id)
        for phase, fit in fits.items()
        for group in fit.groups
    }
    if (
        len(probes) != len(expected_probes)
        or {(r.method, r.guard_id, r.sample_id) for r in probes} != expected_probes
    ):
        raise ArtifactIntegrityError("Source check membership changed")
    if len(replays) != 4 * len(expected_holdout) or {
        (r.method, r.guard_id, r.sample_id) for r in replays
    } != {(method, gid, sid) for method in METHOD_ORDER for gid, sid in expected_holdout}:
        raise ArtifactIntegrityError("Evaluation has duplicate, missing or unexpected holdout rows")
    if len({row.result.replay_id for row in (*replays, *probes)}) != len(replays) + len(probes):
        raise ArtifactIntegrityError("Real executions must retain distinct Replay identities")
    predictions = []
    for row in (*replays, *probes):
        sample = samples[row.sample_id]
        actual = verify_replay(row.replay_ref, cwd=workspace)
        if not report.started_at <= actual.created_at <= report.completed_at:
            raise ArtifactIntegrityError("Replay time does not belong to this actual evaluation")
        if actual.run and (
            not report.started_at <= actual.run.started_at <= report.completed_at
            or actual.run.python_version != report.environment.get("python")
            or actual.run.pytest_version != report.environment.get("pytest")
            or str(float(actual.run.timeout_seconds)) != report.environment.get("timeout_seconds")
        ):
            raise ArtifactIntegrityError(
                "Actual execution environment or time disagrees with evaluation"
            )
        if actual.run and actual.run.pytest_exit_code is not None:
            guard = _load_model(_path(Path(actual.guard_ref), workspace), Guard)
            outcome, cases, _ = _classify_completed_run(
                actual.run.pytest_exit_code,
                _path(Path(actual.run.junit_ref), workspace),
                tuple(case.case_id for case in guard.cases),
            )
            if outcome != actual.run.outcome or cases != actual.run.case_results:
                raise ArtifactIntegrityError("Raw JUnit contradicts the claimed execution result")
        if (
            actual != row.result
            or row.guard_id != actual.guard_id
            or row.guard_id != sample.labels.guard_id
            or (actual.target.module, actual.target.symbol)
            != (sample.target.module, sample.target.symbol)
            or actual.declared_contract_ref != sample.contract_ref
        ):
            raise ArtifactIntegrityError(
                "Raw replay does not belong to its declared evaluation sample"
            )
        if (
            actual.scope_ref != report.scope_refs.get(row.method, {}).get(row.guard_id)
            or actual.scope_digest != report.scope_digests.get(row.method, {}).get(row.guard_id)
            or actual.protocol_ref != report.protocol_ref
        ):
            raise ArtifactIntegrityError("Evaluation method scope binding changed")
        phase = row.method.removeprefix("learned_") if row.method.startswith("learned_") else None
        if (actual.fit_manifest_ref, actual.fit_manifest_digest) != (
            (report.fit_refs[phase], report.fit_digests[phase]) if phase else (None, None)
        ):
            raise ArtifactIntegrityError("Evaluation replay fit binding changed")
        expected_strategy = (
            "learned_conjunction"
            if phase
            else "always"
            if row.method == "b1_always"
            else "fixed_interface"
        )
        scope = _load_model(_path(Path(actual.scope_ref), workspace), ScopePredicate)
        if scope.strategy != expected_strategy:
            raise ArtifactIntegrityError("Evaluation method was relabeled")
        if actual.feature_vector is not None:
            expected_decision = decide_scope(scope, actual.feature_vector.model_dump(mode="json"))
            if actual.decision_trace != expected_decision.trace:
                raise ArtifactIntegrityError(
                    "Evaluation trace does not follow actual automatic features"
                )
        if row in replays:
            predictions.append(
                prediction_from_replay(row.method, row.sample_id, sample.labels, actual)
            )
    if (directory / "predictions.jsonl").read_bytes() != _jsonl(predictions):
        raise ArtifactIntegrityError(
            "Predictions cannot be reconstructed from raw Replay and frozen labels"
        )
    metrics = compute_metrics(tuple(predictions))
    paired = paired_refinement(tuple(predictions), metrics)
    if (directory / "metrics.json").read_bytes() != canonical_json_bytes(metrics) or (
        directory / "paired-refinement.json"
    ).read_bytes() != canonical_json_bytes(paired):
        raise ArtifactIntegrityError("Metrics or paired refinement do not follow raw predictions")
    failures = _acceptance(metrics, paired, probes)
    if (
        report.acceptance_failures != failures
        or report.accepted != (not failures)
        or report.sample_count != len(expected_holdout)
        or report.prediction_count != len(replays)
        or report.execution_count != sum(r.result.run is not None for r in replays)
        or report.source_check_execution_count != sum(r.result.run is not None for r in probes)
    ):
        raise ArtifactIntegrityError("Evaluation summary does not follow its evidence")
    from counterguard.report import render_evaluation

    if (directory / "report.md").read_text(encoding="utf-8") != render_evaluation(
        metrics, paired, report.accepted
    ):
        raise ArtifactIntegrityError("Markdown does not render the stored JSON facts")
    return report
