"""Keep the copyable workflow inside its deliberately narrow security scope."""

import json
import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / "examples/github-actions/counterguard.yml"


def test_example_never_enables_privileged_pr_execution_or_raw_uploads():
    workflow = json.loads(WORKFLOW.read_bytes())  # JSON is also valid YAML.
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["verify"]
    assert job["runs-on"] == "ubuntu-24.04" and job["timeout-minutes"] <= 20
    steps = job["steps"]
    for step in steps:
        if "uses" in step:
            assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", step["uses"])
        assert "continue-on-error" not in step
        assert "${{" not in step.get("run", "")  # Values enter argv via env instead.
    checkout = next(x for x in steps if x.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False
    upload = next(x for x in steps if x.get("uses", "").startswith("actions/upload-artifact@"))
    assert upload["if"] == "${{ always() }}"
    assert upload["with"]["path"].splitlines() == [
        "ci-run/public/summary.json", "ci-run/public/summary.md"
    ]
    assert upload["with"]["include-hidden-files"] is False
    summary = next(x for x in steps if "GITHUB_STEP_SUMMARY" in x.get("run", ""))
    assert summary["if"] == "${{ always() }}"
    assert "REPLACE_WITH_REVIEWED" in job["env"]["CG_TOOL_SHA"]
    assert "CG_TOOL_SHA" in steps[0]["run"] and "exit 2" in steps[0]["run"]
    assert "sha256sum --check" in next(x["run"] for x in steps if "docker load" in x.get("run", ""))
