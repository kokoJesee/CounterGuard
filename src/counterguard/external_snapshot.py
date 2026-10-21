"""Trusted, independently anchored external source review and Docker observations."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.external_snapshot_models import (
    ExternalSnapshotAuthorization,
    ExternalSnapshotEvidence,
    ExternalSnapshotGuard,
    ExternalSnapshotReview,
)
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import DockerPolicyV1
from counterguard.snapshot_admission import (
    read_value,
    require,
    seal,
    verify_snapshot_binding,
)
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_models import ZERO
from counterguard.snapshot_repository import read_snapshot


def _licenses(repo, binding, license_ref, expected=None):
    values = []
    for manifest in binding.trees.values():
        pin = next((p for p in manifest.files if p.path == license_ref), None)
        require(
            pin is not None and manifest.sizes[license_ref] > 0,
            "external_snapshot_license_missing",
        )
        values.append(pin.content_digest)
    require(len(set(values)) == 1, "external_snapshot_license_changed_between_roles")
    if expected is not None:
        require(values[0] == expected, "external_snapshot_license_pin_changed")
    return values[0]


def issue_external_snapshot_review(
    repo,
    binding_path,
    *,
    repository_url,
    license_ref,
    reason,
    output,
    runner_id="root-pytest8",
    timeout=10.0,
):
    """Trusted operator action, not repository ownership or semantic attestation."""
    binding = verify_snapshot_binding(repo, binding_path)
    require(reason.strip(), "external_snapshot_review_reason_required")
    license_digest = _licenses(repo, binding, license_ref)
    _, files = read_snapshot(repo, binding.head_commit, budget=binding.budget)
    require(files[license_ref].strip(), "external_snapshot_license_missing")
    runner = resolve_runner(runner_id=runner_id, image_digest=None)
    require(runner.profile == "root-pytest8.v1", "snapshot_runner_profile_mismatch")
    value = seal(
        ExternalSnapshotReview(
            repository_url=repository_url,
            license_ref=license_ref,
            license_digest=license_digest,
            created_at=datetime.now(UTC),
            reason=reason,
            binding_digest=binding.artifact_digest,
            runner=runner,
            budget=binding.budget,
            timeout_seconds=timeout,
            policy_digest=digest_json_artifact(DockerPolicyV1()),
            implementation_digests=inspection_implementation_digests(),
            artifact_digest=ZERO,
        )
    )
    write_immutable(Path(output), canonical_json_bytes(value))
    return value


def verify_external_snapshot_review(repo, binding_path, review_path, *, trusted_digest):
    require(trusted_digest is not None, "snapshot_independent_trusted_anchor_required")
    binding = verify_snapshot_binding(repo, binding_path)
    review = read_value(review_path, ExternalSnapshotReview, expected_digest=trusted_digest)
    require(
        review.binding_digest == binding.artifact_digest
        and review.budget == binding.budget
        and review.implementation_digests == inspection_implementation_digests()
        and review.policy_digest == digest_json_artifact(DockerPolicyV1()),
        "external_snapshot_review_context_mismatch",
    )
    require(
        resolve_runner(runner_id=review.runner.runner_id, image_digest=None) == review.runner,
        "snapshot_runner_review_changed",
    )
    _licenses(repo, binding, review.license_ref, review.license_digest)
    return binding, review


@dataclass(frozen=True)
class ExternalSnapshotSession(SnapshotSession):
    """Separate concrete authority; old fixture parsers retain their old purpose."""

    _AUTHORIZATION = ExternalSnapshotAuthorization
    _EVIDENCE = ExternalSnapshotEvidence
    _GUARD = ExternalSnapshotGuard
    _CAPTURE = "external_snapshot_capture"
    _GUARD_CHECK = "external_snapshot_guard_check"
    _PURPOSES = frozenset({_CAPTURE, _GUARD_CHECK})
    _FAILURE_SCHEMA = "external-snapshot-failure.v1"

    def context(self):
        return verify_external_snapshot_review(
            self.repo, self.binding_path, self.review_path, trusted_digest=self.trusted_digest
        )

    def replay(self, *args, **kwargs):
        require(False, "external_snapshot_requires_independent_comparison_review")

    def verify_replay(self, *args, **kwargs):
        require(False, "external_snapshot_requires_independent_comparison_review")
