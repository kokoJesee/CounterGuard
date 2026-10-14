"""Share one real D8 capture/compile/fit setup while keeping mutated checks isolated."""

import shutil
from pathlib import Path

import pytest

from evidenceguard.scope import fit_scopes
from scripts.prepare_scope_v1 import prepare

ROOT = Path(__file__).resolve().parents[1]


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
