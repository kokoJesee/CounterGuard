"""Actual Git processes are slow; no repository Python is imported or executed."""

import pytest

from counterguard.repository import read_commit_metadata, read_committed_files
from tests.repository_support import git, sample_repository

pytestmark = pytest.mark.slow


def test_commit_metadata_reads_real_parent_and_message(tmp_path):
    base, fixed = sample_repository(tmp_path)
    metadata = read_commit_metadata(tmp_path, fixed)
    assert metadata["commit"] == fixed
    assert metadata["parents"] == (base,)
    assert metadata["message"] == "change\n"
    assert read_commit_metadata(tmp_path, base)["parents"] == ()


def test_commit_metadata_ignores_worktree_and_replace_environment(tmp_path, monkeypatch):
    base, fixed = sample_repository(tmp_path)
    (tmp_path / "src/pricing.py").write_text("raise AssertionError('never execute')\n")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "alias.cat-file")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "!exit 42")
    metadata = read_commit_metadata(tmp_path, fixed)
    assert metadata["parents"] == (base,)


def test_real_batch_preserves_binary_empty_and_duplicate_blobs(tmp_path):
    sample_repository(tmp_path)
    body = bytes(range(256)) * 2000 + b"\n" + b"f" * 40 + b" blob 7\n"
    (tmp_path / "data.bin").write_bytes(body)
    (tmp_path / "same.bin").write_bytes(body)
    (tmp_path / "empty.txt").write_bytes(b"")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "binary batch fixture")
    _, files, pins = read_committed_files(tmp_path, "HEAD")
    assert files["data.bin"] == body and files["same.bin"] == body
    assert files["empty.txt"] == b""
    assert len({pin.object_id for pin in pins if pin.path.endswith(".bin")}) == 1
