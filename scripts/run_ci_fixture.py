"""Build fresh, trusted demo facts for an ephemeral CI workspace, then verify.

Only CounterGuard's checked-in demonstration code is captured on the host. This
is NOT an importer/bootstrap for user projects, existing Registries or PR code.
No portable re-signing or promotion of user Guards is performed.
"""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from counterguard.compiler import CompileRequest, compile_guard
from counterguard.errors import CounterGuardError
from counterguard.evidence import CaptureRequest, capture_evidence
from counterguard.github_report import export_github_report
from counterguard.lifecycle import GuardState
from counterguard.registry import Registry
from counterguard.runner_catalog import resolve_runner
from counterguard.verify import VerifyRequest, verify_repository

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("fixed", "shadow-regression", "active-regression", "unknown")


def _git(root: Path, *args: str) -> str:
    executable = shutil.which("git")
    if not executable:
        raise ValueError("Git unavailable")
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    result = subprocess.run(
        [executable, "-c", "core.hooksPath=", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        env=env,
        capture_output=True,
        check=True,
        timeout=15,
    )
    return result.stdout.decode().strip()


def run_fixture(workspace: Path, scenario: str) -> int:
    if scenario not in SCENARIOS:
        raise ValueError("Unsupported trusted fixture scenario")
    if workspace.exists():
        raise ValueError("CI fixture workspace exists; choose a new directory")
    review = resolve_runner(runner_id="root-pytest8", image_digest=None)
    workspace.mkdir(parents=True)
    workspace = workspace.resolve()
    try:
        # The fixed CounterGuard checkout is the source, never the target PR.
        shutil.copytree(
            ROOT / "examples", workspace / "examples", ignore=shutil.ignore_patterns("__pycache__")
        )
        test = workspace / "contract_test.py"
        test.write_bytes(
            (ROOT / "tests/contract_tests/test_membership_discount_v1.py").read_bytes()
        )
        contract_ref = "examples/discount/contracts/membership_discount_final_price_v1.json"
        capture_evidence(
            CaptureRequest(
                "evd_ci_fixture_v1",
                Path(contract_ref),
                test,
                "examples.discount.implementations.final_price_v1_buggy:calculate_price",
                "examples.discount.implementations.final_price_v1_fixed:calculate_price",
                workspace,
                Path("facts"),
            )
        )
        guard = compile_guard(
            CompileRequest(
                "grd_ci_fixture_v1",
                workspace / "facts/evidence/evd_ci_fixture_v1/evidence.json",
                workspace,
                workspace / "facts",
            )
        )
        registry = Registry(workspace / "registry")
        registry.add(workspace / "facts/guards/grd_ci_fixture_v1/guard.json", cwd=workspace)
        registry.transition(guard.guard_id, to=GuardState.SHADOW, reason="trusted demo fixture")
        if scenario == "active-regression":
            registry.transition(
                guard.guard_id,
                to=GuardState.ACTIVE,
                reason="explicit demo fixture scenario; not user authorization",
            )
        repo = workspace / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.name", "CounterGuard fixture")
        _git(repo, "config", "user.email", "fixture@example.invalid")
        implementations = workspace / "examples/discount/implementations"
        buggy = (implementations / "final_price_v1_buggy.py").read_bytes()
        fixed = (implementations / "final_price_v1_fixed.py").read_bytes()
        source = repo / "target.py"
        source.write_bytes(buggy if scenario == "fixed" else fixed)
        (repo / "contract.json").write_bytes((workspace / contract_ref).read_bytes())
        (repo / "pyproject.toml").write_text(
            '[project]\nname="counterguard-ci-fixture"\nversion="0.1"\ndependencies=[]\n'
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "trusted fixture base")
        base = _git(repo, "rev-parse", "HEAD")
        source.write_bytes(fixed if scenario == "fixed" else buggy)
        if scenario == "unknown":
            source.write_bytes(source.read_bytes() + b"\n# outside the reviewed source bytes\n")
        _git(repo, "add", "target.py")
        _git(repo, "commit", "-m", "trusted fixture head")
        head = _git(repo, "rev-parse", "HEAD")
        config = workspace / "config.json"
        config.write_text(
            json.dumps(
                {
                    "schema_version": "project-config.v1",
                    "project_id": "ci-fixture",
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
            )
        )
        report = verify_repository(
            VerifyRequest(
                repo,
                base,
                head,
                config,
                registry.root,
                Path("verify"),
                cwd=workspace,
                runner_id=review.runner_id,
            )
        )
        return report.exit_code
    finally:
        # Even a bootstrap failure produces an explicit failure summary. No raw
        # exception, Git stderr, environment or private path is exported.
        export_github_report(workspace / "verify/report.json", workspace / "public")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, default="fixed")
    args = parser.parse_args()
    try:
        code = run_fixture(args.workspace, args.scenario)
    except (OSError, ValueError, subprocess.SubprocessError, CounterGuardError):
        print("Trusted CI fixture preparation failed; no target fallback was used.")
        code = 5
    raise SystemExit(code)


if __name__ == "__main__":
    main()
