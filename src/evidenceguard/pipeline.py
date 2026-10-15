"""One trusted capture/compile/learn/replay flow with a verified completion manifest."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from evidenceguard.artifacts import write_immutable
from evidenceguard.compiler import CompileRequest, compile_guard, verify_guard
from evidenceguard.digests import (
    canonical_json_bytes,
    digest_bytes,
    digest_file,
    digest_json_artifact,
)
from evidenceguard.errors import (
    ArtifactIntegrityError,
    EvidenceGuardError,
)
from evidenceguard.evaluation import _code_files
from evidenceguard.execution import _classify_completed_run, require_pytest
from evidenceguard.models import (
    ArtifactRef,
    Digest,
    FrozenModel,
    NonEmptyText,
    RunOutcome,
    RunRecord,
    UtcDateTime,
)
from evidenceguard.protocol import BenchmarkSample, _load_model, _path, verify_protocol
from evidenceguard.replay import (
    ReplayRequest,
    ReplayResult,
    replay_guard,
    verify_replay,
    verify_scope_binding,
)
from evidenceguard.scope import FitManifest, fit_scopes
from evidenceguard.verification_gate import capture_candidate, gate_exit_code, verify_gate
from evidenceguard.workspace import (
    EMPTY_DIGEST,
    WorkspaceManifest,
    load_scenario,
    prepare_workspace,
    scenario_inputs,
    verify_workspace,
)

Stage = Literal["capture", "compile", "learn", "replay", "verify"]


class ArtifactLink(FrozenModel):
    """References are relative to the caller's source cwd, not the mirrored cwd."""

    ref: ArtifactRef
    artifact_digest: Digest


class PipelineGroup(FrozenModel):
    guard_id: NonEmptyText
    gate: ArtifactLink
    evidence: ArtifactLink
    guard: ArtifactLink
    initial_scope: ArtifactLink
    initial_learning: ArtifactLink
    refined_scope: ArtifactLink
    refined_learning: ArtifactLink


class PipelineReplay(FrozenModel):
    guard_id: NonEmptyText
    sample_id: NonEmptyText
    replay: ArtifactLink
    scope_decision: Literal["applicable", "inapplicable", "unknown"]
    execution_outcome: RunOutcome | Literal["not_run"]
    verdict: NonEmptyText


class PipelineManifest(FrozenModel):
    schema_version: Literal["pipeline-run.v1"] = "pipeline-run.v1"
    run_id: NonEmptyText
    created_at: UtcDateTime
    scenario_id: NonEmptyText
    scenario_ref: ArtifactRef
    scenario_digest: Digest
    workspace: ArtifactLink
    runtime_ref: ArtifactRef
    protocol_digest: Digest
    split_digest: Digest
    code_file_digests: dict[ArtifactRef, Digest]
    code_digest: Digest
    environment: dict[str, str]
    initial_fit: ArtifactLink
    refined_fit: ArtifactLink
    groups: Annotated[tuple[PipelineGroup, ...], Field(min_length=2, max_length=2)]
    replays: Annotated[tuple[PipelineReplay, ...], Field(min_length=6, max_length=6)]
    verdict_counts: dict[str, int]
    execution_count: Annotated[int, Field(ge=0)]
    accepted: bool
    artifact_digest: Digest

    @model_validator(mode="after")
    def canonical_rows(self) -> Self:
        groups = [group.guard_id for group in self.groups]
        rows = [(row.guard_id, row.sample_id) for row in self.replays]
        if (
            not self.run_id.startswith("pip_")
            or groups != sorted(set(groups))
            or rows != sorted(set(rows))
        ):
            raise ValueError("Pipeline requires a safe run identity and canonical distinct rows")
        if self.verdict_counts != dict(Counter(row.verdict for row in self.replays)):
            raise ValueError("Pipeline counts must describe its actual replay rows")
        if self.execution_count != sum(row.execution_outcome != "not_run" for row in self.replays):
            raise ValueError("Pipeline execution count contradicts replay rows")
        return self


