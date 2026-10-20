"""Command-line entry point for the CounterGuard MVP."""

import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from counterguard import __version__
from counterguard.change_analysis import inspect_repository, render_inspection
from counterguard.compiler import CompileRequest, compile_guard, run_guard, verify_guard
from counterguard.demo import run_demo, verify_demo
from counterguard.diagnostics import public_diagnostic
from counterguard.digests import canonical_json_bytes
from counterguard.errors import (
    ArtifactIntegrityError,
    GuardSelfCheckError,
    InsufficientScopeEvidence,
    InvalidEvidenceError,
    RunnerDependencyError,
)
from counterguard.evaluation import evaluate_methods, verify_evaluation
from counterguard.evidence import (
    CaptureRequest,
    capture_evidence,
    evidence_exit_code,
    inventory_evidence,
    verify_evidence,
)
from counterguard.features import audit_features
from counterguard.models import Evidence, RunOutcome, RunRecord
from counterguard.pipeline import PipelineExecutionError, run_pipeline, verify_pipeline
from counterguard.preflight import preflight_repository
from counterguard.protocol import run_train_baselines, verify_protocol
from counterguard.registry_cli import app as registry_app
from counterguard.replay import (
    ReplayRequest,
    replay_exit_code,
    replay_guard,
    replay_train_benchmark,
    verify_replay,
)
from counterguard.report import OutputFormat, command_report, render_report
from counterguard.runner_cli import app as runner_app
from counterguard.scope import fit_scopes
from counterguard.verification_gate import capture_candidate, gate_exit_code, verify_gate

app = typer.Typer(no_args_is_help=True, help="Scope-aware regression guard tooling.")
app.add_typer(registry_app, name="registry")
app.add_typer(runner_app, name="runner")
contract_app = typer.Typer(no_args_is_help=True, help="Prepare review-only contract proposals.")
app.add_typer(contract_app, name="contract")
bootstrap_app = typer.Typer(
    no_args_is_help=True, help="Review sources and bootstrap isolated literal Guards."
)
app.add_typer(bootstrap_app, name="bootstrap")
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


@contract_app.command("draft")
def contract_draft_command(
    repo: Annotated[Path, typer.Option(help="Read committed data only; never imported.")],
    revision: Annotated[str, typer.Option(help="Commit/ref containing the test.")],
    test_ref: Annotated[str, typer.Option(help="Committed test path, relative to repo.")],
    test_function: Annotated[str, typer.Option(help="One top-level test_* function.")],
    target: Annotated[str, typer.Option(help="Declared module:symbol; syntax only.")],
    output: Annotated[Path, typer.Option(help="New proposal directory outside target repo.")],
) -> None:
    """Statically extract literal assertions; proposals never authorize execution."""
    from counterguard.contract_draft import draft_contract
    from counterguard.repository import RepositoryProblem

    try:
        proposal = draft_contract(
            repo,
            revision,
            test_ref=test_ref,
            test_function=test_function,
            target=target,
            output=output,
        )
    except RepositoryProblem as error:
        _error("Committed repository data unavailable: " + error.code, 5 if error.rejected else 4)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        _error(str(error), 2)
    typer.echo(canonical_json_bytes(proposal).decode())
    if proposal.status != "draft_ready":
        raise typer.Exit(4)


