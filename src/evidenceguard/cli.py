"""Command-line entry point for the EvidenceGuard MVP."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from evidenceguard import __version__
from evidenceguard.compiler import CompileRequest, compile_guard, run_guard, verify_guard
from evidenceguard.errors import ArtifactIntegrityError, GuardSelfCheckError, InvalidEvidenceError
from evidenceguard.evidence import CaptureRequest, capture_evidence, verify_evidence
from evidenceguard.models import Evidence, RunOutcome, RunRecord

app = typer.Typer(no_args_is_help=True, help="Scope-aware regression guard tooling.")
evidence_app = typer.Typer(no_args_is_help=True, help="Verify stored Evidence artifacts.")
app.add_typer(evidence_app, name="evidence")
guard_app = typer.Typer(no_args_is_help=True, help="Audit and directly smoke-test Guard assets.")
app.add_typer(guard_app, name="guard")


@app.callback()
def main() -> None:
    """Run EvidenceGuard commands."""


@app.command()
def version() -> None:
    """Print the installed EvidenceGuard version."""
    typer.echo(__version__)


@app.command()
def capture(
    evidence_id: Annotated[str, typer.Option(help="Stable evd_ identity for this capture.")],
    contract: Annotated[Path, typer.Option(help="Repository-relative contract JSON.")],
    test: Annotated[Path, typer.Option(help="Repository-relative pytest contract test.")],
    buggy_target: Annotated[str, typer.Option(help="Buggy module:symbol.")],
    fixed_target: Annotated[str, typer.Option(help="Fixed module:symbol.")],
    artifact_root: Annotated[Path, typer.Option(help="Output directory below cwd.")] = Path(
        "artifacts"
    ),
    cwd: Annotated[Path, typer.Option(help="Trusted project workspace.")] = Path("."),
    timeout: Annotated[float, typer.Option(help="Per-run timeout in seconds.")] = 30.0,
) -> None:
    """Capture a buggy failure and fixed pass as auditable JSON Evidence."""
    try:
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
            )
        )
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"capture execution error: {error}", 3)
    _emit_evidence(evidence)


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
) -> None:
    """Compile minimal regression assertions and validate them on the fixed target."""
    try:
        guard = compile_guard(CompileRequest(guard_id, evidence, cwd, artifact_root))
    except GuardSelfCheckError as error:
        typer.echo(str(error), err=True)
        _emit_run(error.run)
        raise typer.Exit(3) from error
    except InvalidEvidenceError as error:
        _error(str(error), 1)
    except ArtifactIntegrityError as error:
        _error(str(error), 5)
    except ValueError as error:
        _error(str(error), 2)
    except OSError as error:
        _error(f"compile execution error: {error}", 3)
    typer.echo(guard.model_dump_json(indent=2))


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


def _emit_evidence(evidence: Evidence) -> None:
    typer.echo(evidence.model_dump_json(indent=2))
    valid_outcomes = {RunOutcome.PASSED, RunOutcome.TEST_FAILED}
    if any(run.outcome not in valid_outcomes for run in (evidence.buggy_run, evidence.fixed_run)):
        raise typer.Exit(3)
    if not evidence.reproduced:
        raise typer.Exit(1)


def _error(message: str, exit_code: int) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
