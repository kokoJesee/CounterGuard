"""Real Git fixture-only provenance, budgets, immutable files, and trusted review anchors."""

import json

import pytest

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.repository import RepositoryProblem, read_committed_files
from counterguard.snapshot_admission import (
    bind_snapshot,
    issue_snapshot_review,
    verify_snapshot_binding,
    verify_snapshot_review,
)
from counterguard.snapshot_repository import SnapshotBudget, read_snapshot
from counterguard.standalone_contracts import read_standalone_contract
from tests.repository_support import git
from tests.snapshot_support import snapshot_history

pytestmark = pytest.mark.slow


def test_complete_manifest_does_not_omit_large_media_or_widen_old_profile(tmp_path):
    repo, binding = snapshot_history(tmp_path, large_media=True)
    assert not binding.execution_allowed
    assert set(binding.trees) == {"buggy", "fixed", "head"}
    assert len(binding.contract.cases) == 4
    assert binding.tool_additions == ("contracts/range.json",)
    assert "tests/conftest.py" in binding.upstream_refs and "media.bin" in binding.upstream_refs
    assert "media.bin" not in binding.package_refs["fixed"]
    assert "src/snapshot_sample/data.bin" in binding.package_refs["fixed"]
    assert binding.trees["fixed"].sizes["media.bin"] == 1024 * 1024 + 1
    assert verify_snapshot_binding(repo, tmp_path / "binding.json") == binding
    assert read_snapshot(repo, binding.head_commit)[0] == binding.trees["head"]
    with pytest.raises(RepositoryProblem, match="blob_budget_exceeded"):
        read_committed_files(repo, binding.head_commit)
    with pytest.raises(ValueError):
        read_standalone_contract(canonical_json_bytes(binding.contract))
    with pytest.raises(RepositoryProblem, match="snapshot_blob_budget_exceeded"):
        read_snapshot(repo, binding.head_commit, budget=SnapshotBudget(blob_bytes=1024 * 1024))


def test_review_requires_external_anchor_and_distinct_semantics_authority(tmp_path):
    repo, binding = snapshot_history(tmp_path)
    path = tmp_path / "execution-review.json"
    review = issue_snapshot_review(
        repo,
        tmp_path / "binding.json",
        kind="execution",
        reason="tool-owned fixture source, complete package and Docker reviewed",
        output=path,
    )
    assert (
        verify_snapshot_review(
            repo, tmp_path / "binding.json", path, trusted_digest=review.artifact_digest
        )[1]
        == review
    )
    for anchor, kind in [
        (None, "execution"),
        ("sha256:" + "0" * 64, "execution"),
        (review.artifact_digest, "semantics"),
    ]:
        with pytest.raises(ArtifactIntegrityError):
            verify_snapshot_review(
                repo, tmp_path / "binding.json", path, trusted_digest=anchor, kind=kind
            )
    forged = json.loads(path.read_bytes())
    forged["reason"] = "replaced mutable catalog is not an independent authority"
    forged["artifact_digest"] = digest_json_artifact(forged)
    write_immutable(tmp_path / "forged.json", canonical_json_bytes(forged))
    with pytest.raises(ArtifactIntegrityError, match="trusted_anchor"):
        verify_snapshot_review(
            repo,
            tmp_path / "binding.json",
            tmp_path / "forged.json",
            trusted_digest=review.artifact_digest,
        )
    with pytest.raises((ArtifactIntegrityError, FileExistsError, ValueError)):
        issue_snapshot_review(
            repo,
            tmp_path / "binding.json",
            kind="execution",
            reason="cannot overwrite prior review",
            output=path,
        )
    assert binding.semantic_review == "not_performed"


def test_owner_head_may_not_alter_upstream_or_claim_foreign_contract(tmp_path):
    repo, binding = snapshot_history(tmp_path)
    git(repo, "reset", "--soft", binding.contract.fixed_commit)
    (repo / "src/snapshot_sample/core.py").write_text(
        "raise RuntimeError('changed upstream')\n", encoding="utf-8"
    )
    git(repo, "add", "src/snapshot_sample/core.py", "contracts/range.json")
    git(repo, "commit", "-m", "NOT upstream but forbidden source change")
    with pytest.raises(ArtifactIntegrityError, match="changed_upstream"):
        bind_snapshot(
            repo,
            head=git(repo, "rev-parse", "HEAD"),
            contract_ref="contracts/range.json",
            output=tmp_path / "bad.json",
        )
    assert not (tmp_path / "bad.json").exists()


def test_signed_looking_binding_cannot_drop_a_source_case(tmp_path):
    repo, binding = snapshot_history(tmp_path)
    value = json.loads((tmp_path / "binding.json").read_bytes())
    value["contract"]["cases"].pop()
    value["artifact_digest"] = digest_json_artifact(value)
    write_immutable(tmp_path / "tampered.json", canonical_json_bytes(value))
    with pytest.raises(ArtifactIntegrityError, match="not_reconstructable"):
        verify_snapshot_binding(repo, tmp_path / "tampered.json")


def test_unmarked_history_cannot_obtain_fixture_execution_authority(tmp_path):
    repo, _ = snapshot_history(tmp_path, fixture_marker=False)
    with pytest.raises(ArtifactIntegrityError, match="only_tool_owned_fixtures"):
        issue_snapshot_review(
            repo,
            tmp_path / "binding.json",
            kind="execution",
            reason="not a tool-owned fixture",
            output=tmp_path / "review.json",
        )
    assert not (tmp_path / "review.json").exists()