class PipelineFailure(FrozenModel):
    schema_version: Literal["pipeline-failure.v1"] = "pipeline-failure.v1"
    created_at: UtcDateTime
    workspace: ArtifactLink
    failed_stage: Stage
    reason_code: NonEmptyText
    exit_code: Annotated[int, Field(ge=1)]
    completed_artifacts: tuple[ArtifactLink, ...]
    artifact_digest: Digest


class PipelineExecutionError(EvidenceGuardError):
    def __init__(self, stage: str, code: int, failure_ref: str):
        super().__init__(f"Pipeline stopped during {stage}; see {failure_ref}")
        self.exit_code = code


class _StageRejected(Exception):
    def __init__(self, reason: str, code: int):
        self.reason, self.exit_code = reason, code


def _code_bindings() -> dict[str, str]:
    files = _code_files(Path.cwd())
    package = Path(__file__).parent
    for name in (
        "pipeline",
        "workspace",
        "independent_verifier",
        "model_client",
        "verification_gate",
    ):
        files[f"src/evidenceguard/{name}.py"] = digest_file(package / f"{name}.py")
    return files


def _environment() -> dict[str, str]:
    import platform

    return {
        "python": platform.python_version(),
        "pytest": require_pytest(),
        **{name: version(name) for name in ("pydantic", "typer")},
    }


def _link(path: Path, record, cwd: Path) -> ArtifactLink:
    return ArtifactLink(
        ref=path.relative_to(cwd).as_posix(), artifact_digest=record.artifact_digest
    )


def _linked(link: ArtifactLink, model, cwd: Path, runtime: Path):
    path = _path(Path(link.ref), cwd)
    if not path.is_relative_to(runtime):
        raise ArtifactIntegrityError("Pipeline stage reference escapes its runtime namespace")
    value = _load_model(path, model)
    if value.artifact_digest != link.artifact_digest:
        raise ArtifactIntegrityError("Pipeline stage digest mismatch")
    return path, value


def _raw_run(run: RunRecord, *, runtime: Path, cases: tuple[str, ...]) -> None:
    for ref, digest in (
        (run.stdout_ref, run.stdout_digest),
        (run.stderr_ref, run.stderr_digest),
        (run.junit_ref, run.junit_digest),
    ):
        if digest_file(_path(Path(ref), runtime)) != digest:
            raise ArtifactIntegrityError("Pipeline execution log digest mismatch")
    if run.pytest_exit_code is not None:
        outcome, results, _ = _classify_completed_run(
            run.pytest_exit_code, _path(Path(run.junit_ref), runtime), cases
        )
        if outcome != run.outcome or results != run.case_results:
            raise ArtifactIntegrityError("Pipeline raw JUnit contradicts execution metadata")


def _accepted(sample: BenchmarkSample, replay: ReplayResult) -> bool:
    if not sample.labels.guard_applicable:
        return (
            replay.scope_decision == "inapplicable"
            and replay.verdict == "skipped_inapplicable"
            and replay.run is None
        )
    expected = "violation" if sample.labels.guard_violation else "pass"
    return replay.scope_decision == "applicable" and replay.verdict == expected


def _row(sample: BenchmarkSample, replay: ReplayResult, runtime: Path, cwd: Path) -> PipelineReplay:
    return PipelineReplay(
        guard_id=sample.labels.guard_id,
        sample_id=sample.sample_id,
        replay=_link(runtime / f"artifacts/replays/{replay.replay_id}/result.json", replay, cwd),
        scope_decision=replay.scope_decision,
        execution_outcome=replay.run.outcome if replay.run else "not_run",
        verdict=replay.verdict,
    )


