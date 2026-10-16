"""Real Git + pinned Docker through the public verification entry point."""

import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from counterguard.compiler import CompileRequest, compile_guard
from counterguard.evidence import CaptureRequest, capture_evidence
from counterguard.lifecycle import GuardState
from counterguard.registry import Registry
from counterguard.verify import VerifyRequest, verify_repository
from tests.repository_support import git

pytestmark = [pytest.mark.slow, pytest.mark.docker]
ROOT = Path(__file__).resolve().parents[2]


def test_real_verify_shadow_active_repeat_unknown_and_no_local_fallback(tmp_path, monkeypatch):
    image = os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST")
    if not image:
        pytest.skip("set COUNTERGUARD_RUNNER_IMAGE_DIGEST to the reviewed root-profile runner")
    # Only these trusted project fixtures use the local capture/compiler. The Git
    # target below is never imported or executed by the host.
    shutil.copytree(
        ROOT / "examples", tmp_path / "examples", ignore=shutil.ignore_patterns("__pycache__")
    )
    test = tmp_path / "contract_test.py"
    test.write_bytes((ROOT / "tests/contract_tests/test_membership_discount_v1.py").read_bytes())
    contract_ref = "examples/discount/contracts/membership_discount_final_price_v1.json"
    capture_evidence(
        CaptureRequest(
            "evd_verify_fixture_v1",
            Path(contract_ref),
            test,
            "examples.discount.implementations.final_price_v1_buggy:calculate_price",
            "examples.discount.implementations.final_price_v1_fixed:calculate_price",
            tmp_path,
            Path("a"),
        )
    )
    guard = compile_guard(
        CompileRequest(
            "grd_verify_fixture_v1",
            tmp_path / "a/evidence/evd_verify_fixture_v1/evidence.json",
            tmp_path,
            tmp_path / "a",
        )
    )
    registry = Registry(tmp_path / "registry")
    from counterguard.runners.local import LocalTrustedExecutor

    def forbidden_local(*args, **kwargs):
        pytest.fail("A repository verify call reached the trusted-local executor")

    monkeypatch.setattr(LocalTrustedExecutor, "execute", forbidden_local)
    registry.add(tmp_path / "a/guards/grd_verify_fixture_v1/guard.json", cwd=tmp_path)
    registry.transition(guard.guard_id, to=GuardState.SHADOW, reason="fixture review")
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "CounterGuard fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    source = repo / "target.py"
    implementations = tmp_path / "examples/discount/implementations"
    source.write_bytes((implementations / "final_price_v1_fixed.py").read_bytes())
    (repo / "contract.json").write_bytes((tmp_path / contract_ref).read_bytes())
    (repo / "pyproject.toml").write_text(
        '[project]\nname="verify-fixture"\nversion="0.1"\ndependencies=[]\n', encoding="utf-8"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "known fixed snapshot")
    base = git(repo, "rev-parse", "HEAD")
    source.write_bytes((implementations / "final_price_v1_buggy.py").read_bytes())
    git(repo, "add", "target.py")
    git(repo, "commit", "-m", "known regression snapshot")
    head = git(repo, "rev-parse", "HEAD")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "project-config.v1",
                "project_id": "verify-fixture",
                "targets": [
                    {
                        "target_id": "price",
                        "guard_id": guard.guard_id,
                        "source_ref": "target.py",
                        "module": "target",
                        "symbol": "calculate_price",
                        "contract_ref": "contract.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    request = VerifyRequest(
        repo, base, head, config, registry.root, Path("shadow"), image, tmp_path
    )
    shadow = verify_repository(request)
    assert shadow.exit_code == 0 and shadow.counts["shadow_violations"] == 1
    assert shadow.rows[0].execution_outcome == "fail"
    assert "--network=none" in shadow.rows[0].run.argv
    registry.transition(guard.guard_id, to=GuardState.ACTIVE, reason="fixture acceptance")
    active = verify_repository(replace(request, output=Path("active")))
    repeat = verify_repository(replace(request, output=Path("repeat")))
    assert active.exit_code == repeat.exit_code == 1
    assert active.counts == repeat.counts
    assert active.decision_digest == repeat.decision_digest
    assert active.rows[0].run.run_id != repeat.rows[0].run.run_id
    assert (tmp_path / "active/report.json").is_file()
    assert (tmp_path / "active/report.md").is_file()
    source.write_bytes(source.read_bytes() + b"\n# not a reviewed snapshot\n")
    git(repo, "add", "target.py")
    git(repo, "commit", "-m", "unreviewed source")
    unknown = verify_repository(
        replace(request, head=git(repo, "rev-parse", "HEAD"), output=Path("unknown"))
    )
    assert unknown.exit_code == 4 and unknown.counts["executions"] == 0
    assert unknown.rows[0].run is None
