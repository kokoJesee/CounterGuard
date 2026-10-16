"""Review states share Registry's immutable, cross-checked JSON/SQLite event chain."""

import json

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.lifecycle import GuardState, require_transition
from counterguard.registry import Registry
from tests.unit.test_integrity import captured  # noqa: F401
from tests.unit.test_registry import GUARD_ID, registered_inputs  # noqa: F401


@pytest.mark.parametrize("before", list(GuardState))
@pytest.mark.parametrize("after", list(GuardState))
def test_complete_transition_matrix(before, after):
    legal = {
        ("candidate", "shadow"),
        ("candidate", "retired"),
        ("shadow", "active"),
        ("shadow", "retired"),
        ("active", "shadow"),
        ("active", "retired"),
    }
    if (before.value, after.value) in legal:
        require_transition(before, after)
    else:
        with pytest.raises(ValueError, match="Illegal"):
            require_transition(before, after)


def test_states_append_without_rewriting_registration_or_guard(registered_inputs):  # noqa: F811
    workspace, path, guard = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    original = {p: p.read_bytes() for p in (path, registry.root / "events/00000001.json")}
    assert registry.show(GUARD_ID)["lifecycle_state"] == "candidate"
    for state in (GuardState.SHADOW, GuardState.ACTIVE, GuardState.SHADOW, GuardState.RETIRED):
        registry.transition(GUARD_ID, to=state, reason="reviewed", actor="reviewer")
        assert registry.show(GUARD_ID)["lifecycle_state"] == state.value
    assert all(p.read_bytes() == content for p, content in original.items())
    assert len(registry.show(GUARD_ID)["events"]) == 5
    assert registry.show(GUARD_ID)["guard_digest"] == guard.artifact_digest
    registry.add(path, cwd=workspace)
    with pytest.raises(ValueError, match="Illegal"):
        registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="resurrect")
    (registry.root / "registry.sqlite3").unlink()
    registry.rebuild_index()
    assert registry.show(GUARD_ID)["lifecycle_state"] == "retired"
    assert registry.show(GUARD_ID)["verification_schedulable"] is False
    with pytest.raises(ArtifactIntegrityError, match="retired"):
        registry.resolve_for_execution(GUARD_ID)


def test_disable_is_terminal_and_stale_sources_can_only_be_retired(registered_inputs):  # noqa: F811
    workspace, path, _ = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    path.write_bytes(b"damaged")
    with pytest.raises(ArtifactIntegrityError):
        registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="review")
    registry.transition(GUARD_ID, to=GuardState.RETIRED, reason="stale")
    registry.disable(GUARD_ID, reason="disabled")
    with pytest.raises(ArtifactIntegrityError, match="disabled"):
        registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="resurrect")


def test_resigned_event_cannot_skip_state_even_after_index_rebuild(registered_inputs):  # noqa: F811
    workspace, path, _ = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    registry.transition(GUARD_ID, to=GuardState.SHADOW, reason="review")
    event = registry.root / "events/00000002.json"
    payload = json.loads(event.read_bytes())
    payload.update(before="shadow", after="active")
    payload["artifact_digest"] = digest_json_artifact(payload)
    event.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(ArtifactIntegrityError):
        registry.list()
    (registry.root / "registry.sqlite3").unlink()
    with pytest.raises(ArtifactIntegrityError):
        registry.rebuild_index()


def test_guard_transition_cli_rejects_direct_activation(registered_inputs):  # noqa: F811
    workspace, path, _ = registered_inputs
    registry = Registry(workspace / "registry")
    registry.add(path, cwd=workspace)
    runner = CliRunner()
    args = ["guard", "transition", GUARD_ID, "--root", str(registry.root), "--reason", "review"]
    assert runner.invoke(app, [*args, "--to", "active"]).exit_code == 2
    assert runner.invoke(app, [*args, "--to", "shadow"]).exit_code == 0
    history = runner.invoke(app, ["guard", "history", GUARD_ID, "--root", str(registry.root)])
    assert history.exit_code == 0
    assert "local-operator" in history.output
