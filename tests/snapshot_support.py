"""Only tool-authored fixtures; creating this history invokes Git, never Python code."""

from counterguard.models import RunOutcome
from counterguard.snapshot_admission import (
    FIXTURE_MARKER,
    FIXTURE_REF,
    bind_snapshot,
    prepare_snapshot_contract,
)
from tests.repository_support import git


def assert_snapshot_attack_observed(run, behavior):
    """Do not confuse a generic Docker launch failure with a successful attack test."""
    assert run.python_version == "3.13.16" and run.pytest_version == "8.4.2"
    if behavior == "timeout":
        assert run.outcome is RunOutcome.TIMEOUT and run.pytest_exit_code is None
    elif behavior == "memory":
        # The tool-owned bytearray fixture is killed inside the live runner;
        # a missing image/Engine or container transport error is insufficient.
        assert run.outcome is RunOutcome.PROCESS_ERROR and run.pytest_exit_code == -9
    else:
        assert run.outcome is RunOutcome.TEST_FAILED and run.pytest_exit_code == 1
        assert len(run.case_results) == 4
        messages = "\n".join(c.message or "" for c in run.case_results)
        marker = {
            "network": "Network is unreachable",
            "write": "Read-only file system",
            "environment": "AssertionError",
            "process": "Resource temporarily unavailable",
        }[behavior]
        assert marker in messages


def snapshot_history(workspace, *, large_media=False, behavior="normal", fixture_marker=True):
    repo = workspace / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "CounterGuard fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    if fixture_marker:
        (repo / FIXTURE_REF).write_bytes(FIXTURE_MARKER)
    package = repo / "src/snapshot_sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "import re\nfrom .core import check\n"
        "PATTERN = re.compile('abc')\n"
        "class Hook(type):\n def __getattr__(cls, name): return name\n",
        encoding="utf-8",
    )
    protection = (
        "from __future__ import annotations\n"
        "import os\n"
        "if os.environ.get('COUNTERGUARD_CONTRACT') != 'cg_control/contract.json':\n"
        " raise RuntimeError('Docker only')\n"
    )
    (package / "core.py").write_text(
        protection + "def check(value): return value\n", encoding="utf-8"
    )
    (repo / "pyproject.toml").write_text(
        '[project]\nname="snapshot-sample"\ndependencies=[]\nrequires-python=">=3.12"\n'
        '[tool.pytest.ini_options]\nminversion="999"\nrequired_plugins=["missing-plugin"]\n',
        encoding="utf-8",
    )
    (repo / "conftest.py").write_text(
        "raise RuntimeError('root conftest must not load')\n", encoding="utf-8"
    )
    tests = repo / "tests"
    tests.mkdir()
    (tests / "conftest.py").write_text(
        "raise RuntimeError('test conftest must not load')\n", encoding="utf-8"
    )
    if large_media:
        (repo / "media.bin").write_bytes(b"A" * (1024 * 1024 + 1))
        (package / "data.bin").write_bytes(b"B" * (1024 * 1024 + 1))
    git(repo, "add", ".")
    git(repo, "commit", "-m", "tool-owned buggy snapshot")
    buggy = git(repo, "rev-parse", "HEAD")
    attack = {
        "normal": "",
        "network": " import socket\n socket.create_connection(('1.1.1.1', 443), timeout=1)\n",
        "write": " open('/workspace/src/snapshot_sample/core.py', 'w').write('changed')\n",
        "environment": " assert 'COUNTERGUARD_HOST_SECRET' in os.environ\n",
        "timeout": " while True: pass\n",
        "memory": " value = bytearray(512 * 1024 * 1024)\n",
        "process": (
            " import subprocess\n children = []\n try:\n"
            "  for _ in range(128): children.append(subprocess.Popen(['sleep', '60']))\n"
            " finally:\n  for child in children: child.kill()\n"
            "  for child in children: child.wait()\n"
        ),
    }[behavior]
    (package / "core.py").write_text(
        protection
        + "def check(value):\n"
        + attack
        + " if not 0 <= value <= 255: raise ValueError('outside range')\n return value\n",
        encoding="utf-8",
    )
    (tests / "test_check.py").write_text(
        "raise RuntimeError('original test module must never execute')\n"
        "import pytest\nfrom snapshot_sample.core import check\n"
        "@pytest.mark.parametrize('value', [pytest.param(-1, id='negative'),\n"
        " pytest.param(256, id='too large')])\n"
        "def test_invalid(value):\n assert check(7) == 7\n"
        " with pytest.raises(ValueError, match='outside range'): check(value)\n",
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "tool-owned fix with original parameterized regression")
    fixed = git(repo, "rev-parse", "HEAD")
    prepare_snapshot_contract(
        repo,
        buggy=buggy,
        fixed=fixed,
        test_ref="tests/test_check.py",
        test_function="test_invalid",
        target_module="snapshot_sample.core",
        target_symbol="check",
        source_ref="src/snapshot_sample/core.py",
        import_root="src",
        contract_id="snapshot.range.v1",
        output=workspace / "proposal.json",
    )
    (repo / "contracts").mkdir()
    (repo / "contracts/range.json").write_bytes((workspace / "proposal.json").read_bytes())
    git(repo, "add", "contracts/range.json")
    git(repo, "commit", "-m", "NOT upstream: tool-owned fixture contract only")
    head = git(repo, "rev-parse", "HEAD")
    binding = bind_snapshot(
        repo, head=head, contract_ref="contracts/range.json", output=workspace / "binding.json"
    )
    return repo, binding
