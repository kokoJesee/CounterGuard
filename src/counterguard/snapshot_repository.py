"""Independent, incrementally bounded full Git tree reader for research snapshots."""

import hashlib
import tempfile
import time
from pathlib import Path
from typing import Literal

from pydantic import Field

from counterguard.digests import digest_bytes, digest_json_artifact
from counterguard.models import Digest, FrozenModel
from counterguard.project_config import repository_path
from counterguard.repository import (
    FilePin,
    RepositoryProblem,
    _check_mode,
    _git,
    _metadata,
    _prepare_metadata,
    read_repository,
)
from counterguard.standalone_contracts import CommitId

BLOB_BYTES = 8 * 1024 * 1024
TREE_BYTES = 128 * 1024 * 1024
FILE_COUNT = 2048
READ_SECONDS = 30


class SnapshotBudget(FrozenModel):
    blob_bytes: int = Field(default=BLOB_BYTES, ge=1, le=BLOB_BYTES, strict=True)
    tree_bytes: int = Field(default=TREE_BYTES, ge=1, le=TREE_BYTES, strict=True)
    file_count: int = Field(default=FILE_COUNT, ge=1, le=FILE_COUNT, strict=True)


SNAPSHOT_BUDGET = SnapshotBudget()


class SnapshotManifest(FrozenModel):
    schema_version: Literal["research-snapshot-manifest.v1"] = "research-snapshot-manifest.v1"
    commit: CommitId
    budget: SnapshotBudget
    total_bytes: int = Field(ge=0, le=TREE_BYTES, strict=True)
    files: tuple[FilePin, ...]
    sizes: dict[str, int]
    artifact_digest: Digest


def _entries(raw, budget):
    pending, seen = [], set()
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        if len(pending) >= budget.file_count:
            raise RepositoryProblem("snapshot_file_budget_exceeded")
        try:
            header, path = entry.split(b"\t", 1)
            mode, kind, oid = header.decode("ascii").split()
            _check_mode(mode)
            ref = repository_path(path.decode("utf-8"))
            if kind != "blob" or len(oid) != 40 or any(c not in "0123456789abcdef" for c in oid):
                raise ValueError("invalid object")
            if ref.casefold() in seen:
                raise ValueError("colliding paths")
        except (ValueError, UnicodeError) as error:
            raise RepositoryProblem("invalid_snapshot_tree", rejected=True) from error
        seen.add(ref.casefold())
        pending.append((ref, oid))
    return tuple(sorted(pending))


def _sizes(raw, pending, budget):
    oids = tuple(sorted({oid for _, oid in pending}))
    rows = raw.splitlines()
    if len(rows) != len(oids):
        raise RepositoryProblem("invalid_snapshot_headers", rejected=True)
    sizes = {}
    for expected, row in zip(oids, rows, strict=True):
        try:
            oid, kind, text = row.decode("ascii").split()
            if oid != expected or kind != "blob" or not text.isdecimal() or len(text) > 12:
                raise ValueError("header")
            size = int(text)
        except (ValueError, UnicodeError) as error:
            raise RepositoryProblem("invalid_snapshot_headers", rejected=True) from error
        if size > budget.blob_bytes:
            raise RepositoryProblem("snapshot_blob_budget_exceeded")
        sizes[oid] = size
    # Repeated blobs at different paths count repeatedly in the materialized snapshot.
    if sum(sizes[oid] for _, oid in pending) > budget.tree_bytes:
        raise RepositoryProblem("snapshot_tree_budget_exceeded")
    return sizes


def _batches(sizes):
    batch, total = [], 0
    for oid, size in sorted(sizes.items()):
        if batch and (total + size > BLOB_BYTES or len(batch) >= 64):
            yield tuple(batch)
            batch, total = [], 0
        batch.append(oid)
        total += size
    if batch:
        yield tuple(batch)


def _decode_batch(raw, oids, sizes):
    result, offset = {}, 0
    for oid in oids:
        header = f"{oid} blob {sizes[oid]}\n".encode()
        end = offset + len(header)
        body = raw[end : end + sizes[oid]]
        if (
            raw[offset:end] != header
            or raw[end + len(body) : end + len(body) + 1] != b"\n"
            or len(body) != sizes[oid]
        ):
            raise RepositoryProblem("invalid_snapshot_body", rejected=True)
        framed = b"blob " + str(len(body)).encode() + b"\0" + body
        if hashlib.sha1(framed, usedforsecurity=False).hexdigest() != oid:
            raise RepositoryProblem("git_object_integrity", rejected=True)
        result[oid], offset = body, end + len(body) + 1
    if offset != len(raw):
        raise RepositoryProblem("invalid_snapshot_trailing_data", rejected=True)
    return result


def read_snapshot(repo: Path, revision: str, *, budget=SNAPSHOT_BUDGET):
    """Hash every committed file, including media; never delete it to fit old budgets.

    Git output is consumed in <=8 MiB/64-object batches. The retained complete tree is
    bounded by 128 MiB, including duplicate paths. Existing Git fsck/object-store and
    5-second process bounds still apply; the entire operation has a 30-second budget.
    """
    deadline = time.monotonic() + READ_SECONDS
    snapshot = read_repository(repo, revision, revision)
    if snapshot.status != "ready":
        raise RepositoryProblem(snapshot.reason_codes[0], rejected=snapshot.status == "rejected")
    gitdir = Path(repo).absolute() / ".git"
    before = _metadata(gitdir)
    objects = gitdir / "objects"
    with tempfile.TemporaryDirectory(prefix="cg-snapshot-") as temporary:
        isolated = Path(temporary)
        _prepare_metadata(before, isolated)

        def git(*args, **kwargs):
            return _git(isolated, objects, *args, deadline=deadline, **kwargs)

        pending = _entries(git("ls-tree", "-r", "-z", "--full-tree", snapshot.head_commit), budget)
        oids = tuple(sorted({oid for _, oid in pending}))
        request = ("\n".join(oids) + "\n").encode() if oids else b""
        sizes = _sizes(
            git("cat-file", "--batch-check", input_data=request, limit=max(1, len(oids) * 80)),
            pending,
            budget,
        )
        bodies = {}
        for batch in _batches(sizes):
            raw = git(
                "cat-file",
                "--batch",
                input_data=("\n".join(batch) + "\n").encode(),
                limit=sum(sizes[oid] for oid in batch) + len(batch) * 81,
            )
            bodies.update(_decode_batch(raw, batch, sizes))
    if before != _metadata(gitdir) or time.monotonic() > deadline:
        raise RepositoryProblem("snapshot_changed_or_deadline_exceeded", rejected=True)
    files = {ref: bodies[oid] for ref, oid in pending}
    pins = tuple(
        FilePin(revision="head", path=ref, object_id=oid, content_digest=digest_bytes(files[ref]))
        for ref, oid in pending
    )
    manifest = SnapshotManifest(
        commit=snapshot.head_commit,
        budget=budget,
        total_bytes=sum(map(len, files.values())),
        files=pins,
        sizes={ref: len(body) for ref, body in files.items()},
        artifact_digest="sha256:" + "0" * 64,
    )
    manifest = manifest.model_copy(update={"artifact_digest": digest_json_artifact(manifest)})
    return manifest, files
