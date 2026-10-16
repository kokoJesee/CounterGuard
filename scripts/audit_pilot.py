"""Reproduce a frozen candidate's admission decision; never execute candidate code."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspect_repository
from counterguard.digests import canonical_json_bytes, digest_file, digest_json_artifact
from counterguard.errors import FeatureExtractionError
from counterguard.features import extract_ast_features
from counterguard.preflight import preflight_repository
from counterguard.registry import Registry
from counterguard.repository import read_committed_files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.manifest.read_bytes())
    if digest_json_artifact(value) != value["artifact_digest"]:
        raise ValueError("Pilot manifest digest mismatch")
    for ref_key, digest_key in (
        ("config_ref", "config_digest"),
        ("metadata_ref", "metadata_digest"),
        ("design_ref", "design_digest"),
        ("runner_receipt_ref", "runner_receipt_digest"),
    ):
        if digest_file(value[ref_key]) != value[digest_key]:
            raise ValueError("Pilot frozen input changed")
    for ref, expected in value["prerequisite_receipts"].items():
        if digest_file(ref) != expected:
            raise ValueError("Pilot prerequisite receipt changed")
    contract = value["candidate_contract"]
    if digest_file(contract["ref"]) != contract["content_digest"]:
        raise ValueError("Pilot contract proposal changed")
    if digest_file(value["license"]["local_ref"]) != value["license"]["content_digest"]:
        raise ValueError("Pilot frozen license changed")
    args.output.mkdir(parents=True, exist_ok=False)
    preflight = preflight_repository(args.repo, value["head_sha"])
    inspection = inspect_repository(
        args.repo, value["base_sha"], value["head_sha"], value["config_ref"]
    )
    rows = Registry(value["registry_root"]).list()
    blockers = []
    if not value["fsck_admitted"]:
        blockers.append("pilot_fsck_or_size_gate_failed")
    if preflight["status"] != "eligible_candidate":
        blockers.extend(row["code"] for row in preflight["findings"])
    if inspection.status != "ready":
        blockers.extend(inspection.reason_codes)
    if not contract["admitted"]:
        blockers.extend(
            [
                "external_contract_proposal_not_admitted",
                "no_verified_validators_guard_or_applicability_evidence",
            ]
        )
    _, files, pins = read_committed_files(args.repo, value["head_sha"])
    if [pin.model_dump(mode="json") for pin in pins] != value["complete_tree_pins"]:
        raise ValueError("Pilot committed tree differs from the frozen manifest")
    try:
        extract_ast_features(files["src/validators/mac_address.py"], "mac_address")
    except FeatureExtractionError as error:
        blockers.append("decorated_target_outside_ast_features_v1")
        extractor_detail = str(error)
    else:
        extractor_detail = None
    if not blockers:
        raise ValueError("Admission review changed; this audit-only script never executes code")
    guard_rows = []
    for row in rows:
        guard_rows.append(
            {
                **row,
                "scope_decision": "unknown",
                "run": None,
                "verdict": "skipped_disabled" if row["status"] == "disabled" else "skipped_unknown",
                "decision_basis": (
                    "no audited semantic mapping from this Guard family to validators"
                ),
                "not_judged_reasons": sorted(set(blockers)),
            }
        )
    projection = {
        "base_sha": value["base_sha"],
        "head_sha": value["head_sha"],
        "inspection_status": inspection.status,
        "preflight_status": preflight["status"],
        "blockers": sorted(set(blockers)),
        "guards": guard_rows,
        "counts": {
            "registered_guards": len(guard_rows),
            "execution": 0,
            "skipped_disabled": sum(x["verdict"] == "skipped_disabled" for x in guard_rows),
            "skipped_unknown": sum(x["verdict"] == "skipped_unknown" for x in guard_rows),
        },
    }
    report = {
        "schema_version": "pilot-admission-report.v1",
        "accepted": False,
        "status": "stopped_before_repository_execution",
        "created_at": datetime.now(UTC).isoformat(),
        "manifest_digest": value["artifact_digest"],
        "implementation_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip(),
        "implementation_files": {
            str(path): digest_file(path)
            for path in (
                Path(__file__),
                Path("scripts/prepare_pilot_repo.py"),
                Path("scripts/freeze_pilot_candidate.py"),
            )
        },
        "inspection_digest": inspection.artifact_digest,
        "preflight_digest": preflight["artifact_digest"],
        "extractor_detail": extractor_detail,
        "projection": projection,
        "projection_digest": digest_json_artifact(projection),
        "repository_execution_count": 0,
        "local_fallback_count": 0,
        "scope": "admission/refusal validation only; no execution or bug-detection claim",
    }
    report["artifact_digest"] = digest_json_artifact(report)
    for name, payload in (
        ("preflight.json", preflight),
        ("inspection.json", inspection),
        ("report.json", report),
    ):
        write_immutable(args.output / name, canonical_json_bytes(payload))
    print(
        json.dumps(
            {
                "status": report["status"],
                "blockers": projection["blockers"],
                "counts": projection["counts"],
                "report": str(args.output / "report.json"),
            }
        )
    )
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
