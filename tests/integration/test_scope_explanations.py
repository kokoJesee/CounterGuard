"""Export explanations from audited fits without running or rewriting assets."""

import pytest

from counterguard.digests import digest_file
from counterguard.errors import ArtifactIntegrityError
from counterguard.scope_explanations import explain_fitted_scopes


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): digest_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("phase", ["initial", "refined"])
def test_export_is_read_only_for_upstream_and_never_starts_pytest(
    replay_workspace, monkeypatch, phase
):
    def forbidden(*args, **kwargs):
        pytest.fail("An explanation must not launch a process")

    monkeypatch.setattr("subprocess.run", forbidden)
    before = snapshot(replay_workspace / "artifacts")
    output = f"analyses/scope-explanations-v1/{phase}"
    result = explain_fitted_scopes(
        f"artifacts/fitted/{phase}/fit-manifest.json",
        output=output,
        cwd=replay_workspace,
    )
    assert len(result) == 2
    assert all(
        len(item.clause_witnesses) == (1 if phase == "initial" else 2) for item in result.values()
    )
    assert snapshot(replay_workspace / "artifacts") == before
    written = snapshot(replay_workspace / output)
    repeated = explain_fitted_scopes(
        f"artifacts/fitted/{phase}/fit-manifest.json",
        output=output,
        cwd=replay_workspace,
    )
    assert repeated == result
    assert snapshot(replay_workspace / output) == written


def test_stale_learning_is_refused_before_any_explanation_is_written(mutable_replay_workspace):
    workspace = mutable_replay_workspace
    learning = next((workspace / "artifacts/fitted/refined").glob("*.learning.json"))
    learning.write_bytes(learning.read_bytes().replace(b'"conjunction.v1"', b'"conjunction.v0"'))
    with pytest.raises(ArtifactIntegrityError):
        explain_fitted_scopes(
            "artifacts/fitted/refined/fit-manifest.json",
            output="analyses/rejected",
            cwd=workspace,
        )
    assert not (workspace / "analyses/rejected").exists()
