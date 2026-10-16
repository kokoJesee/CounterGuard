"""Command-line entry point for the EvidenceGuard MVP."""

import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from evidenceguard import __version__
from evidenceguard.change_analysis import inspect_repository, render_inspection
from evidenceguard.compiler import CompileRequest, compile_guard, run_guard, verify_guard
from evidenceguard.demo import run_demo, verify_demo
from evidenceguard.diagnostics import public_diagnostic
from evidenceguard.errors import (
    ArtifactIntegrityError,
    GuardSelfCheckError,
    InsufficientScopeEvidence,
    InvalidEvidenceError,
    RunnerDependencyError,
)
from evidenceguard.evaluation import evaluate_methods, verify_evaluation
from evidenceguard.evidence import (
    CaptureRequest,
    capture_evidence,
    evidence_exit_code,
    inventory_evidence,
    verify_evidence,
)
from evidenceguard.features import audit_features
from evidenceguard.models import Evidence, RunOutcome, RunRecord
from evidenceguard.pipeline import PipelineExecutionError, run_pipeline, verify_pipeline
from evidenceguard.protocol import run_train_baselines, verify_protocol
from evidenceguard.registry_cli import app as registry_app
from evidenceguard.replay import (
    ReplayRequest,
    replay_exit_code,
    replay_guard,
    replay_train_benchmark,
    verify_replay,
)
from evidenceguard.report import OutputFormat, command_report, render_report
from evidenceguard.scope import fit_scopes
from evidenceguard.verification_gate import capture_candidate, gate_exit_code, verify_gate

app = typer.Typer(no_args_is_help=True, help="Scope-aware regression guard tooling.")
app.add_typer(registry_app, name="registry")
evidence_app = typer.Typer(no_args_is_help=True, help="Verify stored Evidence artifacts.")
app.add_typer(evidence_app, name="evidence")
guard_app = typer.Typer(no_args_is_help=True, help="Audit and directly smoke-test Guard assets.")
app.add_typer(guard_app, name="guard")
experiment_app = typer.Typer(no_args_is_help=True, help="Audit frozen experiment protocols.")
app.add_typer(experiment_app, name="experiment")
benchmark_app = typer.Typer(no_args_is_help=True, help="Execute frozen benchmark methods.")
app.add_typer(benchmark_app, name="benchmark")
features_app = typer.Typer(no_args_is_help=True, help="Extract and audit static target features.")
app.add_typer(features_app, name="features")
scope_app = typer.Typer(
    no_args_is_help=True, help="Fit scopes from verified training features only."
)
app.add_typer(scope_app, name="scope")
replay_app = typer.Typer(no_args_is_help=True, help="Run or audit a scoped replay.")
app.add_typer(replay_app, name="replay")
verification_app = typer.Typer(no_args_is_help=True, help="Audit independent candidate Gates.")
app.add_typer(verification_app, name="verification")
pipeline_app = typer.Typer(no_args_is_help=True, help="Run or audit the offline MVP pipeline.")
app.add_typer(pipeline_app, name="pipeline")


@app.command("inspect")
def inspect_command(
    repo: Annotated[Path, typer.Option(help="Explicit repository root; committed data only.")],
    base: Annotated[str, typer.Option(help="Base commit, branch/tag or HEAD ancestry.")],
    head: Annotated[str, typer.Option(help="Head commit, branch/tag or HEAD ancestry.")],
    config: Annotated[Path, typer.Option(help="Explicit project-config.v1 JSON-compatible YAML.")],
    format: Annotated[
        OutputFormat, typer.Option(help="Presentation of the same inspection facts.")
    ] = OutputFormat.TEXT,
) -> None:
    """Inspect explicit file mappings without executing repository code."""
    try:
        report = inspect_repository(repo, base, head, config)
    except ValueError as error:
        _error(str(error), 2)
    except OSError:
        _error("Project configuration is unavailable", 2)
    typer.echo(render_inspection(report, format.value), nl=False)
    code = {"ready": 0, "unknown": 4, "rejected": 5}[report.status]
    if code:
        raise typer.Exit(code)


@pipeline_app.command("run")
def pipeline_run(
    scenario: Annotated[Path, typer.Option(help="JSON-compatible YAML scenario.")],
    workspace: Annotated[Path, typer.Option(help="New immutable output directory below cwd.")],
    cwd: Annotated[Path, typer.Option(help="Trusted source workspace.")] = Path("."),
) -> None:
    try:
        manifest = run_pipeline(scenario, cwd=cwd, workspace=workspace)
    except PipelineExecutionError as error:
        _error(str(error), error.exit_code)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except RunnerDependencyError as error:
        _error(str(error), 3)
    except OSError:
        _error("Pipeline input or output is unavailable", 3)
    typer.echo(manifest.model_dump_json(indent=2))
    if not manifest.accepted:
        raise typer.Exit(1)