@contract_app.command("prepare")
def contract_prepare_command(
    repo: Annotated[Path, typer.Option(help="Read committed objects only.")],
    buggy: Annotated[str, typer.Option(help="Full buggy commit SHA.")],
    fixed: Annotated[str, typer.Option(help="Full direct-child fix SHA.")],
    contract_id: Annotated[str, typer.Option(help="New semantic contract identity.")],
    target: Annotated[str, typer.Option(help="Declared module:symbol.")],
    import_root: Annotated[str, typer.Option(help="Explicit . or src.")],
    test_ref: Annotated[str, typer.Option(help="Committed fixed regression test.")],
    test_function: Annotated[str, typer.Option(help="One top-level test_* function.")],
    output: Annotated[Path, typer.Option(help="New preparation directory outside target repo.")],
    profile: Annotated[
        str, typer.Option(help="existing or explicit static-reexport-v2.")
    ] = "existing",
) -> None:
    """Prepare a versioned literal contract for owner review; never execute."""
    from counterguard.bootstrap_binding import prepare_contract
    from counterguard.repository import RepositoryProblem

    try:
        value = prepare_contract(
            repo,
            buggy=buggy,
            fixed=fixed,
            contract_id=contract_id,
            target=target,
            import_root=import_root,
            test_ref=test_ref,
            test_function=test_function,
            output=output,
            profile=profile,
        )
    except RepositoryProblem as error:
        _error("Committed repository data unavailable: " + error.code, 5 if error.rejected else 4)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        _error(str(error), 2)
    typer.echo(canonical_json_bytes(value).decode())
    raise typer.Exit(4)


@bootstrap_app.command("bind")
def bootstrap_bind_command(
    repo: Annotated[Path, typer.Option(help="Read committed objects only.")],
    head: Annotated[str, typer.Option(help="Full owner assertion-head SHA.")],
    contract_ref: Annotated[str, typer.Option(help="Contract path in head, never external input.")],
    output: Annotated[Path, typer.Option(help="New binding directory outside target repo.")],
) -> None:
    """Rebuild B/F/H history, contract cases and source closures without executing."""
    from counterguard.bootstrap_binding import bind_contract
    from counterguard.repository import RepositoryProblem

    try:
        value = bind_contract(repo, head, contract_ref, output=output)
    except RepositoryProblem as error:
        _error("Committed repository data unavailable: " + error.code, 5 if error.rejected else 4)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        _error(str(error), 2)
    typer.echo(canonical_json_bytes(value).decode())
    if value["binding_status"] != "sources_verified":
        raise typer.Exit(5 if value["binding_status"] == "rejected" else 4)
    if value["capture_input_status"] != "review_required":
        raise typer.Exit(4)


@bootstrap_app.command("verify-binding")
def bootstrap_verify_binding_command(
    path: Annotated[Path, typer.Argument(help="Existing binding.json to independently rebuild.")],
    repo: Annotated[Path, typer.Option(help="Repository containing the pinned Git objects.")],
) -> None:
    """Compare a source binding with actual committed facts, not just its self hash."""
    from counterguard.bootstrap_binding import verify_binding
    from counterguard.repository import RepositoryProblem

    try:
        value = verify_binding(repo, path)
    except RepositoryProblem as error:
        _error("Committed repository data unavailable: " + error.code, 5 if error.rejected else 4)
    except (ArtifactIntegrityError, OSError, ValueError, UnicodeError, RecursionError) as error:
        _error(str(error), 5)
    typer.echo(
        canonical_json_bytes(
            {
                "source_binding_verified": True,
                "artifact_digest": value["artifact_digest"],
                "capture_input_status": value["capture_input_status"],
                "execution_allowed": False,
            }
        ).decode()
    )
    if value["capture_input_status"] != "review_required":
        raise typer.Exit(4)


@bootstrap_app.command("capture")
def bootstrap_capture_command(
    repo: Annotated[
        Path, typer.Option(help="Committed source repository; never executed locally.")
    ],
    binding: Annotated[Path, typer.Option(help="Current independently verified binding.json.")],
    runner_id: Annotated[str, typer.Option(help="Reviewed root-pytest8 runner ID.")],
    evidence_id: Annotated[str, typer.Option(help="New evd_ identity; do not reuse history.")],
    review_reason: Annotated[
        str, typer.Option(help="Explicit review of sources, resources and oracles.")
    ],
    output: Annotated[
        Path, typer.Option(help="New immutable capture directory outside target repo.")
    ],
    timeout: Annotated[
        float, typer.Option(help="Per-container pytest deadline, at most 30 seconds.")
    ] = 10.0,
) -> None:
    """Capture B/F through Docker only; unresolved inputs have no override or local fallback."""
    from counterguard.repository import RepositoryProblem
    from counterguard.standalone_capture import capture_standalone, standalone_capture_exit_code

    try:
        value = capture_standalone(
            repo,
            binding,
            runner_id=runner_id,
            evidence_id=evidence_id,
            review_reason=review_reason,
            output=output,
            timeout=timeout,
        )
    except RepositoryProblem as error:
        _error("Committed data unavailable: " + error.code, 5 if error.rejected else 4)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        _error(str(error), 2)
    typer.echo(canonical_json_bytes(value).decode())
    code = standalone_capture_exit_code(value)
    if code:
        raise typer.Exit(code)


