"""One real offline Demo, shared for read-only presentation and mutation checks."""

import json
import shutil
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evidenceguard.cli import app
from evidenceguard.demo import DemoReport, run_demo, verify_demo
from evidenceguard.digests import canonical_json_bytes, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.report import OutputFormat, render_report

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = "examples/demo/mvp.yaml"


@pytest.fixture(scope="module")
def demo_flow(tmp_path_factory):
    root = tmp_path_factory.mktemp("dm")
    for name in ("examples", "benchmarks", "experiments", "tests/fixtures/agent_responses"):
        shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))

    def offline(*args, **kwargs):
        pytest.fail("Default Demo must not request a network connection")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket, "create_connection", offline)
        patch.setattr(socket.socket, "connect", offline)
        # Child pytest only executes the pinned, reviewed local fixtures. This is not a sandbox.
        record = run_demo(SCENARIO, cwd=root, workspace="out")
    return root, record


@pytest.fixture
def mutable_demo(demo_flow, tmp_path_factory):
    root = tmp_path_factory.mktemp("dc")
    shutil.copytree(
        demo_flow[0],
        root,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    return root


def test_real_demo_has_json_markdown_and_six_honest_rows(demo_flow):
    root, record = demo_flow
    assert record.report.payload["accepted"] is True
    assert record.report.payload["replay_execution_count"] == 4
    assert sorted(row.final_verdict for row in record.report.replays) == [
        "pass",
        "pass",
        "skipped",
        "skipped",
        "violation",
        "violation",
    ]
    assert DemoReport.model_validate_json((root / "out/report.json").read_bytes()) == record
    assert (root / "out/report.md").read_text(encoding="utf-8") == render_report(
        record, OutputFormat.MARKDOWN
    )
    for group in record.report.payload["groups"]:
        assert len(group["rules"]["initial"]["clauses"]) == 1
        assert len(group["rules"]["refined"]["clauses"]) == 2


def test_demo_repeat_and_all_formats_never_execute_or_rewrite(demo_flow, monkeypatch):
    root, record = demo_flow
    before = {
        p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (root / "out").rglob("*") if p.is_file()
    }

    def forbidden(*a, **k):
        pytest.fail("Cached Demo may only verify and render")

    for name in (
        "subprocess.run",
        "evidenceguard.demo.run_pipeline",
        "evidenceguard.pipeline.capture_candidate",
        "evidenceguard.pipeline.fit_scopes",
    ):
        monkeypatch.setattr(name, forbidden)
    assert run_demo(SCENARIO, cwd=root, workspace="out") == record
    assert verify_demo("out/report.json", cwd=root) == record
    for format in OutputFormat:
        result = CliRunner().invoke(
            app,
            [
                "demo",
                "--scenario",
                SCENARIO,
                "--workspace",
                "out",
                "--cwd",
                str(root),
                "--format",
                format.value,
            ],
        )
        assert result.exit_code == 0, result.output
        assert result.stdout == render_report(record, format)
    verified = CliRunner().invoke(
        app, ["demo", "--verify-only", "--workspace", "out", "--cwd", str(root), "--format", "json"]
    )
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["artifact_digest"] == record.artifact_digest
    assert before == {
        p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (root / "out").rglob("*") if p.is_file()
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "markdown",
        "resigned_facts",
        "resigned_code",
        "missing_markdown",
        "missing_pipeline",
        "partial",
    ],
)
def test_tampering_and_partial_publication_never_regenerate(mutable_demo, monkeypatch, mutation):
    root = mutable_demo
    marker = root / "out/report.json"
    if mutation == "markdown":
        (root / "out/report.md").write_bytes(b"all passed")
    elif mutation in {"resigned_facts", "resigned_code"}:
        payload = json.loads(marker.read_bytes())
        if mutation == "resigned_facts":
            payload["report"]["payload"]["accepted"] = False
        else:
            payload["presentation_code_digests"]["demo.py"] = "sha256:" + "0" * 64
        payload["artifact_digest"] = digest_json_artifact(payload)
        marker.write_bytes(canonical_json_bytes(payload))
    elif mutation == "partial":
        marker.unlink()
    else:
        (
            root / "out" / ("report.md" if mutation == "missing_markdown" else "run_manifest.json")
        ).unlink()
    before = {p: p.read_bytes() for p in (root / "out").rglob("*") if p.is_file()}

    def forbidden(*a, **k):
        pytest.fail("Corrupt/partial Demo must not execute or regenerate")

    monkeypatch.setattr("evidenceguard.demo.run_pipeline", forbidden)
    with pytest.raises((ArtifactIntegrityError, OSError)):
        run_demo(SCENARIO, cwd=root, workspace="out")
    assert before == {p: p.read_bytes() for p in (root / "out").rglob("*") if p.is_file()}


def test_changed_scenario_path_is_refused(demo_flow):
    root, _ = demo_flow
    other = root / "other.yaml"
    other.write_bytes((root / SCENARIO).read_bytes())
    with pytest.raises(ArtifactIntegrityError, match="another scenario"):
        run_demo("other.yaml", cwd=root, workspace="out")