@pipeline_app.command("verify")
def pipeline_verify(
    path: Annotated[Path, typer.Argument(help="Completed run_manifest.json.")],
    cwd: Annotated[Path, typer.Option(help="Trusted source workspace.")] = Path("."),
) -> None:
    try:
        manifest = verify_pipeline(path, cwd=cwd)
    except RunnerDependencyError as error:
        _error(str(error), 3)
    except (ArtifactIntegrityError, OSError, ValueError) as error:
        _error(str(error), 5)
    typer.echo(manifest.model_dump_json(indent=2))
    if not manifest.accepted:
        raise typer.Exit(1)


@verification_app.command("verify")
def verification_verify(
    path: Annotated[Path, typer.Argument(help="Completed candidate gate.json.")],
    cwd: Annotated[Path, typer.Option(help="Trusted source workspace.")] = Path("."),
) -> None:
    try:
        result = verify_gate(path, cwd=cwd)
    except (ArtifactIntegrityError, OSError, ValueError) as error:
        _error(str(error), 5)
    typer.echo(result.model_dump_json(indent=2))
    code = gate_exit_code(result, cwd=cwd)
    if code:
        raise typer.Exit(code)


@app.callback()
def main() -> None:
    """Run EvidenceGuard commands."""


@app.command()
def version() -> None:
    """Print the installed EvidenceGuard version."""
    typer.echo(__version__)


@app.command()
def demo(
    workspace: Annotated[Path, typer.Option(help="New immutable offline Demo workspace.")] = Path(
        "artifacts/demo-run"
    ),
    scenario: Annotated[Path, typer.Option(help="JSON-compatible YAML scenario.")] = Path(
        "examples/demo/mvp.yaml"
    ),
    cwd: Annotated[Path, typer.Option(help="Trusted source workspace.")] = Path("."),
    format: Annotated[OutputFormat, typer.Option(help="Render the same verified JSON facts.")] = (
        OutputFormat.TEXT
    ),
    verify_only: Annotated[
        bool, typer.Option(help="Read-only audit; never start the Pipeline.")
    ] = (False),
) -> None:
    """Run the recorded offline Demo or audit its completed report."""
    try:
        result = (
            verify_demo(workspace / "report.json", cwd=cwd)
            if verify_only
            else run_demo(scenario, cwd=cwd, workspace=workspace)
        )
    except PipelineExecutionError as error:
        _error(str(error), error.exit_code)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except RunnerDependencyError as error:
        _error(str(error), 3)
    except OSError:
        _error("Demo input or output is unavailable", 3)
    typer.echo(render_report(result, format), nl=False)
    if not result.report.payload["accepted"]:
        raise typer.Exit(1)


@replay_app.command("run")
def replay_run(
    guard: Annotated[Path, typer.Option(help="Guard JSON.")],
    scope: Annotated[Path, typer.Option(help="Bound Scope JSON.")],
    target: Annotated[str, typer.Option(help="New target module:symbol.")],
    contract: Annotated[
        Path | None, typer.Option(help="Declared target contract; missing yields unknown.")
    ] = None,
    cwd: Annotated[Path, typer.Option(help="Trusted workspace.")] = Path("."),
    artifact_root: Annotated[Path, typer.Option(help="Replay output below cwd.")] = Path(
        "artifacts"
    ),
    timeout: Annotated[float, typer.Option(help="Execution timeout in seconds.")] = 30.0,
    format: Annotated[OutputFormat | None, typer.Option(help="Versioned report format.")] = None,
) -> None:
    try:
        result = replay_guard(
            ReplayRequest(
                guard, scope, target, contract, cwd, artifact_root, timeout_seconds=timeout
            )
        )
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"Replay error: {error}", 3)
    _emit_report("replay", result, format)
    code = replay_exit_code(result)
    if code:
        raise typer.Exit(code)


@replay_app.command("verify")
def replay_verify(
    path: Annotated[Path, typer.Argument(help="Replay result.json.")],
    cwd: Annotated[Path, typer.Option(help="Source workspace.")] = Path("."),
) -> None:
    try:
        result = verify_replay(path, cwd=cwd)
    except (ArtifactIntegrityError, OSError) as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    typer.echo(result.model_dump_json(indent=2))


