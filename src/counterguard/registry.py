"""Local immutable registrations and terminal disable events, audited before use."""

from __future__ import annotations

import getpass
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from counterguard.artifacts import write_immutable
from counterguard.compiler import verify_guard
from counterguard.digests import canonical_json_bytes, digest_file, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.evidence import verify_evidence
from counterguard.lifecycle import GuardState, LifecycleEvent, require_transition, state_from_events
from counterguard.models import ArtifactRef, Digest, Evidence, FrozenModel, Guard, UtcDateTime
from counterguard.project_config import reject_links
from counterguard.repository import RepositoryProblem
from counterguard.repository_models import RepositoryEvidence, RepositoryGuard
from counterguard.standalone_models import StandaloneEvidence, StandaloneGuard
from counterguard.storage import sqlite

ZERO = "sha256:" + "0" * 64
MAX_FACTS = 4096
_ID = re.compile(r"^grd_[A-Za-z0-9][A-Za-z0-9_-]{0,90}$")
Text = Annotated[str, Field(min_length=1, max_length=512)]


class RegistryIdentity(FrozenModel):
    schema_version: Literal["registry.v1"] = "registry.v1"
    registry_id: str
    created_at: UtcDateTime
    artifact_digest: Digest


class RegistryEntry(FrozenModel):
    schema_version: Literal["registry-entry.v1", "registry-entry.v2"] = "registry-entry.v1"
    registry_id: str
    registered_at: UtcDateTime
    source_workspace: Text
    guard_ref: ArtifactRef
    guard_file_digest: Digest
    guard: Guard | RepositoryGuard
    evidence: Evidence | RepositoryEvidence
    artifact_digest: Digest

    @model_validator(mode="after")
    def versioned_source_chain(self):
        repository_guard = isinstance(self.guard, RepositoryGuard)
        if repository_guard != isinstance(self.evidence, RepositoryEvidence):
            raise ValueError("Registry cannot mix legacy and repository provenance")
        if repository_guard != (self.schema_version == "registry-entry.v2"):
            raise ValueError("Registry entry version must match its provenance shape")
        return self


class StandaloneRegistryEntry(FrozenModel):
    """New provenance version; legacy entry serialization stays byte-compatible."""

    schema_version: Literal["registry-entry.v3"] = "registry-entry.v3"
    registry_id: str
    registered_at: UtcDateTime
    source_workspace: Text
    source_repository: Text
    guard_ref: ArtifactRef
    guard_file_digest: Digest
    guard: StandaloneGuard
    evidence: StandaloneEvidence
    artifact_digest: Digest


class RegistryEvent(FrozenModel):
    schema_version: Literal["registry-event.v1"] = "registry-event.v1"
    registry_id: str
    sequence: Annotated[int, Field(ge=1)]
    guard_id: Text
    guard_digest: Digest
    kind: Literal["registered", "disabled"]
    actor: Text
    reason: Text
    created_at: UtcDateTime
    previous_digest: Digest
    artifact_digest: Digest


@dataclass(frozen=True)
class VerifiedRegistryGuard:
    entry: RegistryEntry | StandaloneRegistryEntry
    guard: Guard | RepositoryGuard | StandaloneGuard
    evidence: Evidence | RepositoryEvidence | StandaloneEvidence
    source_facts: object = field(default=None, kw_only=True, repr=False, compare=False)


@dataclass(frozen=True)
class ReviewedRegistryGuard(VerifiedRegistryGuard):
    lifecycle_state: GuardState
    event_tip_digest: Digest


def _signed(model):
    return model.model_copy(update={"artifact_digest": digest_json_artifact(model)})


def _read(path: Path, model):
    reject_links(path)
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Registry fact exceeds size limit")
        raw = path.read_bytes()
        if model is RegistryEntry and json.loads(raw).get("schema_version") == "registry-entry.v3":
            model = StandaloneRegistryEntry
        if model is RegistryEvent and json.loads(raw).get("schema_version") == (
            "guard-lifecycle-event.v1"
        ):
            model = LifecycleEvent
        value = model.model_validate_json(raw)
        if digest_json_artifact(value) != value.artifact_digest:
            raise ValueError("Registry fact digest mismatch")
        return value
    except (OSError, ValueError, AttributeError) as error:
        raise ArtifactIntegrityError("Registry JSON fact is invalid or unavailable") from error


