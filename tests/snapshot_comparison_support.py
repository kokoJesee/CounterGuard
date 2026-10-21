"""Author only independent tool-owned target histories, never import their Python."""

from counterguard.snapshot_admission import FIXTURE_MARKER, FIXTURE_REF
from tests.repository_support import git


def comparison_target_history(workspace, *, name="comparison-target", stdout=False, marker=True):
    repo = workspace / name
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "CounterGuard fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    if marker:
        (repo / FIXTURE_REF).write_bytes(FIXTURE_MARKER)
    package = repo / "src/research_target"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from __future__ import annotations\n"
        "import re\nfrom .core import normalize\nPATTERN = re.compile('x')\n",
        encoding="utf-8",
    )
    protection = (
        "import os\nif os.environ.get('COUNTERGUARD_CONTRACT') != 'cg_control/contract.json':\n"
        " raise RuntimeError('only admitted Docker may import this package')\n"
    )
    function = (
        "def normalize(value): print(min(max(value, 0), 255))\n"
        if stdout
        else "def normalize(value):\n"
        " if not 0 <= value <= 255: raise ValueError('own API rejects')\n return value\n"
    )
    (package / "core.py").write_text(protection + function, encoding="utf-8")
    (package / "resource.txt").write_text("Entire package resource\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        '[project]\nname="research-target"\ndependencies=[]\nrequires-python=">=3.12"\n'
        '[tool.pytest.ini_options]\nminversion="999"\nrequired_plugins=["missing-plugin"]\n',
        encoding="utf-8",
    )
    (repo / "conftest.py").write_text(
        "raise RuntimeError('target conftest must not load')\n", encoding="utf-8"
    )
    (repo / "LICENSE").write_text(
        "CounterGuard tool-owned fixture; test material.\n", encoding="utf-8"
    )
    (repo / "README.md").write_text(
        "normalize prints the clamped integer and returns None.\n"
        if stdout
        else "normalize returns a valid integer unchanged; values outside 0..255 "
        "raise ValueError with message own API rejects.\n",
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "tool-owned independent target and its own policy")
    return repo, git(repo, "rev-parse", "HEAD")
