"""Expose runner provenance and local availability without running an image."""

import typer

from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.report import OutputFormat
from counterguard.runner_catalog import list_runners

app = typer.Typer(
    no_args_is_help=True, help="Discover reviewed runner images and their provenance."
)


def _show(runner_id, offline, format):
    try:
        value = list_runners(offline=offline, runner_id=runner_id)
    except ArtifactIntegrityError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(5) from error
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error
    if format is OutputFormat.JSON:
        typer.echo(canonical_json_bytes(value).decode())
    else:
        for row in value["runners"]:
            typer.echo(f"{row['runner_id']} | {row['profile']} | {row['availability']}")
            typer.echo("  image: " + row["image_digest"])
            typer.echo("  build: " + row["provenance"]["build_receipt_ref"])
            typer.echo("  attacks: " + row["provenance"]["attack_receipt_ref"])
        typer.echo("Image execution count: 0")
    if value["exit_code"]:
        raise typer.Exit(value["exit_code"])


@app.command("list")
def list_command(offline: bool = False, format: OutputFormat = OutputFormat.TEXT):
    _show(None, offline, format)


@app.command("show")
def show_command(runner_id: str, offline: bool = False, format: OutputFormat = OutputFormat.JSON):
    _show(runner_id, offline, format)
