"""Prevent Windows path regressions before filesystem or execution side effects."""

from dataclasses import replace
from pathlib import PureWindowsPath

import pytest

from counterguard.artifacts import write_immutable
from counterguard.execution import run_pytest
from counterguard.path_limits import (
    PATH_BUDGET,
    PLACEHOLDER_ID,
    path_units,
    require_evaluation_directory,
    require_paths,
    require_publication,
    require_replay_directory,
    require_run_directory,
)
from tests.unit.test_execution import _request


def test_utf16_budget_includes_non_bmp_characters():
    path = PureWindowsPath("C:/" + "😀" * 115)
    assert path_units(path) == 233
    require_paths(path)
    with pytest.raises(ValueError, match="UTF-16"):
        require_paths(PureWindowsPath("C:/" + "😀" * 120))


def test_longest_atomic_temporary_path_is_checked():
    path = PureWindowsPath("C:/" + "a" * 80 + "/" + "b" * 80 + "/" + "c" * 50 + ".json")
    assert path_units(path) < PATH_BUDGET
    with pytest.raises(ValueError, match="shorter"):
        require_publication(path)


def test_rejected_publication_does_not_create_parent_directory(tmp_path):
    path = tmp_path / ("a" * 50) / ("b" * 50) / ("c" * 70 + ".json")
    with pytest.raises(ValueError, match="Artifact path"):
        write_immutable(path, b"data")
    assert not path.parent.exists()


def test_overlong_run_rejected_before_mkdir_or_subprocess(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Path preflight must prevent subprocess execution")

    monkeypatch.setattr("subprocess.run", forbidden)
    root = tmp_path / ("a" * 60) / ("b" * 60)
    request = replace(_request(tmp_path), artifact_root=root)
    with pytest.raises(ValueError, match="Artifact path"):
        run_pytest(request)
    assert not root.exists()


@pytest.mark.parametrize("day", ["day10", "day11", "day13-smoke", "demo-run"])
def test_planned_d10_to_d14_layouts_fit_the_portable_budget(day):
    root = PureWindowsPath("D:/workspace/counterguard/artifacts") / day
    candidate = root / "candidates" / f"cnd_{PLACEHOLDER_ID}"
    require_publication(candidate / "candidate.json")
    require_publication(candidate / "gate.json")
    require_publication(candidate / "test_candidate.py")
    require_run_directory(candidate / "runtime/runs" / f"run_{PLACEHOLDER_ID}")
    require_replay_directory(root / "replays" / f"rpl_{PLACEHOLDER_ID}")


def test_actual_d9_layout_includes_cache_and_long_report_filenames():
    require_evaluation_directory(
        PureWindowsPath(
            "D:/workspace/counterguard/artifacts/experiments/scope-v1/final-repeat-v1"
        )
    )
