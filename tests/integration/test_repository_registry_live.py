"""Opt-in audit of real v2 registry facts; all mutations affect temporary copies only."""

import os
import shutil
from pathlib import Path

import pytest

from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.pilot_inputs import read_fact, signed
from counterguard.registry import Registry
from counterguard.repository_contracts import GUARD_ID

pytestmark = pytest.mark.slow


@pytest.fixture
def registry_copy(tmp_path):
    manifest_ref = os.environ.get("COUNTERGUARD_PILOT_MANIFEST")
    if not manifest_ref:
        pytest.skip("set COUNTERGUARD_PILOT_MANIFEST for the completed real fork pilot")
    root = Path(__file__).resolve().parents[2]
    manifest = read_fact(root / manifest_ref)
    destination = tmp_path / "registry-copy"
    shutil.copytree(root / manifest["registry_root_ref"], destination)
    return destination


def test_real_v2_entry_preserves_terminal_disable(registry_copy):
    entry = read_fact(registry_copy / "entries" / f"{GUARD_ID}.json")
    assert entry["schema_version"] == "registry-entry.v2"
    assert entry["guard"]["schema_version"] == "guard.v2"
    registry = Registry(registry_copy)
    registry.disable(GUARD_ID, reason="task-owned copied-registry terminal-state audit")
    with pytest.raises(ArtifactIntegrityError, match="disabled"):
        registry.resolve_for_execution(GUARD_ID)


def test_real_v2_missing_source_cannot_be_scheduled_even_after_index_rebuild(registry_copy):
    path = registry_copy / "entries" / f"{GUARD_ID}.json"
    entry = read_fact(path)
    entry["source_workspace"] = str(registry_copy / "missing-source")
    path.write_bytes(canonical_json_bytes(signed(entry)))
    # This is the test-owned clone's index, not any original fact or artifact.
    database = registry_copy / "registry.sqlite3"
    assert database.resolve().parent == registry_copy.resolve()
    database.unlink()
    registry = Registry(registry_copy)
    registry.rebuild_index()
    with pytest.raises(ArtifactIntegrityError, match="invalid or unavailable"):
        registry.resolve_for_execution(GUARD_ID)
