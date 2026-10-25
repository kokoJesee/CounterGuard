from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from counterguard.digests import digest_bytes
from counterguard.scope_v2_readiness import (
    ReadinessCounts,
    ReadinessError,
    ReadinessInput,
    ReadinessStage,
    ScopeV2Readiness,
    dump_readiness,
    seal_readiness,
    verify_readiness,
)

ZERO = "sha256:" + "0" * 64


def _repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "facts.md").write_text("facts\n", encoding="utf-8")
    return root


def _value(root, *, complete=False):
    (root / "facts.md").write_text("facts\n", encoding="utf-8")
    commit = "a" * 40
    status = "passed" if complete else "blocked"
    stages = []
    for name in (
        "specification",
        "feasibility",
        "formal_contracts",
        "real_data",
        "freeze",
        "train_fit",
    ):
        stages.append(
            ReadinessStage(
                name=name,
                status="passed" if complete or name == "specification" else status,
                reason_codes=() if complete or name == "specification" else ("insufficient_data",),
            )
        )
    counts = ReadinessCounts(
        candidate_records=13,
        verified_source_repairs=2,
        external_observation_pairs=2,
        formally_admitted_scenarios=1 if complete else 0,
        frozen_train_rows=2 if complete else 0,
        frozen_holdout_rows=1 if complete else 0,
        fitted_guard_slots=1 if complete else 0,
    )
    return seal_readiness(
        ScopeV2Readiness(
            created_at=datetime(2026, 10, 25, tzinfo=UTC),
            source_commit=commit,
            inputs=(
                ReadinessInput(
                    ref="facts.md",
                    content_digest=digest_bytes((root / "facts.md").read_bytes()),
                    role="data_card",
                ),
            ),
            stages=tuple(stages),
            counts=counts,
            outcome="study_fit_complete" if complete else "insufficient_data",
            holdout_exposure="known" if complete else "not_created",
            next_phase_allowed=complete,
            artifact_digest=ZERO,
        )
    )


def _git_commit_exists(monkeypatch):
    monkeypatch.setattr(
        "counterguard.scope_v2_readiness.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )


def test_incomplete_readiness_verifies_but_cannot_open_next_phase(tmp_path, monkeypatch):
    _git_commit_exists(monkeypatch)
    repo_root = _repo(tmp_path)
    value = _value(repo_root)
    path = tmp_path / "readiness.json"
    path.write_bytes(dump_readiness(value))
    verified = verify_readiness(repo_root, path)
    assert verified.outcome == "insufficient_data"
    assert verified.next_phase_allowed is False


def test_readiness_rejects_false_completion_without_formal_data(tmp_path):
    repo_root = _repo(tmp_path)
    value = _value(repo_root)
    data = value.model_dump()
    data["outcome"] = "study_fit_complete"
    data["next_phase_allowed"] = True
    with pytest.raises(ValueError, match="every readiness stage"):
        ScopeV2Readiness.model_validate(data)


def test_readiness_rejects_tampered_pinned_fact(tmp_path, monkeypatch):
    _git_commit_exists(monkeypatch)
    repo_root = _repo(tmp_path)
    value = _value(repo_root)
    path = tmp_path / "readiness.json"
    path.write_bytes(dump_readiness(value))
    original = (repo_root / "facts.md").read_bytes()
    try:
        (repo_root / "facts.md").write_text("changed\n", encoding="utf-8")
        with pytest.raises(ReadinessError, match="input_digest"):
            verify_readiness(repo_root, path)
    finally:
        (repo_root / "facts.md").write_bytes(original)


def test_readiness_rejects_self_digest_tamper(tmp_path, monkeypatch):
    _git_commit_exists(monkeypatch)
    repo_root = _repo(tmp_path)
    value = _value(repo_root)
    data = json.loads(dump_readiness(value))
    data["counts"]["candidate_records"] += 1
    path = tmp_path / "readiness.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ReadinessError, match="artifact_digest"):
        verify_readiness(repo_root, path)
