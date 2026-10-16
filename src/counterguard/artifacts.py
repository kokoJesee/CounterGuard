"""Atomic immutable-file publication shared by pipeline artifacts."""

import os
import uuid
from pathlib import Path

from counterguard.errors import ArtifactIntegrityError
from counterguard.path_limits import require_publication


def write_immutable(path: Path, data: bytes) -> None:
    require_publication(path)
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
