"""Rebuildable SQLite index with append-only state mirrors."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from evidenceguard.errors import ArtifactIntegrityError

SCHEMA = """
CREATE TABLE registrations (
    guard_id TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE events (
    sequence INTEGER PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TRIGGER registrations_no_update BEFORE UPDATE ON registrations
BEGIN SELECT RAISE(ABORT, 'registrations are immutable'); END;
CREATE TRIGGER registrations_no_delete BEFORE DELETE ON registrations
BEGIN SELECT RAISE(ABORT, 'registrations are immutable'); END;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
PRAGMA user_version = 1;
"""


def connect(path: Path, *, create: bool = False, writable: bool = False) -> sqlite3.Connection:
    if not create and not path.is_file():
        raise ArtifactIntegrityError("Registry index is missing; explicitly rebuild it")
    mode = "rwc" if create else "rw" if writable else "ro"
    try:
        connection = sqlite3.connect(path.as_uri() + f"?mode={mode}", uri=True, timeout=5)
        connection.enable_load_extension(False)
        connection.execute("PRAGMA trusted_schema=OFF")
        if create:
            connection.executescript(SCHEMA)
        if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
            connection.close()
            raise ArtifactIntegrityError("Registry index version is unsupported")
        return connection
    except sqlite3.Error as error:
        raise ArtifactIntegrityError("Registry index is unavailable or corrupt") from error


def require_matches(connection, registrations: list[tuple], events: list[tuple]) -> None:
    try:
        if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ArtifactIntegrityError("Registry index integrity check failed")
        actual_entries = connection.execute(
            "SELECT guard_id, payload FROM registrations ORDER BY guard_id"
        ).fetchall()
        actual_events = connection.execute(
            "SELECT sequence, payload FROM events ORDER BY sequence"
        ).fetchall()
        if actual_entries != registrations or actual_events != events:
            raise ArtifactIntegrityError("Registry index disagrees with immutable JSON facts")
    except sqlite3.Error as error:
        raise ArtifactIntegrityError("Registry index is unavailable or corrupt") from error