@bootstrap_app.command("verify-evidence")
def bootstrap_verify_evidence_command(
    path: Annotated[Path, typer.Argument(help="Existing standalone evidence.v4 JSON.")],
    repo: Annotated[Path, typer.Option(help="Source repository holding pinned B/F/H objects.")],
) -> None:
    """Independently rebuild provenance, authorization, raw JUnit and reproduction claims."""
    from counterguard.repository import RepositoryProblem
    from counterguard.standalone_capture import (
        standalone_capture_exit_code,
        verify_standalone_evidence,
    )

    try:
        value = verify_standalone_evidence(repo, path).model_dump(mode="json")
    except RepositoryProblem as error:
        _error("Committed data unavailable: " + error.code, 5 if error.rejected else 4)
    except (ArtifactIntegrityError, OSError, ValueError, UnicodeError, RecursionError) as error:
        _error(str(error), 5)
    typer.echo(canonical_json_bytes(value).decode())
    code = standalone_capture_exit_code(value)
    if code:
        raise typer.Exit(code)


@bootstrap_app.command("compile")
def bootstrap_compile_command(
    repo: Annotated[Path, typer.Option(help="Git repository containing B/F/H.")],
    evidence: Annotated[Path, typer.Option(help="Current reproduced evidence.v4.")],
    guard_id: Annotated[str, typer.Option(help="New semantic grd_ identity.")],
    review_reason: Annotated[
        str, typer.Option(help="Review of oracles, independence and exact snapshot Scope.")
    ],
    output: Annotated[Path, typer.Option(help="New immutable compilation directory.")],
) -> None:
    """Compile only failed cases and self-check B/F using the reviewed Docker runner."""
    from counterguard.repository import RepositoryProblem
    from counterguard.standalone_guard import compile_standalone_guard

    try:
        guard = compile_standalone_guard(
            repo, evidence, guard_id=guard_id, review_reason=review_reason, output=output
        )
    except InvalidEvidenceError as error:
        _error(str(error), 1)
    except GuardSelfCheckError as error:
        _error(
            str(error), 1 if error.run.outcome in {RunOutcome.PASSED, RunOutcome.TEST_FAILED} else 3
        )
    except RepositoryProblem as error:
        _error(error.code, 5 if error.rejected else 4)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except OSError as error:
        _error(str(error), 3)
    except (ValueError, UnicodeError, RecursionError) as error:
        _error(str(error), 2)
    typer.echo(canonical_json_bytes(guard).decode())


@bootstrap_app.command("verify-guard")
def bootstrap_verify_guard_command(
    path: Annotated[Path, typer.Argument(help="Existing guard.v3 JSON.")],
    repo: Annotated[Path, typer.Option(help="Original B/F/H Git repository.")],
) -> None:
    """Rebuild minimality, exact Scope, B/F authorization and raw self-check results."""
    from counterguard.repository import RepositoryProblem
    from counterguard.standalone_guard import verify_standalone_guard

    try:
        guard = verify_standalone_guard(repo, path)
    except RepositoryProblem as error:
        _error(error.code, 5 if error.rejected else 4)
    except (ArtifactIntegrityError, OSError, ValueError, UnicodeError, RecursionError) as error:
        _error(str(error), 5)
    typer.echo(canonical_json_bytes(guard).decode())


