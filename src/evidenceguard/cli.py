"""Command-line entry point for the EvidenceGuard MVP."""

import typer

from evidenceguard import __version__

app = typer.Typer(no_args_is_help=True, help="Scope-aware regression guard tooling.")


@app.callback()
def main() -> None:
    """Run EvidenceGuard commands."""


@app.command()
def version() -> None:
    """Print the installed EvidenceGuard version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
