"""Bounded, allowlisted CI projection of an existing verification JSON report.

The projection rechecks self integrity and count/exit policy, not provenance or
execution truth. Raw logs, identifiers, actor text and paths are never exported.
"""

import json
import stat
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.project_config import reject_links
from counterguard.verify import VerifyReport, VerifyReportV2

REPORT_LIMIT = 8 * 1024 * 1024
REASONS = frozenset(
    {
        "inspection_unknown",
        "inspection_rejected",
        "scope_unknown",
        "guard_not_registered",
        "guard_disabled",
        "guard_not_reviewed",
        "guard_retired",
        "candidate_not_schedulable",
        "retired_not_schedulable",
        "target_unaffected",
        "unmapped_guard",
        "unknown_source_snapshot",
        "source_snapshot_not_reviewed",
        "verification_integrity_failure",
        "post_execution_integrity_failure",
        "docker_or_request_unavailable",
        "registry_or_input_integrity_failure",
        "invalid_or_unavailable_input",
        "unsupported_repository_scope",
    }
)


def _validated(value: dict) -> VerifyReport | VerifyReportV2:
    model = {"verify-report.v1": VerifyReport, "verify-report.v2": VerifyReportV2}.get(
        value.get("schema_version")
    )
    if model is None:
        raise ValueError("Unsupported verification report")
    report = model.model_validate_json(canonical_json_bytes(value))
    if digest_json_artifact(report) != report.artifact_digest:
        raise ValueError("Verification report digest mismatch")
    if len(report.rows) > 4096:
        raise ValueError("Verification report exceeds row budget")
    return report


def project_github_report(value: dict) -> dict:
    report = _validated(value)
    projection = {
        "schema_version": "github-summary.v1",
        "source_report_digest": report.artifact_digest,
        "source_decision_digest": report.decision_digest,
        "exit_code": report.exit_code,
        "counts": report.counts,
        "issues": [
            {
                "exit_code": item.exit_code,
                "reason_code": item.reason_code
                if item.reason_code in REASONS
                else "other_reason_redacted",
            }
            for item in report.issues
        ],
        "rows": [
            {
                "row": index,
                "state": row.lifecycle_state.value if row.lifecycle_state else "unregistered",
                "scope": row.scope_decision or "not_evaluated",
                "execution": row.execution_outcome,
                "verdict": row.verdict,
                "reason_codes": sorted(
                    {
                        reason if reason in REASONS else "other_reason_redacted"
                        for reason in row.reason_codes
                    }
                ),
            }
            for index, row in enumerate(report.rows, 1)
        ],
        "claim": "Presentation integrity only; provenance and execution are not reverified.",
    }
    projection["artifact_digest"] = digest_json_artifact(projection)
    return projection


def render_github_summary(projection: dict) -> str:
    counts = projection["counts"]
    lines = [
        "# CounterGuard verification",
        "",
        f"Exit code: {projection['exit_code']}",
        "",
        "| Metric | Count |",
        "|---|---:|",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in sorted(counts.items()))
    lines += [
        "",
        "| Row | State | Scope | Execution | Verdict | Reasons |",
        "|---:|---|---|---|---|---|",
    ]
    for row in projection["rows"]:
        lines.append(
            "| "
            + " | ".join(str(row[key]) for key in ("row", "state", "scope", "execution", "verdict"))
            + " | "
            + (", ".join(row["reason_codes"]) or "-")
            + " |"
        )
    lines += [
        "",
        "Shadow violations are warnings. Active violations block.",
        "Unknown, execution errors and integrity errors retain their nonzero exit codes.",
        "Skipped and unknown results are not passes.",
        "",
        "Source report digest: " + projection["source_report_digest"],
        "This summary checks presentation integrity; it does not reverify execution.",
        "",
    ]
    for issue in projection["issues"]:
        lines.append(f"Issue {issue['exit_code']}: {issue['reason_code']}")
    return "\n".join(lines) + "\n"


def export_github_report(report_path: Path, output: Path) -> int:
    """Write only projection files; preserve the report's actual exit status."""
    reject_links(output)
    if output.exists():
        raise ArtifactIntegrityError("CI output already exists; choose a new output ID")
    output.mkdir(parents=True)
    try:
        reject_links(report_path)
        info = report_path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > REPORT_LIMIT:
            raise ValueError("Verification report must be a bounded regular file")
        with report_path.open("rb") as stream:
            raw = stream.read(REPORT_LIMIT + 1)
        if len(raw) > REPORT_LIMIT:
            raise ValueError("Verification report exceeds byte budget")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Verification report must be an object")
        projection = project_github_report(value)
    except (OSError, ValueError, RecursionError, TypeError):
        # A missing/broken JSON must not appear as an empty green report.
        projection = {
            "schema_version": "github-summary-failure.v1",
            "exit_code": 5,
            "reason_code": "verification_report_missing_or_invalid",
        }
        projection["artifact_digest"] = digest_json_artifact(projection)
        markdown = "# CounterGuard verification\n\nReport missing or invalid. Exit code: 5.\n"
    else:
        markdown = render_github_summary(projection)
    write_immutable(output / "summary.json", canonical_json_bytes(projection))
    write_immutable(output / "summary.md", markdown.encode())
    return projection["exit_code"]
