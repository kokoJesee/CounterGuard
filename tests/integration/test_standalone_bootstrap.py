"""Complete root/src onboarding through real Git, immutable facts and pinned Docker."""

import importlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from counterguard.digests import canonical_json_bytes
from counterguard.github_report import export_github_report
from counterguard.lifecycle import GuardState
from counterguard.registry import Registry
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.standalone_capture import capture_standalone
from counterguard.standalone_guard import compile_standalone_guard, verify_standalone_guard
from counterguard.verify import VerifyRequest, verify_repository
from tests.repository_support import git
from tests.standalone_support import standalone_history

pytestmark = [pytest.mark.slow, pytest.mark.docker]


@pytest.mark.parametrize("import_root", [".", "src"], ids=["root", "src"])
def test_full_standalone_bootstrap_and_verification_states(tmp_path, monkeypatch, import_root):
    review = resolve_runner(runner_id="root-pytest8", image_digest=None)
    image = os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST")
    if not image:
        pytest.skip("set COUNTERGUARD_RUNNER_IMAGE_DIGEST for actual generic onboarding")
    assert image == review.image_digest
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("repository code reached a host executor/import")

    monkeypatch.setattr(LocalTrustedExecutor, "execute", forbidden)
    original_import = importlib.import_module

    def safe_import(name, *args, **kwargs):
        if name == "sample" or name.startswith("sample."):
            forbidden()
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", safe_import)
    repo = standalone_history(tmp_path, import_root=import_root)
    head = git(repo, "rev-parse", "HEAD")
    evidence = capture_standalone(
        repo,
        Path("bind/binding.json"),
        runner_id="root-pytest8",
        evidence_id="evd_bootstrap_v1",
        review_reason="tool-owned independent regression and closure review",
        output=Path("c"),
    )
    assert evidence["reproduced"]
    guard = compile_standalone_guard(
        repo,
        Path("c/evidence.json"),
        guard_id="grd_bootstrap_v1",
        review_reason="reviewed minimal failure and exact B/F closure snapshots",
        output=Path("g"),
    )
    assert len(guard.case_ids) == 1 and len(guard.buggy_check.run.case_results) == 1
    assert (
        guard.buggy_check.run.pytest_exit_code == 1 and guard.fixed_check.run.pytest_exit_code == 0
    )
    assert verify_standalone_guard(repo, Path("g/guard.json")) == guard
    binding = json.loads(Path("bind/binding.json").read_bytes())
    contract = binding["contract"]
    registry = Registry(tmp_path / "registry")
    entry = registry.add(Path("g/guard.json"), cwd=tmp_path, repo=repo)
    assert registry.add(Path("g/guard.json"), cwd=tmp_path, repo=repo) == entry
    config = tmp_path / "config.json"
    config.write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "project-config.v2",
                "project_id": "standalone",
                "targets": [
                    {
                        "target_id": "price",
                        "guard_id": guard.guard_id,
                        "module": contract["target_module"],
                        "symbol": contract["target_symbol"],
                        "source_ref": contract["source_ref"],
                        "import_root": import_root,
                        "contract_ref": binding["contract_ref"],
                        "dependency_refs": [
                            ref for ref in contract["runtime_refs"] if ref != contract["source_ref"]
                        ],
                    }
                ],
            }
        )
    )
    source = repo / contract["source_ref"]
    source.write_bytes((tmp_path / "c/b" / contract["source_ref"]).read_bytes())
    git(repo, "add", contract["source_ref"])
    git(repo, "commit", "-m", "tool-owned known regression snapshot")
    regression = git(repo, "rev-parse", "HEAD")
    request = VerifyRequest(
        repo,
        head,
        regression,
        config,
        registry.root,
        Path("candidate"),
        cwd=tmp_path,
        runner_id="root-pytest8",
    )
    candidate = verify_repository(request)
    assert candidate.counts["skipped"] == 1 and candidate.counts["executions"] == 0
    registry.transition(guard.guard_id, to=GuardState.SHADOW, reason="tool fixture scope approval")
    shadow = verify_repository(replace(request, output=Path("shadow")))
    assert shadow.exit_code == 0 and shadow.counts["shadow_violations"] == 1, (
        shadow.model_dump_json()
    )
    registry.transition(guard.guard_id, to=GuardState.ACTIVE, reason="explicit test acceptance")
    active = verify_repository(replace(request, output=Path("active")))
    assert active.exit_code == 1 and active.counts["blocking_violations"] == 1
    if import_root == ".":
        repeated = verify_repository(replace(request, output=Path("repeat")))
        assert (
            repeated.decision_digest == active.decision_digest and repeated.counts == active.counts
        )
        assert repeated.rows[0].run.run_id != active.rows[0].run.run_id
    fixed = verify_repository(replace(request, base=regression, head=head, output=Path("fixed")))
    assert fixed.exit_code == 0 and fixed.counts["pass"] == 1
    assert export_github_report(tmp_path / "active/report.json", tmp_path / "public") == 1
    assert json.loads(Path("public/summary.json").read_bytes())["counts"] == active.counts
    source.write_bytes(source.read_bytes() + b"\n# unreviewed source snapshot\n")
    git(repo, "add", contract["source_ref"])
    git(repo, "commit", "-m", "tool-owned unknown snapshot")
    unknown = verify_repository(
        replace(request, head=git(repo, "rev-parse", "HEAD"), output=Path("unknown"))
    )
    assert (
        unknown.exit_code == 4 and unknown.counts["executions"] == 0 and unknown.rows[0].run is None
    )
    registry.transition(guard.guard_id, to=GuardState.RETIRED, reason="terminal test state")
    retired = verify_repository(replace(request, output=Path("retired")))
    assert retired.counts["skipped"] == 1 and retired.counts["executions"] == 0
    Path("g/test_guard.py").write_bytes(b"assert True\n")
    corrupt = verify_repository(replace(request, output=Path("corrupt")))
    assert corrupt.exit_code == 5 and corrupt.counts["integrity_error"] == 1
