"""Adversarial bounded Git protocol checks; no real process is started."""

import hashlib
import time

import pytest

from evidenceguard import repository


def oid(body):
    framed = b"blob " + str(len(body)).encode() + b"\0" + body
    return hashlib.sha1(framed, usedforsecurity=False).hexdigest()


def test_batch_preserves_empty_binary_and_header_like_content(monkeypatch, tmp_path):
    values = (b"", b"\x00binary\r\n", b"\n" + b"a" * 40 + b" blob 999\n")
    data = {oid(value): value for value in values}
    ids = tuple(sorted(data))
    headers = b"".join(f"{key} blob {len(data[key])}\n".encode() for key in ids)
    bodies = b"".join(f"{key} blob {len(data[key])}\n".encode() + data[key] + b"\n" for key in ids)
    calls = []

    def fake_git(*args, **kwargs):
        calls.append(args[-1])
        assert kwargs["input_data"] == ("\n".join(ids) + "\n").encode()
        return headers if args[-1] == "--batch-check" else bodies

    monkeypatch.setattr(repository, "_git", fake_git)
    actual = repository._batch_blobs(
        tmp_path, tmp_path, (*reversed(ids), ids[0]), deadline=time.monotonic() + 30
    )
    assert actual == data
    assert calls == ["--batch-check", "--batch"]


@pytest.mark.parametrize("mutation", ["hash", "truncated", "trailing", "header"])
def test_batch_rejects_body_tampering_after_size_precheck(monkeypatch, tmp_path, mutation):
    body = b"abc"
    key = oid(body)
    header = f"{key} blob 3\n".encode()
    output = header + body + b"\n"
    if mutation == "hash":
        output = header + b"xyz\n"
    elif mutation == "truncated":
        output = output[:-2]
    elif mutation == "trailing":
        output += b"unexpected"
    else:
        output = output.replace(b"blob 3", b"blob 4")
    monkeypatch.setattr(
        repository, "_git", lambda *a, **k: header if a[-1] == "--batch-check" else output
    )
    with pytest.raises(repository.RepositoryProblem) as error:
        repository._batch_blobs(tmp_path, tmp_path, (key,), deadline=time.monotonic() + 30)
    if mutation == "hash":
        assert error.value.code == "git_object_integrity" and error.value.rejected


@pytest.mark.parametrize("size", [repository.BLOB_LIMIT + 1, -1])
def test_batch_rejects_bad_sizes_before_reading_bodies(monkeypatch, tmp_path, size):
    key = oid(b"abc")
    calls = []

    def fake_git(*args, **kwargs):
        calls.append(args[-1])
        return f"{key} blob {size}\n".encode()

    monkeypatch.setattr(repository, "_git", fake_git)
    with pytest.raises(repository.RepositoryProblem):
        repository._batch_blobs(tmp_path, tmp_path, (key,), deadline=time.monotonic() + 30)
    assert calls == ["--batch-check"]


def test_batch_total_budget_applies_across_both_revisions(monkeypatch, tmp_path):
    ids = tuple(f"{index:040x}" for index in range(9))
    calls = []

    def fake_git(*args, **kwargs):
        calls.append(args[-1])
        return b"".join(f"{key} blob {repository.BLOB_LIMIT}\n".encode() for key in ids)

    monkeypatch.setattr(repository, "_git", fake_git)
    with pytest.raises(repository.RepositoryProblem, match="blob_budget"):
        repository._batch_blobs(tmp_path, tmp_path, ids, deadline=time.monotonic() + 30)
    assert calls == ["--batch-check"]
