"""CLI projection of the concrete local Registry interface."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from counterguard.diagnostics import public_diagnostic
from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.registry import Registry
from counterguard.report import OutputFormat

app = typer.Typer(no_args_is_help=True, help="Manage immutable local Guard registrations.")
Root = Annotated[Path, typer.Option(help="Local registry root; source workspaces stay in place.")]


def _call(operation: Callable, format: OutputFormat):
    try:
        result = operation()
    except (ArtifactIntegrityError, OSError) as error:
        typer.echo("Error: " + public_diagnostic(str(error)), err=True)
        raise typer.Exit(5) from error
    except ValueError as error:
        typer.echo("Error: " + public_diagnostic(str(error)), err=True)
        raise typer.Exit(2) from error
    if format is OutputFormat.JSON:
        typer.echo(canonical_json_bytes(result).decode())
    else:
        rows = result if isinstance(result, list) else [result]
        if format is OutputFormat.MARKDOWN:
            typer.echo("| Guard | Status | Integrity | Schedulable |\n|---|---|---|---|")
        for row in rows:
            typer.echo(
                f"{row.get('guard_id', '')} | {row.get('status', '')} | "
                f"{row.get('integrity', '')} | {row.get('schedulable', '')}"
            )
    rows = result if isinstance(result, list) else [result]
    if any(row.get("integrity") == "invalid" for row in rows):
        raise typer.Exit(5)


@app.command("add")
def add(
    path: Annotated[Path, typer.Argument(help="Verified guard.json below cwd.")],
    root: Root = Path(".counterguard"),
    cwd: Annotated[Path, typer.Option(help="Source-chain workspace.")] = Path("."),
    format: OutputFormat = OutputFormat.JSON,
):
    registry = Registry(root)

    def register():
        entry = registry.add(path, cwd=cwd)
        return registry.show(entry.guard.guard_id)

    _call(register, format)


@app.command("list")
def list_entries(root: Root = Path(".counterguard"), format: OutputFormat = OutputFormat.JSON):
    _call(lambda: Registry(root).list(), format)


@app.command("show")
def show(
    guard_id: str,
    root: Root = Path(".counterguard"),
    with_evidence: bool = False,
    format: OutputFormat = OutputFormat.JSON,
):
    _call(lambda: Registry(root).show(guard_id, with_evidence=with_evidence), format)


@app.command("disable")
def disable(
    guard_id: str,
    reason: Annotated[str, typer.Option()],
    root: Root = Path(".counterguard"),
    format: OutputFormat = OutputFormat.JSON,
):
    _call(lambda: Registry(root).disable(guard_id, reason=reason), format)


@app.command("rebuild-index")
def rebuild_index(root: Root = Path(".counterguard")):
    def rebuild():
        Registry(root).rebuild_index()
        return {"rebuilt": True}

    _call(rebuild, OutputFormat.JSON)
