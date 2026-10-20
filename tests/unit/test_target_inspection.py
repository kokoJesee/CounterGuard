"""Comparison inspections cannot become source bindings or execution permission."""

import importlib
import json
import random
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.bootstrap_binding import verify_binding
from counterguard.cli import app
from counterguard.errors import ArtifactIntegrityError
from counterguard.standalone_contracts import read_standalone_contract
from counterguard.target_inspection import inspect_static_target
from tests.unit.test_bootstrap_binding import pins
from tests.unit.test_static_exports_v2 import files

inspector = importlib.import_module("counterguard.target_inspection")


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    tree = {
        **files(),
        "pyproject.toml": b'[project]\nname="sample"\n',
        "tests/conftest.py": b"raise RuntimeError('never load')\n",
    }
    monkeypatch.setattr(inspector, "read_committed_files", lambda *_: ("a" * 40, tree, pins(tree)))
    monkeypatch.chdir(tmp_path)
    return repo, tree


def inspect(repo, output):
    return inspect_static_target(
        repo,
        "a" * 40,
        target="sample:price",
        import_root=".",
        profile="static-reexport-v2",
        output=Path(output),
    )


def test_comparison_inspection_pins_whole_tree_but_never_claims_source_provenance(inputs):
    repo, tree = inputs
    value = inspect(repo, "target-v1")
    assert value["runtime_assessment"]["status"] == "review_required"
    assert {pin["path"] for pin in value["files"]} == set(tree)
    assert not value["execution_allowed"] and not value["cross_repository_execution_supported"]
    assert value["execution_outcome"] == "not_run"
    assert "cases" not in value and "contract" not in value
    assert value["bootstrap_observations"][1]["loaded_by_plan"] is False
    with pytest.raises(ValueError):
        read_standalone_contract(Path("target-v1/target.json").read_bytes())
    with pytest.raises(ArtifactIntegrityError, match="not_a_source_binding"):
        verify_binding(repo, Path("target-v1/target.json"))
    with pytest.raises(ArtifactIntegrityError, match="Output exists"):
        inspect(repo, "target-v1")


def test_target_inspection_uses_same_dependency_admission_without_override(inputs):
    repo, tree = inputs
    tree["pyproject.toml"] = b'[project]\nname="sample"\ndependencies=["external"]\n'
    value = inspect(repo, "blocked-target")
    assert value["runtime_assessment"]["status"] == "blocked"
    assert any(
        x["code"] == "runtime_dependency_installation_required"
        for x in value["runtime_assessment"]["findings"]
    )
    assert not value["execution_allowed"]


def test_target_inspection_keeps_unknown_and_rejects_unrecognized_profile(inputs):
    repo, tree = inputs
    tree["sample/__init__.py"] += b"side_effect()\n"
    value = inspect(repo, "unknown-target")
    assert value["runtime_assessment"]["status"] == "unknown"
    with pytest.raises(ValueError, match="explicit profile"):
        inspect_static_target(
            repo,
            "HEAD",
            target="sample:price",
            import_root=".",
            profile="bypass",
            output=Path("bypass"),
        )


def test_target_inspection_is_stable_for_twenty_pin_and_file_shuffles(inputs, monkeypatch):
    repo, tree = inputs
    expected = inspect(repo, "expected-target")
    items = list(tree.items())
    for seed in range(20):
        random.Random(seed).shuffle(items)
        shuffled = dict(items)
        monkeypatch.setattr(
            inspector,
            "read_committed_files",
            lambda *_, tree=shuffled: ("a" * 40, tree, tuple(reversed(pins(tree)))),
        )
        assert inspect(repo, f"target-{seed}") == expected


def test_cli_exposes_target_without_requiring_fake_buggy_fixed_or_test(inputs):
    repo, _ = inputs
    result = CliRunner().invoke(
        app,
        [
            "bootstrap",
            "inspect-target",
            "--repo",
            str(repo),
            "--revision",
            "a" * 40,
            "--target",
            "sample:price",
            "--import-root",
            ".",
            "--profile",
            "static-reexport-v2",
            "--output",
            "cli-target",
        ],
    )
    assert result.exit_code == 4, result.output
    assert json.loads(result.stdout)["execution_outcome"] == "not_run"
