"""Actual Git target inspection; no candidate execution or Docker."""

import pytest

from counterguard.snapshot_admission import read_value
from counterguard.snapshot_comparison_data import inspect_snapshot_target
from counterguard.snapshot_comparison_models import SnapshotComparisonTarget, SnapshotTargetEntry
from counterguard.study_models import StudyTarget
from tests.snapshot_comparison_support import comparison_target_history

pytestmark = pytest.mark.slow


def test_readonly_full_target_pins_ignore_dirty_worktree_and_keep_original_configs(tmp_path):
    repo, revision = comparison_target_history(tmp_path)
    entry = SnapshotTargetEntry(
        target_module="research_target",
        target_symbol="normalize",
        source_ref="src/research_target/__init__.py",
        import_root="src",
    )
    kwargs = dict(
        target_id="target",
        entry=entry,
        license_ref="LICENSE",
        interface_kind="value_return",
        interface_basis_ref="README.md",
    )
    target, _ = inspect_snapshot_target(repo, revision, output=tmp_path / "target.json", **kwargs)
    assert not target.execution_allowed
    assert "conftest.py" in target.manifest.sizes and "pyproject.toml" in target.manifest.sizes
    assert set(target.package_refs) == {
        "src/research_target/__init__.py",
        "src/research_target/core.py",
        "src/research_target/resource.txt",
    }
    (repo / "src/research_target/core.py").write_text(
        "raise RuntimeError('dirty bytes not admitted')\n", encoding="utf-8"
    )
    (repo / "conftest.py").unlink()
    assert inspect_snapshot_target(repo, revision, **kwargs)[0] == target
    assert read_value(tmp_path / "target.json", SnapshotComparisonTarget) == target
    with pytest.raises(ValueError):
        StudyTarget.model_validate_json((tmp_path / "target.json").read_bytes())
