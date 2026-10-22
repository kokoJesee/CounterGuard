"""Pinned fixture roster and explicit command gates; no target or subprocess execution."""

import json

import pytest
from pydantic import ValidationError

from counterguard.digests import digest_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.snapshot_admission import ZERO
from scripts.run_snapshot_study import FixtureRoster, load_sessions, main


def test_roster_hash_is_an_independent_anchor_checked_before_repository_access(
    tmp_path, monkeypatch
):
    import scripts.run_snapshot_study as command

    raw = b'{"schema_version":"snapshot-study-cli-roster.v1","sessions":[]}'
    (tmp_path / "roster.json").write_bytes(raw)
    monkeypatch.setattr(command, "SnapshotSession", lambda *a, **k: pytest.fail("source accessed"))
    with pytest.raises(ArtifactIntegrityError, match="roster_anchor"):
        load_sessions(tmp_path, "roster.json", ZERO)
    with pytest.raises(ValidationError):
        load_sessions(tmp_path, "roster.json", digest_bytes(raw))


def test_external_purpose_or_extra_execution_flags_do_not_become_a_fixture_roster():
    for extra in (
        {"purpose": "reviewed_external_snapshot_observation_only"},
        {"execution_allowed": True},
        {"holdout_root": "sealed"},
    ):
        with pytest.raises(ValidationError):
            FixtureRoster.model_validate_json(
                json.dumps(
                    {"schema_version": "snapshot-study-cli-roster.v1", "sessions": [], **extra}
                )
            )


def test_missing_eval_anchor_is_a_usage_error_before_roster_is_read(tmp_path, monkeypatch):
    import scripts.run_snapshot_study as command

    monkeypatch.setattr(command, "load_sessions", lambda *a, **k: pytest.fail("roster opened"))
    with pytest.raises(SystemExit) as error:
        main(
            [
                "evaluate",
                "--workspace",
                str(tmp_path),
                "--roster",
                "missing.json",
                "--roster-digest",
                ZERO,
                "--plan",
                "eval.json",
                "--review",
                "review.json",
                "--output",
                "result",
            ]
        )
    assert error.value.code == 2


def test_fit_delegation_keeps_holdout_out_of_choices(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        main(["fit", "--help"])
    assert error.value.code == 0
    help_text = capsys.readouterr().out
    assert (
        "--phase {initial,refined}" in help_text
        and "holdout" not in help_text.split("options:")[-1]
    )
