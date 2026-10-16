"""Exercise the trusted CI example locally, including actual Docker and reporting."""

import json
import os

import pytest

from scripts.run_ci_fixture import run_fixture

pytestmark = [pytest.mark.slow, pytest.mark.docker]


def test_active_ci_fixture_fails_and_preserves_safe_summary(tmp_path):
    if not os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST"):
        pytest.skip("set COUNTERGUARD_RUNNER_IMAGE_DIGEST to opt in to reviewed Docker checks")
    output = tmp_path / "ci"
    assert run_fixture(output, "active-regression") == 1
    report = json.loads((output / "verify/report.json").read_bytes())
    public = json.loads((output / "public/summary.json").read_bytes())
    assert public["counts"] == report["counts"]
    assert public["counts"]["blocking_violations"] == 1
    assert public["counts"]["executions"] == 1
    assert public["exit_code"] == report["exit_code"] == 1
    assert set(p.name for p in (output / "public").iterdir()) == {"summary.json", "summary.md"}
    assert "--network=none" in report["rows"][0]["run"]["argv"]