def _verify_stages(ledger, *, source, captured, guards, fits, rows, samples) -> Path:
    """Audit published stages before another stage can start executing."""
    runtime = verify_workspace(ledger, cwd=source)
    scenario = load_scenario(source / ledger.scenario_ref)
    for path, expected in captured.values():
        if verify_gate(path, cwd=runtime) != expected:
            raise ArtifactIntegrityError("Pipeline completed Gate changed")
    for identity, expected in guards.items():
        if (
            verify_guard(runtime / f"artifacts/guards/{identity}/guard.json", cwd=runtime)
            != expected
        ):
            raise ArtifactIntegrityError("Pipeline completed Guard changed")
    for phase, expected in fits.items():
        path = runtime / f"artifacts/fitted/{phase}/fit-manifest.json"
        if _load_model(path, FitManifest) != expected:
            raise ArtifactIntegrityError("Pipeline completed fit changed")
        for group in expected.groups:
            verify_scope_binding(
                Path(group.scope_ref),
                Path(f"artifacts/guards/{group.guard_id}/guard.json"),
                cwd=runtime,
                protocol_path=Path(scenario.protocol_ref),
                fit_manifest_path=path,
            )
    for row in rows:
        _, result = _linked(row.replay, ReplayResult, source, runtime)
        if row != _row(samples[row.sample_id], result, runtime, source):
            raise ArtifactIntegrityError("Pipeline completed replay changed")
        if result.run:
            _raw_run(
                result.run,
                runtime=runtime,
                cases=tuple(case.case_id for case in guards[row.guard_id].cases),
            )
    return runtime


