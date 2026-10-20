"""Real CLI process against tool-owned source bytes; no Git, Docker or target import."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from counterguard.digests import canonical_json_bytes
from counterguard.study_features import (
    StudyFeatureAudit,
    verify_study_feature_audit,
)
from tests.unit.test_study_features import command_fixture, context

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parents[2]


def test_real_static_cli_preserves_negative_audit_and_does_not_execute_source(tmp_path):
    _, args = command_fixture(tmp_path)
    # If a future implementation imports/executes this file, both calls fail.
    source = b"raise RuntimeError('target must not execute')\ndef target(x): return int(x)\n"
    review = context(source, source_ref="target.py")
    (tmp_path / "target.py").write_bytes(source)
    (tmp_path / "context.json").write_bytes(canonical_json_bytes(review))
    args[5] = review.artifact_digest
    args += ["--expected", "expected.json", "--output", "audit.json"]

    def run():
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/audit_study_features.py"), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )

    first = run()
    assert first.returncode == 0, first.stderr
    raw = (tmp_path / "audit.json").read_bytes()
    audit = StudyFeatureAudit.model_validate_json(raw)
    assert audit.matched and json.loads(first.stdout)["artifact_digest"] == audit.artifact_digest
    verify_study_feature_audit(audit, source, review, context_anchor=review.artifact_digest)
    second = run()
    assert second.returncode == 0, second.stderr
    assert second.stdout == first.stdout
    assert (tmp_path / "audit.json").read_bytes() == raw

    manual = json.loads((tmp_path / "expected.json").read_bytes())
    manual["ast_features"] = []
    (tmp_path / "expected.json").write_text(json.dumps(manual), encoding="utf-8")
    args[-1] = "negative-audit.json"
    mismatch = run()
    assert mismatch.returncode == 4, mismatch.stderr
    assert not json.loads(mismatch.stdout)["matched"]
    assert (tmp_path / "audit.json").read_bytes() == raw

    args[5] = "sha256:" + "0" * 64
    args[-1] = "rejected.json"
    invalid = run()
    assert invalid.returncode == 5, invalid.stderr
    assert json.loads(invalid.stdout)["reason_code"] == "study_feature_input_invalid"
    assert not (tmp_path / "rejected.json").exists()
