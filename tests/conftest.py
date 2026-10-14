"""Share one real D8 capture/compile/fit setup while keeping mutated checks isolated."""

import shutil
import subprocess
from pathlib import Path

import pytest

from evidenceguard.scope import fit_scopes
from scripts.prepare_scope_v1 import prepare

ROOT = Path(__file__).resolve().parents[1]
SLOW_DIRECTORIES = frozenset({"integration", "e2e"})
SLOW_FIXTURES = frozenset({"replay_workspace", "flow"})


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    """Assign tiers before -m selection, including transitive fixture dependencies."""
    for item in items:
        relative = item.path.relative_to(ROOT / "tests")
        if (
            relative.parts[0] in SLOW_DIRECTORIES or SLOW_FIXTURES.intersection(item.fixturenames)
        ) and item.get_closest_marker("slow") is None:
            item.add_marker(pytest.mark.slow)
        if item.get_closest_marker("slow") is not None:
            if item.get_closest_marker("fast") is not None:
                raise pytest.UsageError(f"Test cannot be both fast and slow: {item.nodeid}")
        else:
            item.add_marker(pytest.mark.fast)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item):
    """Cover fixture setup/call/teardown, including module/session fixture setup."""
    if item.get_closest_marker("slow") is not None:
        yield
        return

    def forbidden(*args, **kwargs):
        pytest.fail("Fast test attempted a real child process; mark it pytest.mark.slow")

    with pytest.MonkeyPatch.context() as guard:
        guard.setattr(subprocess, "Popen", forbidden)
        yield


@pytest.fixture(scope="session")
def replay_workspace(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("replay")
    for directory in ("examples", "benchmarks", "experiments", "tests/contract_tests"):
        shutil.copytree(
            ROOT / directory, workspace / directory, ignore=shutil.ignore_patterns("__pycache__")
        )
    prepare(workspace)
    for phase in ("initial", "refined"):
        fit_scopes(
            "experiments/scope_v1.json",
            phase=phase,
            output=f"artifacts/fitted/{phase}",
            cwd=workspace,
        )
    return workspace


@pytest.fixture
def mutable_replay_workspace(replay_workspace, tmp_path):
    shutil.copytree(
        replay_workspace, tmp_path, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__")
    )
    return tmp_path
