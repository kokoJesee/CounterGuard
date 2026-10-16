"""Pinned review provenance plus read-only local image discovery, never image execution."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.digests import digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import ArtifactRef, Digest, FrozenModel, UtcDateTime
from counterguard.runners.docker import _docker_executable, _run_bounded

CATALOG_DIGEST = "sha256:cca05916cd88669c735d8c19b427874df6c824498a6e898260461ebc99dfcd87"
CATALOG_PATH = Path(__file__).parent / "data/runner-catalog.v1.json"


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
                "reason_code": None
                if availability == "available"
                else (
                    "local_image_not_checked" if offline else "image_missing_or_engine_unavailable"
                ),
                "provenance": review.model_dump(mode="json"),
            }
        )
    return {
        "schema_version": "runner-discovery.v1",
        "catalog_digest": catalog.artifact_digest,
        "image_execution_count": 0,
        "runners": rows,
        "exit_code": 0 if offline or any(row["usable"] for row in rows) else 3,
    }
