"""CLI smoke tests."""

from typer.testing import CliRunner

from evidenceguard import __version__
from evidenceguard.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
