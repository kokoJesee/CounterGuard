"""Atomic immutable-file publication shared by pipeline artifacts."""

import os
import uuid
from pathlib import Path

from evidenceguard.errors import ArtifactIntegrityError


def write_immutable(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ArtifactIntegrityError(f"Immutable artifact conflict: {path.name}") from None
    finally:
        temporary.unlink(missing_ok=True)