def _id(value: str) -> str:
    if not _ID.fullmatch(value):
        raise ValueError("Expected a bounded Guard ID")
    return value


def _text(value: str, label: str) -> str:
    if not value.strip() or len(value) > 512 or any(ord(c) < 32 for c in value):
        raise ValueError(f"Registry {label} must be nonempty bounded text")
    return value


class Registry:
    """Small local interface; no operation executes a Guard or repository code."""

    def __init__(self, root: str | Path):
        self.root = Path(root).absolute()
        reject_links(self.root)

    def _initialize(self) -> None:
        if self.root.exists() and any(self.root.iterdir()):
            return
        self.root.mkdir(parents=True, exist_ok=True)
        identity = _signed(
            RegistryIdentity(
                registry_id=uuid.uuid4().hex,
                created_at=datetime.now(UTC),
                artifact_digest=ZERO,
            )
        )
        write_immutable(self.root / "registry.json", canonical_json_bytes(identity))
        (self.root / "entries").mkdir()
        (self.root / "events").mkdir()
        sqlite.connect(self.root / "registry.sqlite3", create=True).close()

    def _facts(self):
        reject_links(self.root)
        identity = _read(self.root / "registry.json", RegistryIdentity)
        entries = {}
        events = []
        for name, model in (("entries", RegistryEntry), ("events", RegistryEvent)):
            directory = self.root / name
            reject_links(directory)
            paths = sorted(directory.iterdir())
            if len(paths) > MAX_FACTS:
                raise ArtifactIntegrityError("Registry fact limit exceeded")
            for path in paths:
                value = _read(path, model)
                if value.registry_id != identity.registry_id:
                    raise ArtifactIntegrityError("Registry identity mismatch")
                if name == "entries":
                    guard_id = _id(value.guard.guard_id)
                    if path.name != f"{guard_id}.json" or guard_id in entries:
                        raise ArtifactIntegrityError("Registry entry identity mismatch")
                    entries[guard_id] = value
                else:
                    if path.name != f"{len(events) + 1:08d}.json":
                        raise ArtifactIntegrityError("Registry event history is incomplete")
                    events.append(value)
        states = {}
        review_states = {}
        previous = ZERO
        for sequence, event in enumerate(events, 1):
            entry = entries.get(event.guard_id)
            if (
                event.sequence != sequence
                or event.previous_digest != previous
                or entry is None
                or event.guard_digest != entry.guard.artifact_digest
                or event.kind == "registered"
                and event.guard_id in states
                or event.kind == "disabled"
                and states.get(event.guard_id) != "enabled"
                or event.kind == "transitioned"
                and (
                    states.get(event.guard_id) != "enabled"
                    or event.before != review_states.get(event.guard_id)
                    or event.evidence_digest != entry.evidence.artifact_digest
                )
            ):
                raise ArtifactIntegrityError("Registry state history contradicts its facts")
            if event.kind == "registered":
                states[event.guard_id] = "enabled"
                review_states[event.guard_id] = GuardState.CANDIDATE
            elif event.kind == "disabled":
                states[event.guard_id] = "disabled"
            else:
                review_states[event.guard_id] = event.after
            previous = event.artifact_digest
        if set(entries) != set(states):
            raise ArtifactIntegrityError("Registry has an incomplete registration")
        return identity, entries, events, states

    @contextmanager
    def _transaction(self, *, writable=False):
        reject_links(self.root / "registry.sqlite3")
        connection = sqlite.connect(self.root / "registry.sqlite3", writable=writable)
        try:
            connection.execute("BEGIN IMMEDIATE" if writable else "BEGIN")
            facts = self._facts()
            _, entries, events, _ = facts
            sqlite.require_matches(
                connection,
                [(key, canonical_json_bytes(value)) for key, value in sorted(entries.items())],
                [(event.sequence, canonical_json_bytes(event)) for event in events],
            )
            yield connection, facts
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            raise ArtifactIntegrityError("Registry index transaction failed") from error
        finally:
            connection.close()

    def _append(self, connection, identity, entry, events, kind, *, actor, reason):
        if len(events) >= MAX_FACTS:
            raise ArtifactIntegrityError("Registry event limit exceeded")
        event = _signed(
            RegistryEvent(
                registry_id=identity.registry_id,
                sequence=len(events) + 1,
                guard_id=entry.guard.guard_id,
                guard_digest=entry.guard.artifact_digest,
                kind=kind,
                actor=_text(actor, "actor"),
                reason=_text(reason, "reason"),
                created_at=datetime.now(UTC),
                previous_digest=events[-1].artifact_digest if events else ZERO,
                artifact_digest=ZERO,
            )
        )
        raw = canonical_json_bytes(event)
        write_immutable(self.root / f"events/{event.sequence:08d}.json", raw)
        connection.execute("INSERT INTO events VALUES (?, ?)", (event.sequence, raw))

    def add(
        self, guard_path: str | Path, *, cwd: str | Path, repo: Path | None = None
    ) -> RegistryEntry | StandaloneRegistryEntry:
        workspace = Path(cwd).absolute()
        reject_links(workspace)
        path = Path(guard_path)
        path = path if path.is_absolute() else workspace / path
        reject_links(path)
        path = path.resolve(strict=True)
        from counterguard.standalone_capture import _file

        raw = _file(workspace, path.relative_to(workspace.resolve(strict=True)).as_posix())
        standalone = json.loads(raw).get("schema_version") == "guard.v3"
        if standalone:
            if repo is None:
                raise ValueError("Standalone Guard registration requires --repo for Git provenance")
            from counterguard.standalone_guard import verify_standalone_guard_chain

            try:
                guard, source_facts = verify_standalone_guard_chain(repo, path, cwd=workspace)
            except RepositoryProblem as error:
                raise ArtifactIntegrityError("Standalone Git provenance unavailable") from error
            evidence = source_facts[1]
        else:
            guard = verify_guard(path, cwd=workspace)
            evidence = verify_evidence(workspace / guard.source_evidence_ref, cwd=workspace)
        guard_id = _id(guard.guard_id)
        self._initialize()
        with self._transaction(writable=True) as (connection, facts):
            identity, entries, events, _ = facts
            if guard_id in entries:
                entry = entries[guard_id]
                if entry.guard.artifact_digest != guard.artifact_digest:
                    raise ArtifactIntegrityError("Registry Guard ID already has a different digest")
                self._verify_source(entry)
                return entry
            if len(entries) >= MAX_FACTS:
                raise ArtifactIntegrityError("Registry entry limit exceeded")
            entry_type = StandaloneRegistryEntry if standalone else RegistryEntry
            source_version = (
                {"source_repository": str(repo.resolve(strict=True))}
                if standalone
                else {
                    "schema_version": "registry-entry.v2"
                    if isinstance(guard, RepositoryGuard)
                    else "registry-entry.v1"
                }
            )
            entry = _signed(
                entry_type(
                    **source_version,
                    registry_id=identity.registry_id,
                    registered_at=datetime.now(UTC),
                    source_workspace=str(workspace.resolve(strict=True)),
                    guard_ref=path.relative_to(workspace.resolve(strict=True)).as_posix(),
                    guard_file_digest=digest_file(path),
                    guard=guard,
                    evidence=evidence,
                    artifact_digest=ZERO,
                )
            )
            self._verify_source(entry)
            raw = canonical_json_bytes(entry)
            if len(raw) > 2 * 1024 * 1024:
                raise ArtifactIntegrityError("Registry entry exceeds its reader byte budget")
            write_immutable(self.root / f"entries/{guard_id}.json", raw)
            connection.execute("INSERT INTO registrations VALUES (?, ?)", (guard_id, raw))
            self._append(
                connection,
                identity,
                entry,
                events,
                "registered",
                actor="local-operator" if standalone else getpass.getuser(),
                reason="verified source-chain registration",
            )
            return entry

    def _verify_source(self, entry: RegistryEntry) -> VerifiedRegistryGuard:
        workspace = Path(entry.source_workspace)
        if not workspace.is_absolute():
            raise ArtifactIntegrityError("Registry source workspace must be absolute")
        reject_links(workspace / entry.guard_ref)
        source_facts = None
        try:
            if isinstance(entry, StandaloneRegistryEntry):
                from counterguard.standalone_guard import verify_standalone_guard_chain

                repo = Path(entry.source_repository)
                if not repo.is_absolute():
                    raise ArtifactIntegrityError("Registry source repository must be absolute")
                guard, source_facts = verify_standalone_guard_chain(
                    repo, workspace / entry.guard_ref, cwd=workspace
                )
                evidence = source_facts[1]
            else:
                guard = verify_guard(workspace / entry.guard_ref, cwd=workspace)
                evidence = verify_evidence(workspace / guard.source_evidence_ref, cwd=workspace)
            if (
                guard != entry.guard
                or evidence != entry.evidence
                or digest_file(workspace / entry.guard_ref) != entry.guard_file_digest
            ):
                raise ArtifactIntegrityError("Registry source chain differs from registration")
        except (OSError, ValueError, RepositoryProblem) as error:
            raise ArtifactIntegrityError(
                "Registry source chain is invalid or unavailable"
            ) from error
        return VerifiedRegistryGuard(entry, guard, evidence, source_facts=source_facts)

    def _view(self, entry, events, state, *, with_evidence=False):
        try:
            self._verify_source(entry)
            integrity = "verified"
        except (ArtifactIntegrityError, OSError, ValueError):
            integrity = "invalid"
        value = {
            "guard_id": entry.guard.guard_id,
            "guard_digest": entry.guard.artifact_digest,
            "entry_digest": entry.artifact_digest,
            "source_evidence_id": entry.evidence.evidence_id,
            "source_evidence_ref": entry.guard.source_evidence_ref,
            "source_evidence_digest": entry.evidence.artifact_digest,
            "status": state,
            "lifecycle_state": state_from_events(events, entry.guard.guard_id).value,
            "integrity": integrity,
            "schedulable": state == "enabled"
            and integrity == "verified"
            and state_from_events(events, entry.guard.guard_id) is not GuardState.RETIRED,
            "verification_schedulable": state == "enabled"
            and integrity == "verified"
            and state_from_events(events, entry.guard.guard_id)
            in {GuardState.SHADOW, GuardState.ACTIVE},
            "reason_code": "source_chain_invalid" if integrity == "invalid" else None,
            "events": [
                e.model_dump(mode="json") for e in events if e.guard_id == entry.guard.guard_id
            ],
        }
        if with_evidence:
            value.update(
                guard=entry.guard.model_dump(mode="json"),
                evidence=entry.evidence.model_dump(mode="json"),
            )
        if isinstance(entry, StandaloneRegistryEntry):
            value["source_profile"] = "standalone-literals-docker.v1"
        return value

    def list(self) -> list[dict]:
        with self._transaction() as (_, (_, entries, events, states)):
            return [
                self._view(entry, events, states[key]) for key, entry in sorted(entries.items())
            ]

    def show(self, guard_id: str, *, with_evidence=False) -> dict:
        guard_id = _id(guard_id)
        with self._transaction() as (_, (_, entries, events, states)):
            if guard_id not in entries:
                raise ValueError("Registry Guard ID is not registered")
            return self._view(
                entries[guard_id], events, states[guard_id], with_evidence=with_evidence
            )

    def disable(self, guard_id: str, *, reason: str, actor: str | None = None) -> dict:
        guard_id = _id(guard_id)
        reason = _text(reason, "reason")
        actor = _text(actor or getpass.getuser(), "actor")
        with self._transaction(writable=True) as (connection, facts):
            identity, entries, events, states = facts
            if guard_id not in entries:
                raise ValueError("Registry Guard ID is not registered")
            if states[guard_id] != "disabled":
                self._append(
                    connection,
                    identity,
                    entries[guard_id],
                    events,
                    "disabled",
                    actor=actor,
                    reason=reason,
                )
        return self.show(guard_id)

    def resolve_for_execution(self, guard_id: str) -> VerifiedRegistryGuard:
        guard_id = _id(guard_id)
        with self._transaction() as (_, (_, entries, events, states)):
            if guard_id not in entries:
                raise ValueError("Registry Guard ID is not registered")
            if states[guard_id] == "disabled":
                raise ArtifactIntegrityError("Registry Guard is disabled")
            if state_from_events(events, guard_id) is GuardState.RETIRED:
                raise ArtifactIntegrityError("Registry Guard is retired")
            return self._verify_source(entries[guard_id])

    def resolve_for_verification(self, guard_id: str) -> ReviewedRegistryGuard:
        """Audit provenance and its review state in one Registry transaction."""
        guard_id = _id(guard_id)
        with self._transaction() as (_, (_, entries, events, states)):
            if guard_id not in entries:
                raise ValueError("Registry Guard ID is not registered")
            state = state_from_events(events, guard_id)
            if states[guard_id] != "enabled" or state not in {GuardState.SHADOW, GuardState.ACTIVE}:
                raise ArtifactIntegrityError("Registry verification requires enabled Shadow/Active")
            verified = self._verify_source(entries[guard_id])
            tip = next(
                event.artifact_digest for event in reversed(events) if event.guard_id == guard_id
            )
            return ReviewedRegistryGuard(
                verified.entry,
                verified.guard,
                verified.evidence,
                state,
                tip,
                source_facts=verified.source_facts,
            )

    def transition(
        self, guard_id: str, *, to: GuardState, reason: str, actor: str = "local-operator"
    ) -> dict:
        """Append a review decision; enabled is never an implicit Active promotion."""
        guard_id = _id(guard_id)
        to = GuardState(to)
        reason, actor = _text(reason, "reason"), _text(actor, "actor")
        with self._transaction(writable=True) as (connection, facts):
            identity, entries, events, states = facts
            if guard_id not in entries:
                raise ValueError("Registry Guard ID is not registered")
            if states[guard_id] == "disabled":
                raise ArtifactIntegrityError("Registry Guard is disabled")
            before = state_from_events(events, guard_id)
            require_transition(before, to)
            entry = entries[guard_id]
            # Retirement remains available when a source chain has become stale.
            if to is not GuardState.RETIRED:
                self._verify_source(entry)
            if len(events) >= MAX_FACTS:
                raise ArtifactIntegrityError("Registry event limit exceeded")
            event = _signed(
                LifecycleEvent(
                    registry_id=identity.registry_id,
                    sequence=len(events) + 1,
                    guard_id=guard_id,
                    guard_digest=entry.guard.artifact_digest,
                    evidence_digest=entry.evidence.artifact_digest,
                    before=before,
                    after=to,
                    actor=actor,
                    reason=reason,
                    created_at=datetime.now(UTC),
                    previous_digest=events[-1].artifact_digest,
                    artifact_digest=ZERO,
                )
            )
            raw = canonical_json_bytes(event)
            write_immutable(self.root / f"events/{event.sequence:08d}.json", raw)
            connection.execute("INSERT INTO events VALUES (?, ?)", (event.sequence, raw))
        return self.show(guard_id)

    def rebuild_index(self) -> None:
        """Explicit recovery from all JSON facts, including terminal disable history."""
        _, entries, events, _ = self._facts()
        database = self.root / "registry.sqlite3"
        reject_links(database)
        if database.exists():
            raise ArtifactIntegrityError("Rebuild requires a missing index; preserve damaged DB")
        connection = sqlite.connect(database, create=True, writable=True)
        try:
            with connection:
                connection.executemany(
                    "INSERT INTO registrations VALUES (?, ?)",
                    [(key, canonical_json_bytes(value)) for key, value in sorted(entries.items())],
                )
                connection.executemany(
                    "INSERT INTO events VALUES (?, ?)",
                    [(event.sequence, canonical_json_bytes(event)) for event in events],
                )
        finally:
            connection.close()
