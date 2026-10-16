"""The requested manifest is a real compare constraint, not an ignored CLI flag."""

import sys

import pytest

from counterguard.digests import canonical_json_bytes
from counterguard.pilot_inputs import read_fact, signed
from scripts import run_pilot


@pytest.mark.parametrize("matches", [False, True])
def test_compare_checks_requested_manifest_before_verification(tmp_path, monkeypatch, matches):
    monkeypatch.chdir(tmp_path)
    manifest = signed({"schema_version": "test-only-manifest", "head": "one"})
    (tmp_path / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    wanted = manifest["artifact_digest"] if matches else "sha256:" + "f" * 64
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_bytes(canonical_json_bytes(signed({"manifest_digest": wanted})))
    calls = []

    def compare(*args):
        calls.append(args)
        return signed({"accepted": True})

    monkeypatch.setattr(run_pilot, "compare_replays", compare)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_pilot.py",
            "--manifest",
            "manifest.json",
            "--phase",
            "compare",
            "--first",
            "a.json",
            "--second",
            "b.json",
            "--output",
            "out",
        ],
    )
    assert run_pilot.main() == (0 if matches else 4)
    result = read_fact(tmp_path / "out/report.json")
    assert result["accepted"] is matches
    assert bool(calls) is matches
    if not matches:
        assert "requested manifest" in result["reason"]
        assert result["next_stage_allowed"] is False
