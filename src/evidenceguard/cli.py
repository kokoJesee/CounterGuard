"""Command-line entry point for the EvidenceGuard MVP."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from evidenceguard import __version__
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.evidence import CaptureRequest, capture_evidence, verify_evidence
from evidenceguard.models import Evidence, RunOutcome

app = typer.Typer(no_args_is_help=True, help="Scope-aware regression guard tooling.")
evidence_app = typer.Typer(no_args_is_help=True, help="Verify stored Evidence artifacts.")
app.add_typer(evidence_app, name="evidence")


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