@benchmark_app.command("replay")
def benchmark_replay(
    protocol: Annotated[Path, typer.Option(help="Frozen protocol JSON.")],
    phase: Annotated[str, typer.Option(help="initial or refined.")],
    split: Annotated[str, typer.Option(help="D8 accepts train only.")] = "train",
    fitted: Annotated[Path | None, typer.Option(help="Fitted bundle directory.")] = None,
    cwd: Annotated[Path, typer.Option(help="Trusted source workspace.")] = Path("."),
    artifact_root: Annotated[Path, typer.Option(help="Run reports below cwd.")] = Path("artifacts"),
) -> None:
    try:
        directory = fitted or artifact_root / f"experiments/scope-v1/fitted/learning-v2/{phase}"
        report = replay_train_benchmark(
            protocol,
            phase=phase,
            fitted=directory,
            cwd=cwd,
            artifact_root=artifact_root,
            split=split,
        )
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"Benchmark replay error: {error}", 3)
    typer.echo(json.dumps(report, indent=2))
    counts = report["counts"]
    code = (
        5
        if counts["stale"]
        else 3
        if any(counts[key] for key in ("collection_error", "execution_error", "timeout"))
        else 4
        if counts["skipped_unknown"]
        else 1
        if counts["violation"]
        else 0
    )
    if code:
        raise typer.Exit(code)


@app.command("learn")
@scope_app.command("learn")
def scope_learn(
    protocol: Annotated[Path, typer.Option(help="Frozen protocol JSON.")],
    phase: Annotated[str, typer.Option(help="initial or refined; never holdout.")],
    output: Annotated[Path, typer.Option(help="Immutable fitted scope directory below cwd.")],
    cwd: Annotated[Path, typer.Option(help="Trusted source workspace.")] = Path("."),
    format: Annotated[OutputFormat | None, typer.Option(help="Versioned report format.")] = None,
) -> None:
    try:
        manifest = fit_scopes(protocol, phase=phase, output=output, cwd=cwd)
    except InsufficientScopeEvidence as error:
        _emit_report(
            "learn",
            {"status": "refused", "reason_code": error.reason_code, "detail": str(error)},
            format,
        )
        raise typer.Exit(4) from error
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except (ValueError, TypeError) as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"Scope fitting error: {error}", 3)
    _emit_report("learn", manifest, format)


@features_app.command("audit")
def features_audit(
    benchmark_root: Annotated[Path, typer.Option(help="Separate train/holdout sample files.")],
    output: Annotated[Path, typer.Option(help="JSON audit report below cwd.")],
    cwd: Annotated[Path, typer.Option(help="Source workspace.")] = Path("."),
    artifact_root: Annotated[
        Path, typer.Option(help="Extracted feature records below cwd.")
    ] = Path("artifacts"),
    context: Annotated[Path | None, typer.Option(help="Reviewed module context manifest.")] = None,
) -> None:
    """Compare every feature with manual annotations and retain mismatches/errors."""
    try:
        report = audit_features(
            benchmark_root=benchmark_root,
            output=output,
            cwd=cwd,
            artifact_root=artifact_root,
            module_context_path=context,
        )
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"Feature audit error: {error}", 3)
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    codes = {entry["exit_code"] for entry in report["entries"]}
    for code in (5, 3, 2, 1):
        if code in codes:
            raise typer.Exit(code)