def run_pipeline(
    scenario_path: str | Path, *, cwd: str | Path, workspace: str | Path
) -> PipelineManifest:
    source = Path(cwd).resolve(strict=True)
    scenario_path = _path(Path(scenario_path), source)
    output = _path(Path(workspace), source)
    if (output / "run_manifest.json").exists():
        manifest = verify_pipeline(output / "run_manifest.json", cwd=source)
        if manifest.scenario_ref != scenario_path.relative_to(source).as_posix():
            raise ArtifactIntegrityError("Pipeline workspace belongs to another scenario file")
        return manifest
    code_files, environment = _code_bindings(), _environment()
    ledger = prepare_workspace(scenario_path, cwd=source, output=output)
    ledger_link = _link(output / "workspace_manifest.json", ledger, source)
    runtime = verify_workspace(ledger, cwd=source)
    scenario = load_scenario(scenario_path)
    _, _, samples, requests, _ = scenario_inputs(scenario, cwd=runtime)
    completed = []
    captured, guards, fits, rows = {}, {}, {}, []
    stage: Stage = "capture"
    try:
        for group in sorted(scenario.guards, key=lambda item: item.guard_id):
            _verify_stages(
                ledger,
                source=source,
                captured=captured,
                guards=guards,
                fits=fits,
                rows=rows,
                samples=samples,
            )
            gate = capture_candidate(group.request_ref, cwd=runtime, workspace="artifacts")
            stem = requests[group.guard_id].request_id.removeprefix("req_")
            gate_path = runtime / f"artifacts/candidates/cnd_{stem}/gate.json"
            completed.append(_link(gate_path, gate, source))
            if gate.status != "verified":
                raise _StageRejected("candidate_not_verified", gate_exit_code(gate, cwd=runtime))
            captured[group.guard_id] = (gate_path, gate)
        stage = "compile"
        for guard_id, (_gate_path, gate) in sorted(captured.items()):
            _verify_stages(
                ledger,
                source=source,
                captured=captured,
                guards=guards,
                fits=fits,
                rows=rows,
                samples=samples,
            )
            guard = compile_guard(
                CompileRequest(guard_id, Path(gate.evidence_ref), runtime, Path("artifacts"))
            )
            guards[guard_id] = guard
            completed.append(
                _link(runtime / f"artifacts/guards/{guard_id}/guard.json", guard, source)
            )
        protocol, split, _ = verify_protocol(scenario.protocol_ref, cwd=runtime)
        stage = "learn"
        for phase in ("initial", "refined"):
            _verify_stages(
                ledger,
                source=source,
                captured=captured,
                guards=guards,
                fits=fits,
                rows=rows,
                samples=samples,
            )
            fits[phase] = fit_scopes(
                scenario.protocol_ref, phase=phase, output=f"artifacts/fitted/{phase}", cwd=runtime
            )
            completed.append(
                _link(runtime / f"artifacts/fitted/{phase}/fit-manifest.json", fits[phase], source)
            )
            _verify_stages(
                ledger,
                source=source,
                captured=captured,
                guards=guards,
                fits=fits,
                rows=rows,
                samples=samples,
            )
        stage = "replay"
        for group in sorted(scenario.guards, key=lambda item: item.guard_id):
            for sample_id in sorted(group.replay_sample_ids):
                _verify_stages(
                    ledger,
                    source=source,
                    captured=captured,
                    guards=guards,
                    fits=fits,
                    rows=rows,
                    samples=samples,
                )
                sample = samples[sample_id]
                request = ReplayRequest(
                    guard_path=Path(f"artifacts/guards/{group.guard_id}/guard.json"),
                    scope_path=Path(f"artifacts/fitted/refined/{group.guard_id}.json"),
                    target=f"{sample.target.module}:{sample.target.symbol}",
                    contract_path=Path(sample.contract_ref),
                    cwd=runtime,
                    protocol_path=Path(scenario.protocol_ref),
                )
                result = replay_guard(request)
                row = _row(sample, result, runtime, source)
                rows.append(row)
                completed.append(row.replay)
                if result.verdict in {"stale", "collection_error", "execution_error", "timeout"}:
                    raise _StageRejected("replay_failed", 5 if result.verdict == "stale" else 3)
        stage = "verify"
        groups = []
        for guard_id, guard in sorted(guards.items()):
            gate_path, gate = captured[guard_id]
            inputs = {}
            for phase in ("initial", "refined"):
                fit_group = next(g for g in fits[phase].groups if g.guard_id == guard_id)
                inputs[phase + "_scope"] = ArtifactLink(
                    ref=(runtime / fit_group.scope_ref).relative_to(source).as_posix(),
                    artifact_digest=fit_group.scope_digest,
                )
                inputs[phase + "_learning"] = ArtifactLink(
                    ref=(runtime / fit_group.learning_ref).relative_to(source).as_posix(),
                    artifact_digest=fit_group.learning_digest,
                )
            groups.append(
                PipelineGroup(
                    guard_id=guard_id,
                    gate=_link(gate_path, gate, source),
                    evidence=ArtifactLink(
                        ref=(runtime / gate.evidence_ref).relative_to(source).as_posix(),
                        artifact_digest=gate.evidence_digest,
                    ),
                    guard=_link(runtime / f"artifacts/guards/{guard_id}/guard.json", guard, source),
                    **inputs,
                )
            )
        draft = PipelineManifest(
            run_id="pip_" + uuid.uuid4().hex,
            created_at=datetime.now(UTC),
            scenario_id=scenario.scenario_id,
            scenario_ref=ledger.scenario_ref,
            scenario_digest=ledger.scenario_digest,
            workspace=ledger_link,
            runtime_ref=ledger.runtime_ref,
            protocol_digest=protocol.artifact_digest,
            split_digest=split.artifact_digest,
            code_file_digests=code_files,
            code_digest=digest_bytes(canonical_json_bytes(code_files)),
            environment=environment,
            initial_fit=_link(
                runtime / "artifacts/fitted/initial/fit-manifest.json", fits["initial"], source
            ),
            refined_fit=_link(
                runtime / "artifacts/fitted/refined/fit-manifest.json", fits["refined"], source
            ),
            groups=tuple(groups),
            replays=tuple(rows),
            verdict_counts=dict(Counter(row.verdict for row in rows)),
            execution_count=sum(row.execution_outcome != "not_run" for row in rows),
            accepted=all(
                _accepted(
                    samples[row.sample_id],
                    _load_model(_path(Path(row.replay.ref), source), ReplayResult),
                )
                for row in rows
            ),
            artifact_digest=EMPTY_DIGEST,
        )
        manifest = draft.model_copy(update={"artifact_digest": digest_json_artifact(draft)})
        _audit_manifest(manifest, source=source, output=output)
        write_immutable(output / "run_manifest.json", canonical_json_bytes(manifest) + b"\n")
        return verify_pipeline(output / "run_manifest.json", cwd=source)
    except Exception as error:
        # Preserve partial artifacts even for an unexpected integration fault;
        # retain its Python cause without serializing arbitrary exception text.
        code = (
            5
            if isinstance(error, ArtifactIntegrityError)
            else error.exit_code
            if isinstance(error, _StageRejected)
            else 3
        )
        reason = error.reason if isinstance(error, _StageRejected) else type(error).__name__
        draft = PipelineFailure(
            created_at=datetime.now(UTC),
            workspace=ledger_link,
            failed_stage=stage,
            reason_code=reason,
            exit_code=code,
            completed_artifacts=tuple(completed),
            artifact_digest=EMPTY_DIGEST,
        )
        failure = draft.model_copy(update={"artifact_digest": digest_json_artifact(draft)})
        write_immutable(output / "failure.json", canonical_json_bytes(failure) + b"\n")
        raise PipelineExecutionError(
            stage, code, (output / "failure.json").relative_to(source).as_posix()
        ) from error


