"""The copyable Beta workflow has no privileged PR path or unpinned tool delivery."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_beta_workflow_has_closed_permissions_pins_hashes_and_public_outputs():
    value = json.loads((ROOT / "examples/github-actions/counterguard-beta.yml").read_bytes())
    assert set(value["on"]) == {"workflow_dispatch"}
    assert value["permissions"] == {"contents": "read"}
    job = value["jobs"]["verify"]
    assert job["runs-on"] == "ubuntu-24.04" and job["timeout-minutes"] <= 25
    env = job["env"]
    assert re.fullmatch("[0-9a-f]{40}", env["CG_TOOL_SHA"])
    for key in ("CG_WHEEL_SHA256", "CG_ARCHIVE_SHA256", "CG_REQUIREMENTS_SHA256"):
        assert re.fullmatch("[0-9a-f]{64}", env[key])
    assert (
        env["CG_REQUIREMENTS_SHA256"]
        == hashlib.sha256((ROOT / "requirements/runner.lock.txt").read_bytes()).hexdigest()
    )
    steps = job["steps"]
    for step in steps:
        assert "continue-on-error" not in step and "${{" not in step.get("run", "")
        if "uses" in step:
            assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", step["uses"])
    checkout = steps[0]["with"]
    assert checkout["fetch-depth"] == 0 and checkout["persist-credentials"] is False
    install = next(step["run"] for step in steps if "docker load" in step.get("run", ""))
    assert "sha256sum --check" in install and "--only-binary=:all: --require-hashes" in install
    assert "docker build" not in install and "pip install './tool" not in install
    upload = next(step for step in steps if "upload-artifact@" in step.get("uses", ""))
    assert upload["if"] == "${{ always() }}" and upload["with"]["include-hidden-files"] is False
    assert upload["with"]["path"].splitlines() == [
        "ci-run/public/summary.json",
        "ci-run/public/summary.md",
    ]
    summary = next(step for step in steps if "GITHUB_STEP_SUMMARY" in step.get("run", ""))
    assert summary["if"] == "${{ always() }}"
