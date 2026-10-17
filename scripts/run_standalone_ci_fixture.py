"""Trusted tool-owned source-only CI demo; every target run uses reviewed Docker.

This creates a new demonstration history and Registry. It never imports PR code,
copies an existing Registry, or promotes a user's Guard. Use a fixed tool commit.
"""

import argparse
import json
import sys
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes
from counterguard.errors import CounterGuardError
from counterguard.github_report import export_github_report
from counterguard.lifecycle import GuardState
from counterguard.registry import Registry
from counterguard.repository import RepositoryProblem
from counterguard.standalone_capture import capture_standalone
from counterguard.standalone_guard import compile_standalone_guard
from counterguard.verify import VerifyRequest, verify_repository

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("fixed", "shadow-regression", "active-regression", "unknown")


def run_fixture(workspace: Path, scenario: str, *, import_root=".") -> int:
    if scenario not in SCENARIOS or import_root not in {".", "src"}:
        raise ValueError("Unsupported controlled fixture scenario/layout")
    if workspace.exists():
        raise ValueError("Use a new fixture workspace")
    workspace.mkdir(parents=True)
    workspace = workspace.resolve(strict=True)
    # Only the pinned trusted tool checkout is added, never the target repository.
    sys.path.insert(0, str(ROOT))
    from tests.repository_support import git
    from tests.standalone_support import standalone_history

    try:
        repo = standalone_history(workspace, import_root=import_root)
        owner_head = git(repo, "rev-parse", "HEAD")
        evidence = capture_standalone(
            repo,
            workspace / "bind/binding.json",
            runner_id="root-pytest8",
            evidence_id="evd_ci_standalone_v1",
            review_reason="tool-owned fixture oracle/closure review",
            output=workspace / "capture",
            cwd=workspace,
        )
        if not evidence.get("reproduced"):
            raise ValueError("Controlled fixture did not reproduce")
        guard = compile_standalone_guard(
            repo,
            workspace / "capture/evidence.json",
            guard_id="grd_ci_standalone_v1",
            review_reason="tool-owned exact snapshot/independence review",
            output=workspace / "guard",
            cwd=workspace,
        )
        registry = Registry(workspace / "registry")
        registry.add(workspace / "guard/guard.json", cwd=workspace, repo=repo)
        registry.transition(
            guard.guard_id, to=GuardState.SHADOW, reason="explicit trusted demo review"
        )
        if scenario == "active-regression":
            registry.transition(
                guard.guard_id,
                to=GuardState.ACTIVE,
                reason="explicit controlled demo scenario, not authorization of user Guards",
            )
        binding = json.loads((workspace / "bind/binding.json").read_bytes())
        contract = binding["contract"]
        source = repo / contract["source_ref"]
        source.write_bytes((workspace / "capture/b" / contract["source_ref"]).read_bytes())
        if scenario == "unknown":
            source.write_bytes(source.read_bytes() + b"\n# deliberately unreviewed snapshot\n")
        git(repo, "add", contract["source_ref"])
        git(repo, "commit", "-m", "tool-owned demonstration target snapshot")
        target_head = git(repo, "rev-parse", "HEAD")
        config = {
            "schema_version": "project-config.v2",
            "project_id": "ci-standalone",
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
        write_immutable(workspace / "config.json", canonical_json_bytes(config))
        base, head = (target_head, owner_head) if scenario == "fixed" else (owner_head, target_head)
        report = verify_repository(
            VerifyRequest(
                repo,
                base,
                head,
                workspace / "config.json",
                registry.root,
                workspace / "verify",
                cwd=workspace,
                runner_id="root-pytest8",
            )
        )
        return report.exit_code
    finally:
        export_github_report(workspace / "verify/report.json", workspace / "public")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--scenario", choices=SCENARIOS, default="fixed")
    parser.add_argument("--import-root", choices=(".", "src"), default=".")
    args = parser.parse_args()
    try:
        code = run_fixture(args.workspace, args.scenario, import_root=args.import_root)
    except (CounterGuardError, RepositoryProblem, OSError, ValueError):
        print("Controlled Docker fixture failed; no host fallback or raw diagnostics exported.")
        code = 5
    raise SystemExit(code)


if __name__ == "__main__":
    main()
