"""One gated repository workflow; refusal never falls back to trusted-local execution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import RunOutcome, RunRecord, RunRole
from counterguard.pilot_inputs import load_inputs, read_fact, signed
from counterguard.registry import Registry
from counterguard.repository_contracts import GUARD_ID
from counterguard.repository_guard import (
    _verify_record,
    build_repository_guard,
    execute_admitted,
    make_request,
    verify_pilot_scope,
)


def legacy_decisions(workspace: Path) -> list[dict]:
    root = workspace / ".counterguard"
    if not (root / "registry.sqlite3").is_file():
        return []
    registry = Registry(root)
    rows = []
    for item in registry.list():
        details = registry.show(item["guard_id"], with_evidence=True)
        guard = details["guard"]
        rows.append(
            {
                "guard_id": item["guard_id"],
                "guard_digest": item["guard_digest"],
                "status": item["status"],
                "integrity": item["integrity"],
                "source_evidence_id": guard["source_evidence_id"],
                "source_evidence_ref": guard["source_evidence_ref"],
                "contract_id": guard["contract_id"],
                "scope_decision": "unknown",
                "scope_basis": None,
                "verdict": "skipped_disabled"
                if item["status"] == "disabled"
                else "skipped_unknown",
                "not_judged_reasons": ["no_audited_mapping_from_this_business_to_validators"],
                "run": None,
            }
        )
    return rows


def replay_pilot(manifest_path: Path, workspace: Path) -> dict:
    facts = load_inputs(manifest_path, workspace)
    manifest = facts["manifest"]
    registry = Registry(workspace / manifest["registry_root_ref"])
    verified = registry.resolve_for_execution(GUARD_ID)
    guard = verified.guard
    scope = verify_pilot_scope(workspace / manifest["scope_ref"], facts, guard)
    request = make_request(
        facts,
        workspace,
        "h",
        RunRole.REPLAY,
        tuple(case.case_id for case in guard.cases),
        test_ref="t/guard.py",
    )
    run, authorization_ref = execute_admitted(
        request, facts, manifest_path, workspace, phase="replay"
    )
    # Re-verify terminal disable/source state, not just the pre-run registration snapshot.
    registry.resolve_for_execution(GUARD_ID)
    verdict = {RunOutcome.PASSED: "pass", RunOutcome.TEST_FAILED: "violation"}.get(
        run.outcome, "execution_error"
    )
    rows = legacy_decisions(workspace)
    rows.append(
        {
            "guard_id": guard.guard_id,
            "guard_digest": guard.artifact_digest,
            "status": "enabled",
            "integrity": "verified",
            "source_evidence_id": guard.source_evidence_id,
            "source_evidence_ref": guard.source_evidence_ref,
            "contract_id": guard.contract_id,
            "scope_decision": "applicable",
            "scope_basis": scope.basis,
            "scope_digest": scope.artifact_digest,
            "verdict": verdict,
            "not_judged_reasons": [],
            "authorization_ref": authorization_ref,
            "run": run.model_dump(mode="json"),
        }
    )
    rows.sort(key=lambda row: row["guard_id"])
    counts = {"registered_guards": len(rows), "execution": sum(r["run"] is not None for r in rows)}
    for name in ("pass", "violation", "skipped_disabled", "skipped_unknown", "execution_error"):
        counts[name] = sum(row["verdict"] == name for row in rows)
    projection = {
        "manifest_digest": manifest["artifact_digest"],
        "head_sha": manifest["head_sha"],
        "counts": counts,
        "guards": [
            {
                key: row[key]
                for key in (
                    "guard_id",
                    "guard_digest",
                    "scope_decision",
                    "scope_basis",
                    "verdict",
                    "source_evidence_id",
                    "not_judged_reasons",
                )
            }
            for row in rows
        ],
    }
    return signed(
        {
            "schema_version": "pilot-execution-report.v2",
            "created_at": datetime.now(UTC).isoformat(),
            "accepted": verdict == "pass",
            "scope": "MAC exact-snapshot integration only",
            "learned_scope_evaluated": False,
            "manifest_ref": manifest_path.relative_to(workspace).as_posix(),
            "manifest_digest": manifest["artifact_digest"],
            "head_sha": manifest["head_sha"],
            "guards": rows,
            "projection": projection,
            "projection_digest": digest_json_artifact(projection),
            "repository_execution_count": counts["execution"],
            "local_fallback_count": 0,
            "implementation_digests": inspection_implementation_digests(),
        }
    )


def verify_pilot_report(path: Path, workspace: Path) -> dict:
    """Rebuild decisions and raw execution claims; a valid self hash is insufficient."""
    value = read_fact(path)
    if value.get("schema_version") != "pilot-execution-report.v2":
        raise ArtifactIntegrityError("Expected a real execution report")
    manifest_path = workspace / value["manifest_ref"]
    facts = load_inputs(manifest_path, workspace)
    manifest = facts["manifest"]
    if (
        value["manifest_digest"] != manifest["artifact_digest"]
        or value["head_sha"] != manifest["head_sha"]
        or value["implementation_digests"] != facts["implementation_digests"]
        or value["learned_scope_evaluated"] is not False
        or value["local_fallback_count"] != 0
    ):
        raise ArtifactIntegrityError("Execution report binding or scope claim differs")
    verified = Registry(workspace / manifest["registry_root_ref"]).resolve_for_execution(GUARD_ID)
    guard = verified.guard
    scope = verify_pilot_scope(workspace / manifest["scope_ref"], facts, guard)
    rows = value["guards"]
    primary = [row for row in rows if row["guard_id"] == GUARD_ID]
    if len(primary) != 1 or primary[0]["run"] is None:
        raise ArtifactIntegrityError("Report must contain one actual MAC execution")
    row = primary[0]
    run = RunRecord.model_validate_json(canonical_json_bytes(row["run"]))
    _verify_record(run, row["authorization_ref"], manifest_path, workspace, "replay")
    verdict = {RunOutcome.PASSED: "pass", RunOutcome.TEST_FAILED: "violation"}.get(
        run.outcome, "execution_error"
    )
    expected = {
        "guard_id": guard.guard_id,
        "guard_digest": guard.artifact_digest,
        "status": "enabled",
        "integrity": "verified",
        "source_evidence_id": guard.source_evidence_id,
        "source_evidence_ref": guard.source_evidence_ref,
        "contract_id": guard.contract_id,
        "scope_decision": "applicable",
        "scope_basis": scope.basis,
        "scope_digest": scope.artifact_digest,
        "verdict": verdict,
        "not_judged_reasons": [],
        "authorization_ref": row["authorization_ref"],
        "run": run.model_dump(mode="json"),
    }
    expected_rows = sorted([*legacy_decisions(workspace), expected], key=lambda r: r["guard_id"])
    if rows != expected_rows:
        raise ArtifactIntegrityError("Report rows contradict source, scope or actual runs")
    counts = {"registered_guards": len(rows), "execution": 1}
    for name in ("pass", "violation", "skipped_disabled", "skipped_unknown", "execution_error"):
        counts[name] = sum(item["verdict"] == name for item in rows)
    projection = {
        "manifest_digest": manifest["artifact_digest"],
        "head_sha": manifest["head_sha"],
        "counts": counts,
        "guards": [
            {
                key: item[key]
                for key in (
                    "guard_id",
                    "guard_digest",
                    "scope_decision",
                    "scope_basis",
                    "verdict",
                    "source_evidence_id",
                    "not_judged_reasons",
                )
            }
            for item in rows
        ],
    }
    if (
        value["projection"] != projection
        or value["projection_digest"] != digest_json_artifact(projection)
        or value["repository_execution_count"] != 1
        or value["accepted"] != (verdict == "pass")
    ):
        raise ArtifactIntegrityError(
            "Report counts/acceptance contradict independently rebuilt facts"
        )
    return value


def compare_replays(first: Path, second: Path) -> dict:
    workspace = Path.cwd().resolve(strict=True)
    a, b = verify_pilot_report(first, workspace), verify_pilot_report(second, workspace)
    if (
        a.get("schema_version") != "pilot-execution-report.v2"
        or b.get("schema_version") != a["schema_version"]
    ):
        raise ArtifactIntegrityError("Compare requires execution reports, not static refusals")
    runs_a = {row["run"]["run_id"] for row in a["guards"] if row["run"] is not None}
    runs_b = {row["run"]["run_id"] for row in b["guards"] if row["run"] is not None}
    if not runs_a.isdisjoint(runs_b):
        raise ArtifactIntegrityError("Repeatability requires independent run records")
    equal = a["projection"] == b["projection"]
    accepted = a["accepted"] and b["accepted"] and equal
    return signed(
        {
            "schema_version": "pilot-repeatability.v2",
            "accepted": accepted,
            "execution_repeatability_tested": True,
            "counts_equal": equal,
            "first_report_digest": a["artifact_digest"],
            "second_report_digest": b["artifact_digest"],
            "first_projection_digest": a["projection_digest"],
            "second_projection_digest": b["projection_digest"],
            "counts": a["projection"]["counts"],
        }
    )


def run_phase(manifest_path: Path, workspace: Path, output: Path, phase: str) -> dict:
    facts = load_inputs(manifest_path, workspace)
    if phase == "preflight":
        write_immutable(output / "inspection.json", canonical_json_bytes(facts["inspection"]))
        value = signed(
            {
                "schema_version": "repository-preflight.v2",
                "status": "eligible_candidate",
                "manifest_digest": facts["manifest"]["artifact_digest"],
                "execution_allowed": False,
                "source_selection": "complete_committed_trees_only",
                "profile": "docker-policy.v1/pytest9.0.3/src/pinned-MAC-oracle",
                "revisions": facts["preflights"],
                "implementation_digests": facts["implementation_digests"],
            }
        )
        write_immutable(output / "preflight.json", canonical_json_bytes(value))
        return signed(
            {
                "phase": phase,
                "accepted": True,
                "repository_execution_count": 0,
                "manifest_digest": facts["manifest"]["artifact_digest"],
            }
        )
    if phase == "build-guard":
        guard = build_repository_guard(manifest_path, workspace)
        return signed(
            {
                "phase": phase,
                "accepted": True,
                "guard_id": guard.guard_id,
                "guard_digest": guard.artifact_digest,
                "minimal_cases": len(guard.cases),
                "repository_execution_count": 3,
                "local_fallback_count": 0,
            }
        )
    if phase == "replay":
        return replay_pilot(manifest_path, workspace)
    raise ValueError("Unknown pilot phase")
