"""Stable SHA-256 helpers for source files and JSON artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

if TYPE_CHECKING:
    from counterguard.models import Digest


def digest_bytes(data: bytes) -> Digest:
    """Return the CounterGuard digest representation for raw bytes."""

    return cast("Digest", f"sha256:{hashlib.sha256(data).hexdigest()}")


def digest_file(path: str | Path) -> Digest:
    """Hash a file's original bytes without newline or encoding normalization."""

    return digest_bytes(Path(path).read_bytes())


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a JSON-compatible value using CounterGuard's canonical form."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    jsonable = to_jsonable_python(value)
    return json.dumps(
        jsonable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest_json_artifact(value: Mapping[str, object] | BaseModel) -> Digest:
    """Hash canonical JSON after removing its top-level self digest."""

    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    payload.pop("artifact_digest", None)
    return digest_bytes(canonical_json_bytes(payload))