def _audit_manifest(manifest: PipelineManifest, *, source: Path, output: Path) -> None:
    if (
        manifest.workspace.ref
        != (output / "workspace_manifest.json").relative_to(source).as_posix()
        or manifest.runtime_ref != (output / "w").relative_to(source).as_posix()
    ):
        raise ArtifactIntegrityError("Pipeline manifest namespace/location mismatch")
    ledger = _load_model(output / "workspace_manifest.json", WorkspaceManifest)
    if (
        ledger.artifact_digest != manifest.workspace.artifact_digest
        or ledger.scenario_ref != manifest.scenario_ref
        or ledger.scenario_digest != manifest.scenario_digest
        or ledger.runtime_ref != manifest.runtime_ref
    ):
        raise ArtifactIntegrityError("Pipeline workspace/scenario binding mismatch")
    runtime = verify_workspace(ledger, cwd=source)
    scenario = load_scenario(source / ledger.scenario_ref)
    protocol, split, _ = verify_protocol(scenario.protocol_ref, cwd=runtime)
    _, _, samples, requests, _ = scenario_inputs(scenario, cwd=runtime)
    if (
        manifest.scenario_id != scenario.scenario_id
        or manifest.protocol_digest != protocol.artifact_digest
        or manifest.split_digest != split.artifact_digest
        or manifest.code_file_digests != _code_bindings()
        or manifest.code_digest != digest_bytes(canonical_json_bytes(manifest.code_file_digests))
        or manifest.environment != _environment()
    ):
        raise ArtifactIntegrityError("Pipeline runtime/protocol provenance changed; keep history")
    if {g.guard_id for g in manifest.groups} != {g.guard_id for g in scenario.guards}:
        raise ArtifactIntegrityError("Pipeline Guard membership mismatch")
    fits = {}
    for phase, link in (("initial", manifest.initial_fit), ("refined", manifest.refined_fit)):
        path, fit = _linked(link, FitManifest, source, runtime)
        if path != runtime / f"artifacts/fitted/{phase}/fit-manifest.json" or fit.phase != phase:
            raise ArtifactIntegrityError("Pipeline fitted phase mismatch")
        fits[phase] = fit
    by_guard = {}
    for group in manifest.groups:
        gate_path = _path(Path(group.gate.ref), source)
        if not gate_path.is_relative_to(runtime):
            raise ArtifactIntegrityError("Pipeline Gate reference escapes runtime")
        gate = verify_gate(gate_path, cwd=runtime)
        selector = next(g for g in scenario.guards if g.guard_id == group.guard_id)
        if (
            gate.artifact_digest != group.gate.artifact_digest
            or gate.status != "verified"
            or gate.request_ref != selector.request_ref
            or gate.request_id != requests[group.guard_id].request_id
            or group.evidence.ref != (runtime / gate.evidence_ref).relative_to(source).as_posix()
            or group.evidence.artifact_digest != gate.evidence_digest
        ):
            raise ArtifactIntegrityError("Pipeline Gate/Evidence binding mismatch")
        guard_path = _path(Path(group.guard.ref), source)
        guard = verify_guard(guard_path, cwd=runtime)
        if (
            guard_path != runtime / f"artifacts/guards/{group.guard_id}/guard.json"
            or guard.guard_id != group.guard_id
            or guard.artifact_digest != group.guard.artifact_digest
            or guard.source_evidence_ref != gate.evidence_ref
            or guard.source_evidence_digest != gate.evidence_digest
        ):
            raise ArtifactIntegrityError("Pipeline compiler did not consume its verified Evidence")
        _raw_run(
            guard.validation_run, runtime=runtime, cases=tuple(case.case_id for case in guard.cases)
        )
        by_guard[group.guard_id] = guard
        for phase in ("initial", "refined"):
            scope_link = getattr(group, phase + "_scope")
            learning_link = getattr(group, phase + "_learning")
            fitted_group = next(g for g in fits[phase].groups if g.guard_id == group.guard_id)
            if (
                scope_link.ref != (runtime / fitted_group.scope_ref).relative_to(source).as_posix()
                or scope_link.artifact_digest != fitted_group.scope_digest
                or learning_link.ref
                != (runtime / fitted_group.learning_ref).relative_to(source).as_posix()
                or learning_link.artifact_digest != fitted_group.learning_digest
            ):
                raise ArtifactIntegrityError("Pipeline Scope/learning references differ from fit")
            verify_scope_binding(
                _path(Path(scope_link.ref), source),
                guard_path,
                cwd=runtime,
                protocol_path=Path(scenario.protocol_ref),
                fit_manifest_path=runtime / f"artifacts/fitted/{phase}/fit-manifest.json",
            )
    expected = {
        (g.guard_id, sample_id) for g in scenario.guards for sample_id in g.replay_sample_ids
    }
    if {(row.guard_id, row.sample_id) for row in manifest.replays} != expected:
        raise ArtifactIntegrityError("Pipeline replay membership differs from scenario")
    accepted = True
    for row in manifest.replays:
        path, result = _linked(row.replay, ReplayResult, source, runtime)
        result = verify_replay(path, cwd=runtime)
        sample = samples[row.sample_id]
        group = next(g for g in manifest.groups if g.guard_id == row.guard_id)
        if (
            row != _row(sample, result, runtime, source)
            or result.guard_id != row.guard_id
            or result.guard_digest != group.guard.artifact_digest
            or result.scope_ref
            != (runtime / f"artifacts/fitted/refined/{row.guard_id}.json")
            .relative_to(runtime)
            .as_posix()
            or result.scope_digest != group.refined_scope.artifact_digest
            or result.fit_manifest_digest != fits["refined"].artifact_digest
            or (result.target.module, result.target.symbol)
            != (sample.target.module, sample.target.symbol)
            or result.declared_contract_ref != sample.contract_ref
        ):
            raise ArtifactIntegrityError("Pipeline replay summary/target/source mismatch")
        if result.run:
            _raw_run(
                result.run,
                runtime=runtime,
                cases=tuple(case.case_id for case in by_guard[row.guard_id].cases),
            )
        accepted &= _accepted(sample, result)
    if accepted != manifest.accepted:
        raise ArtifactIntegrityError("Pipeline acceptance contradicts its actual replay rows")


def verify_pipeline(path: str | Path, *, cwd: str | Path) -> PipelineManifest:
    source = Path(cwd).resolve(strict=True)
    path = _path(Path(path), source)
    if path.name != "run_manifest.json":
        raise ArtifactIntegrityError("Pipeline completion marker must be run_manifest.json")
    manifest = _load_model(path, PipelineManifest)
    _audit_manifest(manifest, source=source, output=path.parent)
    return manifest