@bootstrap_app.command("plan")
def bootstrap_plan_command(
    repo: Annotated[Path, typer.Option(help="Read committed files; never import or execute.")],
    revision: Annotated[str, typer.Option(help="Commit/ref containing target and source test.")],
    target: Annotated[str, typer.Option(help="One declared module:symbol target.")],
    import_root: Annotated[str, typer.Option(help="Explicit . or src import root.")],
    test_ref: Annotated[str, typer.Option(help="Committed upstream test path.")],
    test_function: Annotated[str, typer.Option(help="Selected top-level test_* function.")],
    output: Annotated[Path, typer.Option(help="New review plan directory outside target repo.")],
    profile: Annotated[
        str, typer.Option(help="existing or explicit static-reexport-v2.")
    ] = "existing",
) -> None:
    """Separate target import closure from whole-repository test bootstrap requirements."""
    from counterguard.bootstrap_plan import plan_bootstrap
    from counterguard.repository import RepositoryProblem

    try:
        plan = plan_bootstrap(
            repo,
            revision,
            target=target,
            import_root=import_root,
            test_ref=test_ref,
            test_function=test_function,
            output=output,
            profile=profile,
        )
    except RepositoryProblem as error:
        _error("Committed repository data unavailable: " + error.code, 5 if error.rejected else 4)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        _error(str(error), 2)
    typer.echo(canonical_json_bytes(plan).decode())
    # Even a complete static plan needs review and unimplemented execution
    # capabilities. Exit zero must never be mistaken for generic admission.
    raise typer.Exit(4)


@bootstrap_app.command("inspect-target")
def bootstrap_inspect_target_command(
    repo: Annotated[Path, typer.Option(help="Read a complete committed tree only.")],
    revision: Annotated[str, typer.Option(help="Fixed comparison-target commit.")],
    target: Annotated[str, typer.Option(help="Public root module:symbol.")],
    import_root: Annotated[str, typer.Option(help="Explicit . or src.")],
    profile: Annotated[str, typer.Option(help="Explicit static-reexport-v2 only.")],
    output: Annotated[Path, typer.Option(help="New read-only inspection receipt directory.")],
) -> None:
    """Inspect a comparison target; no fictional source contract or execution."""
    from counterguard.repository import RepositoryProblem
    from counterguard.target_inspection import inspect_static_target

    try:
        value = inspect_static_target(
            repo,
            revision,
            target=target,
            import_root=import_root,
            profile=profile,
            output=output,
        )
    except RepositoryProblem as error:
        _error(error.code, 5 if error.rejected else 4)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        _error(str(error), 2)
    typer.echo(canonical_json_bytes(value).decode())
    raise typer.Exit(4)  # Review-required never means permission to execute.


@app.command("preflight")
def preflight_command(
    repo: Annotated[Path, typer.Option(help="Repository root; only committed files are read.")],
    revision: Annotated[str, typer.Option(help="Commit/ref to assess without imports or install.")],
    profile: Annotated[
        str, typer.Option(help="legacy or minimal-python static admission.")
    ] = "legacy",
    import_root: Annotated[str, typer.Option(help="Explicit . or src for minimal-python.")] = ".",
) -> None:
    """Statically check compatibility with the fixed Docker no-install profile."""
    if profile == "minimal-python":
        from counterguard.admission import admission_repository

        if import_root not in {".", "src"}:
            _error("Use --import-root . or src", 2)
        result = admission_repository(repo, revision, import_root=import_root)
    elif profile == "legacy" and import_root == ".":
        result = preflight_repository(repo, revision)
    else:
        _error("Use --profile legacy or --profile minimal-python --import-root .|src", 2)
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["status"] != "eligible_candidate":
        raise typer.Exit(5 if result["status"] == "rejected" else 4)


