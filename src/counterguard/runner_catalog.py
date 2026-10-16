"""Pinned reviews, bundled receipt verification and read-only image discovery."""

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.digests import digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import ArtifactRef, Digest, FrozenModel, UtcDateTime
from counterguard.runners.docker import _docker_executable, _run_bounded

CATALOG_DIGEST = "sha256:cca05916cd88669c735d8c19b427874df6c824498a6e898260461ebc99dfcd87"
CATALOG_PATH = Path(__file__).parent / "data/runner-catalog.v1.json"
RECEIPTS_PATH = Path(__file__).parent / "data/runner-receipts.v1"


class RunnerReview(FrozenModel):
    schema_version: Literal["runner-review.v1"] = "runner-review.v1"
    runner_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
    profile: Literal["root-pytest8.v1", "validators-src-pytest9.v1"]
    image_digest: Digest
    pytest_version: Literal["8.4.2", "9.0.3"]
    base_registry_digests: Annotated[tuple[str, ...], Field(min_length=1, max_length=4)]
    build_receipt_ref: ArtifactRef
    build_receipt_digest: Digest
    lock_digest: Digest
    container_source_digests: dict[ArtifactRef, Digest]
    attack_receipt_ref: ArtifactRef
    attack_receipt_digest: Digest
    attack_log_digest: Digest
    attacks_passed: Literal[4] = 4
    reviewed_at: UtcDateTime
    artifact_digest: Digest

    @model_validator(mode="after")
    def consistent_profile(self):
        expected = "8.4.2" if self.profile == "root-pytest8.v1" else "9.0.3"
        if self.pytest_version != expected:
            raise ValueError("Runner review profile/version mismatch")
        if digest_json_artifact(self) != self.artifact_digest:
            raise ValueError("Runner review digest mismatch")
        return self


class RunnerCatalog(FrozenModel):
    schema_version: Literal["runner-catalog.v1"] = "runner-catalog.v1"
    reviews: Annotated[tuple[RunnerReview, ...], Field(min_length=1, max_length=16)]
    artifact_digest: Digest


def _receipt(ref: str, expected_digest: str) -> dict:
    # The catalog, including these names and digests, must pass the code pin first.
    # Never fetch a URL or follow a repository-supplied path to acquire evidence.
    path = RECEIPTS_PATH / Path(ref).name
    with path.open("rb") as stream:
        raw = stream.read(131073)
    if len(raw) > 131072:
        raise ValueError("Runner receipt exceeds byte budget")
    value = json.loads(raw)
    if (
        not isinstance(value, dict)
        or value.get("artifact_digest") != expected_digest
        or digest_json_artifact(value) != expected_digest
    ):
        raise ValueError("Runner receipt differs from the pinned review")
    return value


def _verify_receipts(review: RunnerReview) -> None:
    build = _receipt(review.build_receipt_ref, review.build_receipt_digest)
    attacks = _receipt(review.attack_receipt_ref, review.attack_receipt_digest)
    if (
        build.get("schema_version") != "runner-build-receipt.v1"
        or attacks.get("schema_version") != "runner-attack-acceptance.v1"
        or build.get("image_id") != review.image_digest
        or attacks.get("image_id") != review.image_digest
        or build.get("lock_digest") != review.lock_digest
        or attacks.get("runner_lock_digest") != review.lock_digest
        or build.get("base_registry_digests") != list(review.base_registry_digests)
        or any(
            build.get("files", {}).get(ref) != digest
            for ref, digest in review.container_source_digests.items()
        )
        or not any(
            item.get("name") == "pytest" and item.get("version") == review.pytest_version
            for item in build.get("packages", [])
        )
        or attacks.get("accepted") is not True
        or attacks.get("exit_code") != 0
        or attacks.get("passed") != review.attacks_passed
        or attacks.get("log_digest") != review.attack_log_digest
    ):
        raise ValueError("Runner receipts contradict the pinned review")


def load_catalog() -> RunnerCatalog:
    try:
        raw = CATALOG_PATH.read_bytes()
        if len(raw) > 131072:
            raise ValueError("Runner catalog exceeds byte budget")
        catalog = RunnerCatalog.model_validate_json(raw)
        ids = [item.runner_id for item in catalog.reviews]
        images = [item.image_digest for item in catalog.reviews]
        if (
            len(ids) != len(set(ids))
            or len(images) != len(set(images))
            or catalog.artifact_digest != CATALOG_DIGEST
            or digest_json_artifact(catalog) != CATALOG_DIGEST
        ):
            raise ValueError("Runner catalog differs from the installed trust pin")
        for review in catalog.reviews:
            _verify_receipts(review)
        return catalog
    except (OSError, ValueError) as error:
        raise ArtifactIntegrityError("Installed runner review catalog is invalid") from error


def resolve_runner(*, runner_id: str | None, image_digest: str | None) -> RunnerReview:
    if bool(runner_id) == bool(image_digest):
        raise ValueError("Specify exactly one of --runner-id or --image; use runner list")
    for review in load_catalog().reviews:
        if review.runner_id == runner_id or review.image_digest == image_digest:
            return review
    raise ArtifactIntegrityError("Runner has no pinned review; use counterguard runner list")


def _availability(image_digest: str) -> str:
    try:
        result = _run_bounded(
            (_docker_executable(), "image", "inspect", "--format={{.Id}}", image_digest),
            cwd=Path.cwd(),
            timeout=5,
            stdout_limit=256,
            stderr_limit=65536,
        )
        if result.timed_out or result.overflowed:
            return "unavailable"
        if (
            result.returncode == 0
            and result.stdout.decode("ascii", errors="ignore").strip() == image_digest
        ):
            return "available"
    except OSError:
        pass
    return "unavailable"


def list_runners(*, offline: bool = False, runner_id: str | None = None) -> dict:
    catalog = load_catalog()
    if runner_id and runner_id not in {review.runner_id for review in catalog.reviews}:
        raise ValueError("Unknown reviewed runner ID")
    rows = []
    for review in catalog.reviews:
        if runner_id and review.runner_id != runner_id:
            continue
        availability = "not_checked" if offline else _availability(review.image_digest)
        rows.append(
            {
                "runner_id": review.runner_id,
                "profile": review.profile,
                "image_digest": review.image_digest,
                "review_digest": review.artifact_digest,
                "availability": availability,
                "usable": availability == "available",
                "receipt_integrity": "verified",
                "reason_code": None
                if availability == "available"
                else (
                    "local_image_not_checked" if offline else "image_missing_or_engine_unavailable"
                ),
                "provenance": review.model_dump(mode="json"),
            }
        )
    return {
        "schema_version": "runner-discovery.v2",
        "catalog_digest": catalog.artifact_digest,
        "image_execution_count": 0,
        "runners": rows,
        "exit_code": 0 if offline or any(row["usable"] for row in rows) else 3,
    }
