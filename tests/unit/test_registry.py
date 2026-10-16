"""Registry facts and status never substitute for a fresh source-chain audit."""

import json
import sqlite3

import pytest
from typer.testing import CliRunner

from evidenceguard.cli import app
from evidenceguard.compiler import CompileRequest, compile_guard
from evidenceguard.digests import canonical_json_bytes, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.registry import Registry
from tests.unit.test_integrity import captured  # noqa: F401

GUARD_ID = "grd_registry_v1"


@pytest.fixture
def registered_inputs(captured):  # noqa: F811
    workspace, _ = captured
    guard = compile_guard(
        CompileRequest(
            GUARD_ID,
            workspace / "artifacts/evidence/evd_integrity_v1/evidence.json",
            workspace,
            workspace / "artifacts",
        )
    )
    path = workspace / f"artifacts/guards/{GUARD_ID}/guard.json"
    return workspace, path, guard


def test_add_is_idempotent_and_disabled_records_cannot_be_reenabled(registered_inputs):
    workspace, path, guard = registered_inputs
    registry = Registry(workspace / "registry")
    first = registry.add(path, cwd=workspace)
    facts = (registry.root / f"entries/{GUARD_ID}.json").read_bytes()
    assert registry.add(path, cwd=workspace) == first
    assert (registry.root / f"entries/{GUARD_ID}.json").read_bytes() == facts
    assert len(registry.show(GUARD_ID)["events"]) == 1
    assert registry.resolve_for_execution(GUARD_ID).guard == guard
    registry.disable(GUARD_ID, reason="manual review", actor="reviewer")
    registry.disable(GUARD_ID, reason="manual review", actor="reviewer")
    registry.add(path, cwd=workspace)
    assert len(registry.show(GUARD_ID)["events"]) == 2
    assert registry.list()[0]["status"] == "disabled"
    with pytest.raises(ArtifactIntegrityError, match="disabled"):
        registry.resolve_for_execution(GUARD_ID)


def test_same_identity_with_another_digest_is_rejected(registered_inputs):
    workspace, path, guard = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    payload = guard.model_dump(mode="json")
    payload["created_at"] = "2026-10-16T01:00:00Z"
    payload["artifact_digest"] = digest_json_artifact(payload)
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="different digest"):
        registry.add(path, cwd=workspace)


@pytest.mark.parametrize("damage", ["source", "junit", "evidence"])
def test_source_chain_damage_is_visible_and_cannot_be_scheduled(registered_inputs, damage):
    workspace, path, guard = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    entry = registry.resolve_for_execution(GUARD_ID)
    ref = {
        "source": entry.evidence.fixed_target.source_ref,
        "junit": guard.validation_run.junit_ref,
        "evidence": guard.source_evidence_ref,
    }[damage]
    (workspace / ref).write_bytes(b"damaged")
    assert registry.list()[0]["integrity"] == "invalid"
    assert registry.show(GUARD_ID)["schedulable"] is False
    with pytest.raises(ArtifactIntegrityError):
        registry.resolve_for_execution(GUARD_ID)


def test_sqlite_is_an_index_and_json_event_history_survives_rebuild(registered_inputs):
    workspace, path, _ = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    registry.disable(GUARD_ID, reason="review")
    database = registry.root / "registry.sqlite3"
    database.unlink()
    with pytest.raises(ArtifactIntegrityError, match="index"):
        registry.resolve_for_execution(GUARD_ID)
    registry.rebuild_index()
    assert registry.show(GUARD_ID)["status"] == "disabled"
    with (
        sqlite3.connect(database) as connection,
        pytest.raises(sqlite3.DatabaseError, match="append-only"),
    ):
        connection.execute("DELETE FROM events")


def test_resigned_state_event_and_index_tampering_fail_closed(registered_inputs):
    workspace, path, _ = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    registry.disable(GUARD_ID, reason="review")
    event = registry.root / "events/00000002.json"
    payload = json.loads(event.read_bytes())
    payload["kind"] = "registered"
    payload["artifact_digest"] = digest_json_artifact(payload)
    event.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(ArtifactIntegrityError):
        registry.resolve_for_execution(GUARD_ID)
    with pytest.raises(ArtifactIntegrityError):
        registry.rebuild_index()


def test_ids_and_empty_reasons_cannot_become_paths(registered_inputs):
    workspace, path, _ = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    for guard_id in ("../escape", "C:/escape", "grd_a/b"):
        with pytest.raises(ValueError):
            registry.show(guard_id)
    with pytest.raises(ValueError):
        registry.disable(GUARD_ID, reason="   ")


def test_index_mutation_and_incomplete_publication_do_not_schedule(registered_inputs):
    workspace, path, _ = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    with sqlite3.connect(registry.root / "registry.sqlite3") as connection:
        connection.execute("DROP TRIGGER events_no_delete")
        connection.execute("DELETE FROM events")
    with pytest.raises(ArtifactIntegrityError, match="disagrees"):
        registry.resolve_for_execution(GUARD_ID)
    with pytest.raises(ArtifactIntegrityError):
        registry.add(path, cwd=workspace)


def test_deleted_event_fails_even_when_database_is_missing(registered_inputs):
    workspace, path, _ = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    (registry.root / "events/00000001.json").unlink()
    (registry.root / "registry.sqlite3").unlink()
    with pytest.raises(ArtifactIntegrityError, match="incomplete"):
        registry.rebuild_index()


def test_registry_cli_has_the_same_facts_and_exit_five_for_damage(registered_inputs):
    workspace, path, _ = registered_inputs
    runner = CliRunner()
    root = workspace / "registry"
    added = runner.invoke(
        app, ["registry", "add", str(path), "--cwd", str(workspace), "--root", str(root)]
    )
    assert added.exit_code == 0, added.output
    shown = runner.invoke(
        app, ["registry", "show", GUARD_ID, "--root", str(root), "--with-evidence"]
    )
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["evidence"]["reproduced"] is True
    (root / "registry.sqlite3").write_bytes(b"not sqlite")
    failed = runner.invoke(app, ["registry", "show", GUARD_ID, "--root", str(root)])
    assert failed.exit_code == 5, failed.output