@app.command("verify")
def verify_command(
    repo: Annotated[
        Path, typer.Option(help="Committed target repository; never executed locally.")
    ],
    base: Annotated[str, typer.Option()],
    head: Annotated[str, typer.Option()],
    config: Annotated[Path, typer.Option(help="Explicit project configuration.")],
    registry: Annotated[Path, typer.Option(help="Verified local Registry root.")],
    output: Annotated[Path, typer.Option(help="New report directory below cwd, outside repo.")],
    image: Annotated[
        str | None, typer.Option(help="Exact ID already present in runner list.")
    ] = None,
    runner_id: Annotated[
        str | None, typer.Option(help="Reviewed ID from counterguard runner list.")
    ] = None,
    runner: Annotated[str, typer.Option(help="Only docker is supported.")] = "docker",
    format: OutputFormat = OutputFormat.TEXT,
) -> None:
    """Verify historical Shadow/Active Guards and preserve reports on domain failures."""
    from counterguard.verify import VerifyRequest, render_verify, verify_repository

    if runner != "docker":
        _error("verify requires --runner docker; no local fallback exists", 2)
    try:
        report = verify_repository(
            VerifyRequest(repo, base, head, config, registry, output, image, runner_id=runner_id)
        )
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except (OSError, ValueError) as error:
        _error(str(error), 2)
    typer.echo(
        canonical_json_bytes(report).decode()
        if format is OutputFormat.JSON
        else render_verify(report)
    )
    if report.exit_code:
        raise typer.Exit(report.exit_code)


@app.command("ci-report")
def ci_report_command(
    report: Annotated[Path, typer.Option(help="Existing verify report.json; never executed.")],
    output: Annotated[Path, typer.Option(help="New directory for safe summary.json/md only.")],
) -> None:
    """Export an allowlisted GitHub Summary, preserving the verification exit code."""
    from counterguard.github_report import export_github_report

    try:
        code = export_github_report(report, output)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except (OSError, ValueError) as error:
        _error(str(error), 2)
    if code:
        raise typer.Exit(code)


@guard_app.command("transition")
def guard_transition(
    guard_id: str,
    to: Annotated[str, typer.Option(help="shadow, active or retired; legal transitions only.")],
    reason: Annotated[str, typer.Option()],
    root: Path = Path(".counterguard"),
    actor: Annotated[
        str, typer.Option(help="Local audit label, not an authenticated identity.")
    ] = "local-operator",
    format: OutputFormat = OutputFormat.JSON,
) -> None:
    from counterguard.lifecycle import GuardState
    from counterguard.registry import Registry

    try:
        value = Registry(root).transition(guard_id, to=GuardState(to), reason=reason, actor=actor)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except (OSError, ValueError) as error:
        _error(str(error), 2)
    _emit_guard_history(value, format)


@guard_app.command("history")
def guard_history(
    guard_id: str,
    root: Path = Path(".counterguard"),
    format: OutputFormat = OutputFormat.JSON,
) -> None:
    from counterguard.registry import Registry

    try:
        value = Registry(root).show(guard_id)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except (OSError, ValueError) as error:
        _error(str(error), 2)
    _emit_guard_history(value, format)


def _emit_guard_history(value, format):
    if format is OutputFormat.JSON:
        typer.echo(canonical_json_bytes(value).decode())
        return
    typer.echo(f"{value['guard_id']}: {value['status']} / {value['lifecycle_state']}")
    for event in value["events"]:
        typer.echo(
            public_diagnostic(
                f"{event['sequence']} | {event['kind']} | {event.get('before', '-')} -> "
                f"{event.get('after', '-')} | {event['actor']} | {event['reason']}"
            ).replace("\n", " ")
        )


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
    """Run CounterGuard commands."""


@app.command()
def version() -> None:
    """Print the installed CounterGuard version."""
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
    split: Annotated[str, typer.Option(help="Only training samples may be used here.")] = "train",
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
    agent_source: Annotated[
        str | None, typer.Option(help="Use recorded response providers only.")
    ] = None,
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
    run: Annotated[Path | None, typer.Option(help="Immutable evaluation output directory.")] = None,
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
    split: Annotated[
        str, typer.Option(help="Use only the frozen holdout split for evaluation.")
    ] = "holdout",
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
    split: Annotated[str, typer.Option(help="Use only the training split.")] = "train",
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
        # Earlier clients keep the original artifact shape and digest semantics.
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(render_report(command_report(operation, payload), format), nl=False)


def _error(message: str, exit_code: int) -> NoReturn:
    typer.echo(f"Error: {public_diagnostic(message)}", err=True)
    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
