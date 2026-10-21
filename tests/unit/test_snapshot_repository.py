"""Pure boundary tests before requesting any Git blob bodies."""

import hashlib

import pytest
from pydantic import ValidationError

from counterguard.repository import BLOB_LIMIT, RepositoryProblem
from counterguard.snapshot_admission import _compatible_python
from counterguard.snapshot_repository import (
    BLOB_BYTES,
    TREE_BYTES,
    SnapshotBudget,
    _batches,
    _decode_batch,
    _entries,
    _sizes,
)

OID = "a" * 40


@pytest.mark.parametrize(
    "field,value",
    [
        ("blob_bytes", BLOB_BYTES + 1),
        ("tree_bytes", TREE_BYTES + 1),
        ("file_count", 2049),
        ("blob_bytes", 0),
        ("file_count", True),
    ],
)
def test_new_budget_can_be_tightened_but_never_widened(field, value):
    with pytest.raises(ValidationError):
        SnapshotBudget(**{field: value})
    assert BLOB_LIMIT == 1024 * 1024


@pytest.mark.parametrize(
    "path,mode",
    [
        ("../escape", "100644"),
        ("A.py\0ignored", "100644"),
        ("link", "120000"),
        ("module", "160000"),
        ("folder/.git/config", "100644"),
    ],
)
def test_unsafe_tree_entries_refuse(path, mode):
    with pytest.raises(RepositoryProblem):
        _entries(f"{mode} blob {OID}\t{path}\0".encode(), SnapshotBudget())


def test_case_alias_collision_and_count_are_not_accepted_on_windows():
    with pytest.raises(RepositoryProblem):
        _entries(
            f"100644 blob {OID}\tA.py\0".encode() + f"100644 blob {OID}\ta.py\0".encode(),
            SnapshotBudget(),
        )
    with pytest.raises(RepositoryProblem, match="snapshot_file_budget_exceeded"):
        _entries(
            f"100644 blob {OID}\ta\0".encode() + f"100644 blob {OID}\tb\0".encode(),
            SnapshotBudget(file_count=1),
        )


def test_aliases_count_against_tree_size_before_body_read():
    pending = (("a", OID), ("b", OID))
    with pytest.raises(RepositoryProblem, match="snapshot_tree_budget_exceeded"):
        _sizes(f"{OID} blob 8\n".encode(), pending, SnapshotBudget(blob_bytes=8, tree_bytes=15))
    assert _sizes(
        f"{OID} blob 8\n".encode(), pending, SnapshotBudget(blob_bytes=8, tree_bytes=16)
    ) == {OID: 8}
    with pytest.raises(RepositoryProblem, match="snapshot_blob_budget_exceeded"):
        _sizes(f"{OID} blob 9\n".encode(), pending, SnapshotBudget(blob_bytes=8))


def test_incremental_batches_and_object_hash_and_trailing_bytes():
    sizes = {f"{i:040x}": BLOB_BYTES // 2 for i in range(5)}
    assert tuple(map(len, _batches(sizes))) == (2, 2, 1)
    body = b"tool-owned fixture"
    oid = hashlib.sha1(
        b"blob " + str(len(body)).encode() + b"\0" + body, usedforsecurity=False
    ).hexdigest()
    raw = f"{oid} blob {len(body)}\n".encode() + body + b"\n"
    assert _decode_batch(raw, (oid,), {oid: len(body)}) == {oid: body}
    for corrupted in (raw + b"extra", raw[:-1], raw.replace(body, b"X" * len(body))):
        with pytest.raises(RepositoryProblem):
            _decode_batch(corrupted, (oid,), {oid: len(body)})


@pytest.mark.parametrize(
    "requirement,expected",
    [
        (None, False),
        (">=3.8", True),
        (">=3.10,<4", True),
        (">=3.14", False),
        ("~=3.8", False),
        ("==3.13.*", False),
        ("", False),
        ("!=3.13.16", False),
    ],
)
def test_python_requirement_never_guesses(requirement, expected):
    assert _compatible_python(requirement) is expected