@app.command()
def capture(
    evidence_id: Annotated[str | None, typer.Option(help="Stable evd_ identity.")] = None,
    contract: Annotated[
        Path | None, typer.Option(help="Repository-relative contract JSON.")
    ] = None,
    test: Annotated[
        Path | None, typer.Option(help="Repository-relative pytest contract test.")
    ] = None,
    buggy_target: Annotated[str | None, typer.Option(help="Buggy module:symbol.")] = None,
    fixed_target: Annotated[str | None, typer.Option(help="Fixed module:symbol.")] = None,
    artifact_root: Annotated[Path, typer.Option(help="Output directory below cwd.")] = Path(
        "artifacts"
    ),
    cwd: Annotated[Path, typer.Option(help="Trusted project workspace.")] = Path("."),
    timeout: Annotated[float, typer.Option(help="Per-run timeout in seconds.")] = 30.0,
    supersedes: Annotated[
        Path | None, typer.Option(help="Predecessor Evidence; derives the next revision.")
    ] = None,
    reason: Annotated[
        str | None, typer.Option(help="Why this recapture replaces its predecessor.")
    ] = None,
    request: Annotated[
        Path | None, typer.Option(help="Independent verification request JSON.")
    ] = None,
    agent_source: Annotated[str | None, typer.Option(help="D10 provider: recorded.")] = None,
    workspace: Annotated[Path | None, typer.Option(help="Candidate/Gate output below cwd.")] = None,
    format: Annotated[OutputFormat | None, typer.Option(help="Versioned report format.")] = None,
) -> None:
    """Capture a buggy failure and fixed pass as auditable JSON Evidence."""
    try:
        if request is not None:
            if (
                any(
                    value is not None
                    for value in (
                        evidence_id,
                        contract,
                        test,
                        buggy_target,
                        fixed_target,
                        supersedes,
                        reason,
                    )
                )
                or artifact_root != Path("artifacts")
                or timeout != 30.0
            ):
                raise ValueError("Do not mix request mode with direct capture options")
            if agent_source != "recorded" or workspace is None:
                raise ValueError("Request mode requires --agent-source recorded and --workspace")
            result = capture_candidate(
                request, cwd=cwd, workspace=workspace, agent_source=agent_source
            )
            _emit_report("capture", result, format)
            code = gate_exit_code(result, cwd=cwd)
            if code:
                raise typer.Exit(code)
            return
        if agent_source is not None or workspace is not None:
            raise ValueError("Agent options require --request")
        if any(
            value is None for value in (evidence_id, contract, test, buggy_target, fixed_target)
        ):
            raise ValueError("Direct capture requires evidence-id, contract, test and both targets")
        evidence = capture_evidence(
            CaptureRequest(
                evidence_id=evidence_id,
                contract_path=contract,
                test_path=test,
                buggy_target=buggy_target,
                fixed_target=fixed_target,
                cwd=cwd,
                artifact_root=artifact_root,
                timeout_seconds=timeout,
                tool_version=__version__,
                supersedes_path=supersedes,
                recapture_reason=reason,
            )
        )
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"capture execution error: {error}", 3)
    _emit_evidence(evidence, format)


@evidence_app.command("inventory")
def evidence_inventory(
    cwd: Annotated[Path, typer.Option(help="Workspace used for full verification.")] = Path("."),
    artifact_root: Annotated[Path, typer.Option(help="Artifact directory to inspect.")] = Path(
        "artifacts"
    ),
) -> None:
    """List verification and supersession states; exit 0 means inspection completed."""
    try:
        report = inventory_evidence(cwd=cwd, artifact_root=artifact_root)
    except (ValueError, OSError) as error:
        _error(str(error), 2)
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))


@experiment_app.command("verify")
def experiment_verify(
    protocol: Annotated[Path | None, typer.Option(help="Frozen experiment protocol JSON.")] = None,
    run: Annotated[Path | None, typer.Option(help="Immutable D9 evaluation directory.")] = None,
    cwd: Annotated[Path, typer.Option(help="Source workspace.")] = Path("."),
) -> None:
    """Audit protocol, split membership, data pins, and complete Guard provenance."""
    try:
        if (protocol is None) == (run is None):
            raise ValueError("Specify exactly one of --protocol and --run")
        if run is not None:
            report = verify_evaluation(run, cwd=cwd)
            typer.echo(report.model_dump_json(indent=2))
            return
        spec, manifest, guards = verify_protocol(protocol, cwd=cwd)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"Protocol verification error: {error}", 5)
    typer.echo(
        json.dumps(
            {
                "protocol_id": spec.protocol_id,
                "protocol_digest": spec.artifact_digest,
                "split_digest": manifest.artifact_digest,
                "guard_ids": sorted(guards),
                "train_count": sum(
                    len(p.initial + p.refinement_additions) for p in manifest.phases.values()
                ),
                "holdout_count": sum(len(p.holdout) for p in manifest.phases.values()),
                "verified": True,
            },
            indent=2,
        )
    )


@app.command("evaluate")
@experiment_app.command("evaluate")
def experiment_evaluate(
    protocol: Annotated[Path, typer.Option(help="Frozen scope_v1 protocol JSON.")],
    fitted: Annotated[Path, typer.Option(help="Directory containing initial/refined fit bundles.")],
    output: Annotated[Path, typer.Option(help="New immutable evaluation directory.")],
    split: Annotated[str, typer.Option(help="D9 accepts holdout only.")] = "holdout",
    cwd: Annotated[Path, typer.Option(help="Trusted source workspace.")] = Path("."),
    timeout: Annotated[float, typer.Option(help="Per-run timeout in seconds.")] = 30.0,
    format: Annotated[OutputFormat | None, typer.Option(help="Versioned report format.")] = None,
) -> None:
    try:
        report = evaluate_methods(
            protocol,
            fitted=fitted,
            output=output,
            cwd=cwd,
            split=split,
            timeout_seconds=timeout,
        )
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"Evaluation execution error: {error}", 3)
    _emit_report("evaluate", report, format)
    if not report.accepted:
        raise typer.Exit(1)


