"""Prepare reproducible runtime assets without changing the frozen experiment protocol."""

import argparse
import json
from pathlib import Path

from evidenceguard.compiler import CompileRequest, compile_guard
from evidenceguard.evidence import CaptureRequest, capture_evidence, verify_evidence
from evidenceguard.models import Guard

SCENARIOS = (
    {
        "evidence_stem": "evd_discount_v1_member_rate_fix",
        "guard_id": "grd_discount_member_rate_regression_v2",
        "contract": "examples/discount/contracts/membership_discount_final_price_v1.json",
        "test": "tests/contract_tests/test_membership_discount_v1.py",
        "buggy": "examples.discount.implementations.final_price_v1_buggy:calculate_price",
        "fixed": "examples.discount.implementations.final_price_v1_fixed:calculate_price",
    },
    {
        "evidence_stem": "evd_query_limit_v1_zero_fix",
        "guard_id": "grd_query_limit_zero_regression_v2",
        "contract": "examples/validation/contracts/input_limit_query_v1.json",
        "test": "tests/contract_tests/test_query_limit_v1.py",
        "buggy": "examples.validation.implementations.query_limit_v1_buggy:parse_limit",
        "fixed": "examples.validation.implementations.query_limit_v1_fixed:parse_limit",
    },
)
RECAPTURE_REASON = (
    "Adopt semantic capture revisions and explicit replacement provenance; "
    "retain the verified exception whitelist and isolated execution harness."
)


def prepare(workspace: Path) -> dict[str, Guard]:
    workspace = workspace.resolve(strict=True)
    guards = {}
    for scenario in SCENARIOS:
        stem = scenario["evidence_stem"]
        evidence_path = Path(f"artifacts/evidence/{stem}_v2/evidence.json")
        if (workspace / evidence_path).exists():
            evidence = verify_evidence(evidence_path, cwd=workspace)
        else:
            # Preserve existing historical artifacts. A clean checkout instead creates
            # a semantic v1 predecessor; neither path rewrites the frozen protocol.
            predecessor = Path(f"artifacts/evidence/{stem}_d4/evidence.json")
            if not (workspace / predecessor).exists():
                predecessor = Path(f"artifacts/evidence/{stem}_v1/evidence.json")
                capture_evidence(
                    CaptureRequest(
                        evidence_id=f"{stem}_v1",
                        contract_path=Path(scenario["contract"]),
                        test_path=Path(scenario["test"]),
                        buggy_target=scenario["buggy"],
                        fixed_target=scenario["fixed"],
                        cwd=workspace,
                        artifact_root=Path("artifacts"),
                    )
                )
            evidence = capture_evidence(
                CaptureRequest(
                    evidence_id=f"{stem}_v2",
                    contract_path=Path(scenario["contract"]),
                    test_path=Path(scenario["test"]),
                    buggy_target=scenario["buggy"],
                    fixed_target=scenario["fixed"],
                    cwd=workspace,
                    artifact_root=Path("artifacts"),
                    supersedes_path=predecessor,
                    recapture_reason=RECAPTURE_REASON,
                )
            )
        if not evidence.reproduced:
            raise ValueError("Protocol preparation requires reproduced Evidence")
        guard = compile_guard(
            CompileRequest(
                scenario["guard_id"],
                evidence_path,
                workspace,
                Path("artifacts"),
            )
        )
        guards[guard.guard_id] = guard
    return guards


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path("."))
    args = parser.parse_args()
    prepared = prepare(args.cwd)
    print(json.dumps({key: value.artifact_digest for key, value in prepared.items()}, indent=2))