@benchmark_app.command("baselines")
def benchmark_baselines(
    protocol: Annotated[Path, typer.Option(help="Frozen experiment protocol JSON.")],
    split: Annotated[str, typer.Option(help="D5 accepts train only.")] = "train",
    cwd: Annotated[Path, typer.Option(help="Trusted source workspace.")] = Path("."),
    artifact_root: Annotated[Path, typer.Option(help="Report output below cwd.")] = Path(
        "artifacts"
    ),
) -> None:
    """Predict applicability and actually run each applicable Guard on training rows."""
    try:
        report = run_train_baselines(protocol, cwd=cwd, artifact_root=artifact_root, split=split)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"Baseline execution error: {error}", 3)
    typer.echo(json.dumps(report, indent=2))
    if report["infrastructure_errors"]:
        raise typer.Exit(3)


@evidence_app.command("verify")
def evidence_verify(
    path: Annotated[Path, typer.Argument(help="Stored evidence.json to verify.")],
    cwd: Annotated[Path, typer.Option(help="Workspace used for artifact references.")] = Path("."),
) -> None:
    """Verify the schema, self digest, and all referenced input and log digests."""
    try:
        evidence = verify_evidence(path, cwd=cwd)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"verification execution error: {error}", 3)
    _emit_evidence(evidence)


@app.command("compile")
def compile_command(
    guard_id: Annotated[str, typer.Option(help="Independent grd_ identity.")],
    evidence: Annotated[Path, typer.Option(help="Verified source Evidence JSON.")],
    cwd: Annotated[Path, typer.Option(help="Trusted project workspace.")] = Path("."),
    artifact_root: Annotated[Path, typer.Option(help="Output below cwd.")] = Path("artifacts"),
    format: Annotated[OutputFormat | None, typer.Option(help="Versioned report format.")] = None,
) -> None:
    """Compile minimal regression assertions and validate them on the fixed target."""
    try:
        guard = compile_guard(CompileRequest(guard_id, evidence, cwd, artifact_root))
    except GuardSelfCheckError as error:
        typer.echo(str(error), err=True)
        _emit_report("compile", error.run, format)
        raise typer.Exit(3) from error
    except InvalidEvidenceError as error:
        _error(str(error), 1)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"compile execution error: {error}", 3)
    _emit_report("compile", guard, format)


@guard_app.command("verify")
def guard_verify(
    path: Annotated[Path, typer.Argument(help="Guard JSON to audit.")],
    cwd: Annotated[Path, typer.Option(help="Source workspace.")] = Path("."),
) -> None:
    """Verify Guard content, source Evidence, and fixed-target self-check logs."""
    try:
        guard = verify_guard(path, cwd=cwd)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"Guard verification error: {error}", 3)
    typer.echo(guard.model_dump_json(indent=2))


@guard_app.command("run")
def guard_run(
    path: Annotated[Path, typer.Argument(help="Guard JSON to execute directly.")],
    target: Annotated[str, typer.Option(help="New target module:symbol.")],
    cwd: Annotated[Path, typer.Option(help="Trusted project workspace.")] = Path("."),
    artifact_root: Annotated[Path, typer.Option(help="Run output below cwd.")] = Path("artifacts"),
    timeout: Annotated[float, typer.Option(help="Run timeout in seconds.")] = 30.0,
) -> None:
    """Direct smoke replay; this command does not decide Scope applicability."""
    try:
        run = run_guard(path, target, cwd=cwd, artifact_root=artifact_root, timeout_seconds=timeout)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"Guard execution error: {error}", 3)
    _emit_run(run)


def _emit_run(run: RunRecord) -> None:
    typer.echo(run.model_dump_json(indent=2))
    if run.outcome is RunOutcome.TEST_FAILED:
        raise typer.Exit(1)
    if run.outcome is not RunOutcome.PASSED:
        raise typer.Exit(3)


def _emit_evidence(evidence: Evidence, format: OutputFormat | None = None) -> None:
    _emit_report("capture", evidence, format)
    code = evidence_exit_code(evidence)
    if code:
        raise typer.Exit(code)


def _emit_report(operation: str, record, format: OutputFormat | None) -> None:
    payload = record if isinstance(record, dict) else record.model_dump(mode="json")
    if format is None:
        # Pre-D12 clients keep the original artifact shape and its original digest semantics.
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(render_report(command_report(operation, payload), format), nl=False)


def _error(message: str, exit_code: int) -> NoReturn:
    typer.echo(f"Error: {public_diagnostic(message)}", err=True)
    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
