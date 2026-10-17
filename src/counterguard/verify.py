"""One fail-closed entry point for historical Guard selection, Docker replay and reports."""

from __future__ import annotations

import ast
import html
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import StringConstraints, TypeAdapter, model_validator

from counterguard.artifacts import write_immutable
from counterguard.change_analysis import inspect_repository, inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError, GuardReplayIntegrityError
from counterguard.execution import PytestRunRequest, verify_run_record
from counterguard.lifecycle import GuardState
from counterguard.models import (
    ArtifactRef,
    Digest,
    Evidence,
    FrozenModel,
    Guard,
    RunOutcome,
    RunRecord,
    RunRole,
    TargetRef,
    UtcDateTime,
)
from counterguard.preflight import inspect_execution_requirements
from counterguard.project_config import load_project_config, reject_links
from counterguard.registry import Registry
from counterguard.repository import RepositoryProblem, read_committed_files
from counterguard.repository_models import RepositoryGuard
from counterguard.repository_verify import UnsupportedRepositoryScope, prepare_repository_replay
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import DockerExecutor, authorize_docker_execution
from counterguard.standalone_models import StandaloneGuard
from counterguard.standalone_replay import StandaloneScopeUnknown, prepare_standalone_replay

ZERO = "sha256:" + "0" * 64


@dataclass(frozen=True)
class VerifyRequest:
    repo: Path
    base: str
    head: str
    config: Path
    registry: Path
    output: Path
    image_digest: str | None = None
    cwd: Path = Path(".")
    runner_id: str | None = None


class VerifyRow(FrozenModel):
    guard_id: str
    target_id: str | None
    lifecycle_state: GuardState | None
    registry_status: str | None
    guard_digest: Digest | None = None
    entry_digest: Digest | None = None
    source_evidence_id: str | None = None
    source_evidence_ref: ArtifactRef | None = None
    source_evidence_digest: Digest | None = None
    impact: Literal["affected", "unaffected", "unknown"] = "unknown"
    scope_decision: Literal["applicable", "inapplicable", "unknown"] | None = None
    scope_basis: Literal["verified-evidence-source-snapshot.v1"] | None = None
    scope_digest: Digest | None = None
    execution_outcome: Literal["not_run", "pass", "fail", "error", "timeout"] = "not_run"
    verdict: Literal[
        "pass", "violation", "skipped", "unknown", "execution_error", "integrity_error"
    ]
    reason_codes: tuple[str, ...] = ()
    run_workspace_ref: ArtifactRef | None = None
    run: RunRecord | None = None

    @model_validator(mode="after")
    def coherent_result(self):
        if self.execution_outcome != execution_outcome(self.run):
            raise ValueError("Execution presentation contradicts its raw run")
        if self.run is not None and self.scope_decision != "applicable":
            raise ValueError("Only an applicable Guard can have an execution record")
        if self.verdict in {"skipped", "unknown"} and self.run is not None:
            raise ValueError("Skipped/unknown rows cannot claim an execution")
        if self.verdict in {"pass", "violation"}:
            expected = RunOutcome.PASSED if self.verdict == "pass" else RunOutcome.TEST_FAILED
            if self.run is None or self.run.outcome is not expected:
                raise ValueError("Verification verdict contradicts execution")
        if self.verdict == "unknown" and self.scope_decision != "unknown":
            raise ValueError("Unknown must remain an explicit Scope decision")
        if self.verdict not in {"pass", "violation"} and not self.reason_codes:
            raise ValueError("Unjudged results require an explicit reason")
        return self


def execution_outcome(run):
    if run is None:
        return "not_run"
    return {
        RunOutcome.PASSED: "pass",
        RunOutcome.TEST_FAILED: "fail",
        RunOutcome.TIMEOUT: "timeout",
    }.get(run.outcome, "error")


def row_exit_code(row: VerifyRow) -> int:
    return {
        "integrity_error": 5,
        "execution_error": 3,
        "unknown": 4,
        "violation": 1 if row.lifecycle_state is GuardState.ACTIVE else 0,
    }.get(row.verdict, 0)


def summarize(rows, issues):
    codes = {row_exit_code(row) for row in rows} | {issue.exit_code for issue in issues}
    code = next((value for value in (5, 3, 4, 2, 1) if value in codes), 0)
    counts = {
        name: sum(row.verdict == name for row in rows)
        for name in (
            "pass",
            "violation",
            "skipped",
            "unknown",
            "execution_error",
            "integrity_error",
        )
    }
    counts.update(
        rows=len(rows),
        guards=len({row.guard_id for row in rows}),
        executions=sum(row.run is not None for row in rows),
        blocking_violations=sum(row_exit_code(row) == 1 for row in rows),
        shadow_violations=sum(
            row.verdict == "violation" and row.lifecycle_state is GuardState.SHADOW for row in rows
        ),
    )
    return code, counts


class VerifyIssue(FrozenModel):
    exit_code: Literal[2, 3, 4, 5]
    reason_code: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,127}$")]


def _decision_digest(rows, issues, counts, code):
    return digest_json_artifact(
        {
            "rows": [
                row.model_dump(mode="json", exclude={"run", "run_workspace_ref"}) for row in rows
            ],
            "issues": [issue.model_dump(mode="json") for issue in issues],
            "counts": counts,
            "exit_code": code,
        }
    )


class VerifyReport(FrozenModel):
    schema_version: Literal["verify-report.v1"] = "verify-report.v1"
    created_at: UtcDateTime
    backend: Literal["docker"] = "docker"
    agent_enabled: Literal[False] = False
    base_commit: str | None
    head_commit: str | None
    inspection_digest: Digest | None
    registry_snapshot_digest: Digest | None
    implementation_digests: dict[str, Digest]
    rows: tuple[VerifyRow, ...]
    issues: tuple[VerifyIssue, ...]
    counts: dict[str, int]
    exit_code: int
    decision_digest: Digest
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent_summary(self):
        if (self.exit_code, self.counts) != summarize(self.rows, self.issues):
            raise ValueError("Verification summary contradicts its rows/issues")
        if self.decision_digest != _decision_digest(
            self.rows, self.issues, self.counts, self.exit_code
        ):
            raise ValueError("Verification decision digest contradicts its rows/issues")
        return self


class VerifyRowV2(VerifyRow):
    scope_basis: Literal["verified-evidence-source-snapshot.v1", "pilot-scope.v1"] | None = None
    runner_review_digest: Digest | None = None


class VerifyReportV2(VerifyReport):
    schema_version: Literal["verify-report.v2"] = "verify-report.v2"
    rows: tuple[VerifyRowV2, ...]
    runner_id: str | None
    runner_image_digest: Digest | None
    runner_review_digest: Digest | None

    @model_validator(mode="after")
    def reviewed_execution(self):
        if any(row.runner_review_digest != self.runner_review_digest for row in self.rows):
            raise ValueError("Row runner review differs from report selection")
        if self.counts["executions"] and not (
            self.runner_id and self.runner_image_digest and self.runner_review_digest
        ):
            raise ValueError("Execution requires a pinned runner review")
        return self


class VerifyRowV3(VerifyRowV2):
    scope_basis: (
        Literal[
            "verified-evidence-source-snapshot.v1", "pilot-scope.v1", "standalone-snapshot-scope.v1"
        ]
        | None
    ) = None


class VerifyReportV3(VerifyReportV2):
    schema_version: Literal["verify-report.v3"] = "verify-report.v3"
    rows: tuple[VerifyRowV3, ...]


def _snapshot(rows):
    return digest_json_artifact(
        {
            "entries": [
                {
                    key: row[key]
                    for key in (
                        "guard_id",
                        "guard_digest",
                        "entry_digest",
                        "status",
                        "lifecycle_state",
                        "integrity",
                    )
                }
                | {"event_tip": row["events"][-1]["artifact_digest"]}
                for row in rows
            ]
        }
    )


def _scope(verified, mapping, files):
    """Legacy Evidence supports exact known source bytes, not learned generalization."""
    guard, evidence = verified.guard, verified.evidence
    if not isinstance(guard, Guard) or not isinstance(evidence, Evidence):
        return None, "repository_profile_requires_its_reviewed_pilot_entrypoint"
    if mapping.dependency_refs or mapping.import_root != "." or mapping.module is None:
        return None, "no_audited_dependency_or_import_root_scope"
    source = files.get(mapping.source_ref)
    contract = files.get(mapping.contract_ref)
    if source is None or contract is None:
        return None, "missing_committed_input"
    if digest_bytes(contract) != guard.contract_digest:
        return None, "contract_not_in_verified_scope"
    if digest_bytes(source) not in {guard.source_buggy_digest, guard.source_fixed_digest}:
        return None, "source_not_in_verified_scope"
    if mapping.symbol not in {evidence.buggy_target.symbol, evidence.fixed_target.symbol}:
        return None, "symbol_not_in_verified_scope"
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None, "source_cannot_be_audited"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            roots = [node.module.split(".")[0]] if node.module and not node.level else [""]
        else:
            continue
        if any(root not in sys.stdlib_module_names for root in roots):
            return None, "no_audited_dependency_scope"
    return digest_json_artifact(
        {
            "schema_version": "verified-evidence-source-snapshot.v1",
            "guard_digest": guard.artifact_digest,
            "evidence_digest": evidence.artifact_digest,
            "source_digest": digest_bytes(source),
            "contract_digest": digest_bytes(contract),
            "symbol": mapping.symbol,
        }
    ), None


def _execute_guard(request, output, report, mapping, verified, files):
    runtime = output / "work" / mapping.target_id
    for ref in mapping.input_refs():
        if ref.startswith("_cg/"):
            raise ValueError("Declared input overlaps generated verification files")
        write_immutable(runtime / ref, files[ref])
    test = runtime / "_cg/test_guard.py"
    source_workspace = Path(verified.entry.source_workspace)
    write_immutable(test, (source_workspace / verified.guard.test_ref).read_bytes())
    run_request = PytestRunRequest(
        role=RunRole.REPLAY,
        contract_id=verified.guard.contract_id,
        contract_digest=verified.guard.contract_digest,
        target=TargetRef(
            module=mapping.module, symbol=mapping.symbol, source_ref=mapping.source_ref
        ),
        target_digest=digest_bytes(files[mapping.source_ref]),
        test_path=test,
        contract_path=runtime / mapping.contract_ref,
        known_case_ids=tuple(case.case_id for case in verified.guard.cases),
        cwd=runtime,
        artifact_root=runtime / "a",
    )
    authorization = authorize_docker_execution(
        report,
        config_path=request.config,
        target_id=mapping.target_id,
        request=run_request,
        image_digest=request.image_digest,
    )
    write_immutable(runtime / "authorization.json", canonical_json_bytes(authorization))
    record = DockerExecutor(authorization, report, request.config).execute(run_request)
    try:
        write_immutable(runtime / "run.json", canonical_json_bytes(record))
        verify_run_record(record, cwd=runtime, known_case_ids=run_request.known_case_ids)
    except (ArtifactIntegrityError, OSError, ValueError) as error:
        raise GuardReplayIntegrityError("Post-execution run audit failed", record) from error
    return record


def render_verify(report: VerifyReport) -> str:
    lines = [
        "# CounterGuard verification",
        "",
        f"Exit code: {report.exit_code}",
        f"Base: {report.base_commit or 'unknown'}",
        f"Head: {report.head_commit or 'unknown'}",
        "",
        "| Guard / target | State | Scope | Execution | Verdict | Reasons |",
        "|---|---|---|---|---|---|",
    ]

    def escape(value):
        return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ")

    for row in report.rows:
        lines.append(
            "| "
            + " | ".join(
                escape(value)
                for value in (
                    f"{row.guard_id} / {row.target_id or '-'}",
                    row.lifecycle_state or "unregistered",
                    row.scope_decision or "not evaluated",
                    row.execution_outcome,
                    row.verdict,
                    ", ".join(row.reason_codes) or "-",
                )
            )
            + " |"
        )
    lines.extend(["", "Counts: " + canonical_json_bytes(report.counts).decode(), ""])
    lines.extend(f"Issue {issue.exit_code}: {escape(issue.reason_code)}" for issue in report.issues)
    lines.extend(["", f"Decision digest: {report.decision_digest}", ""])
    return "\n".join(lines)


def verify_repository(request: VerifyRequest) -> VerifyReportV2 | VerifyReportV3:
    """Write JSON and Markdown before returning any domain failure; never run locally."""
    cwd = request.cwd.resolve(strict=True)
    output = request.output if request.output.is_absolute() else cwd / request.output
    reject_links(output)
    output = output.resolve()
    if not output.is_relative_to(cwd) or output == cwd:
        raise ValueError("Verification output must be a new directory below cwd")
    if output.is_relative_to(request.repo.absolute()):
        raise ValueError("Verification output must be outside the target repository")
    if output.exists():
        raise ArtifactIntegrityError("Verification output already exists; use a new output ID")
    output.mkdir(parents=True)
    rows, issues = [], []
    inspection = None
    snapshot = None
    review = None
    report_type, row_type = VerifyReportV2, VerifyRowV2
    try:
        # Validate the image identity's syntax even when every row is skipped.
        if request.image_digest is not None:
            TypeAdapter(Digest).validate_python(request.image_digest)
        review = resolve_runner(runner_id=request.runner_id, image_digest=request.image_digest)
        request = replace(request, image_digest=review.image_digest)
        config, _ = load_project_config(request.config)
        inspection = inspect_repository(request.repo, request.base, request.head, request.config)
        write_immutable(output / "inspection.json", canonical_json_bytes(inspection))
        registry = Registry(request.registry)
        listed = registry.list()
        if any(item.get("source_profile") == "standalone-literals-docker.v1" for item in listed):
            report_type, row_type = VerifyReportV3, VerifyRowV3
        snapshot = _snapshot(listed)
        by_id = {row["guard_id"]: row for row in listed}
        mappings = [(mapping.guard_id, mapping) for mapping in config.targets]
        mapped = {guard_id for guard_id, _ in mappings}
        mappings += [(guard_id, None) for guard_id in by_id.keys() - mapped]
        files = None
        if inspection.status != "ready":
            issues.append(
                VerifyIssue(
                    exit_code=5 if inspection.status == "rejected" else 4,
                    reason_code="inspection_" + inspection.status,
                )
            )
        for guard_id, mapping in sorted(
            mappings, key=lambda pair: (pair[0], pair[1].target_id if pair[1] else "")
        ):
            item = by_id.get(guard_id)
            state = GuardState(item["lifecycle_state"]) if item else None
            values = dict(
                guard_id=guard_id,
                target_id=mapping.target_id if mapping else None,
                lifecycle_state=state,
                registry_status=item["status"] if item else None,
                runner_review_digest=review.artifact_digest,
            )
            if item:
                values.update(guard_digest=item["guard_digest"], entry_digest=item["entry_digest"])
                values.update(
                    {
                        key: item[key]
                        for key in (
                            "source_evidence_id",
                            "source_evidence_ref",
                            "source_evidence_digest",
                        )
                    }
                )

            def result(verdict, reason, _values=values, **kwargs):
                payload = _values | kwargs
                payload["execution_outcome"] = execution_outcome(payload.get("run"))
                return row_type(
                    **payload,
                    verdict=verdict,
                    reason_codes=(reason,) if isinstance(reason, str) else tuple(reason or ()),
                )

            if item and item["integrity"] != "verified":
                rows.append(result("integrity_error", "source_chain_invalid"))
                continue
            if item and (
                item["status"] == "disabled" or state not in {GuardState.SHADOW, GuardState.ACTIVE}
            ):
                rows.append(
                    result(
                        "skipped",
                        "registry_disabled"
                        if item["status"] == "disabled"
                        else "lifecycle_" + state.value,
                    )
                )
                continue
            if not item or mapping is None:
                rows.append(
                    result(
                        "unknown",
                        "guard_not_registered" if not item else "no_target_mapping",
                        scope_decision="unknown",
                    )
                )
                continue
            impact = next(row for row in inspection.targets if row.target_id == mapping.target_id)
            values["impact"] = impact.impact
            if impact.impact == "unaffected":
                rows.append(result("skipped", "unaffected_inputs"))
                continue
            if inspection.status != "ready" or impact.impact == "unknown":
                rows.append(
                    result(
                        "unknown",
                        ("impact_unknown", *impact.reason_codes),
                        scope_decision="unknown",
                    )
                )
                continue
            try:
                verified = registry.resolve_for_execution(guard_id)
                values.update(
                    source_evidence_id=verified.evidence.evidence_id,
                    source_evidence_ref=verified.guard.source_evidence_ref,
                    source_evidence_digest=verified.evidence.artifact_digest,
                )
                if isinstance(verified.guard, StandaloneGuard):
                    scope_digest, run_request, executor = prepare_standalone_replay(
                        request, output, mapping, inspection
                    )
                    values.update(
                        scope_decision="applicable",
                        scope_basis="standalone-snapshot-scope.v1",
                        scope_digest=scope_digest,
                        run_workspace_ref=f"work/{mapping.target_id}",
                    )
                    if _snapshot(registry.list()) != snapshot:
                        raise ArtifactIntegrityError("Registry changed before Docker execution")
                    run = executor.execute(run_request)
                elif isinstance(verified.guard, RepositoryGuard):
                    scope_digest, run_request, executor = prepare_repository_replay(
                        request, output, mapping, inspection
                    )
                    values.update(
                        scope_decision="applicable",
                        scope_basis="pilot-scope.v1",
                        scope_digest=scope_digest,
                        run_workspace_ref=f"work/{mapping.target_id}",
                    )
                    if _snapshot(registry.list()) != snapshot:
                        raise ArtifactIntegrityError("Registry changed before Docker execution")
                    run = executor.execute(run_request)
                elif config.schema_version != "project-config.v1":
                    rows.append(
                        result(
                            "unknown", "project_profile_requires_review", scope_decision="unknown"
                        )
                    )
                    continue
                elif review.profile != "root-pytest8.v1":
                    rows.append(
                        result("unknown", "runner_profile_mismatch", scope_decision="unknown")
                    )
                    continue
                else:
                    if files is None:
                        head, files, pins = read_committed_files(
                            request.repo, inspection.head_commit
                        )
                        if head != inspection.head_commit:
                            raise ArtifactIntegrityError("Head changed during verification")
                        head_pins = {pin.path: pin for pin in pins}
                        if any(
                            head_pins.get(pin.path) != pin
                            for pin in inspection.files
                            if pin.revision == "head"
                        ):
                            raise ArtifactIntegrityError("Committed inputs differ from inspection")
                    scope_digest, reason = _scope(verified, mapping, files)
                    if reason:
                        rows.append(result("unknown", reason, scope_decision="unknown"))
                        continue
                    preflight = inspect_execution_requirements(files)
                    write_immutable(output / "preflight.json", canonical_json_bytes(preflight))
                    if preflight["status"] != "eligible_candidate" or any(
                        warning["code"] == "dynamic_code_requires_target_review"
                        for warning in preflight["warnings"]
                    ):
                        rows.append(
                            result(
                                "unknown",
                                (
                                    "runner_profile_requires_review",
                                    *sorted({finding["code"] for finding in preflight["findings"]}),
                                ),
                                scope_decision="unknown",
                            )
                        )
                        continue
                    values.update(
                        scope_decision="applicable",
                        scope_basis="verified-evidence-source-snapshot.v1",
                        scope_digest=scope_digest,
                        run_workspace_ref=f"work/{mapping.target_id}",
                    )
                    if _snapshot(registry.list()) != snapshot:
                        raise ArtifactIntegrityError("Registry changed before Docker execution")
                    run = _execute_guard(request, output, inspection, mapping, verified, files)
                values["run"] = run
                registry.resolve_for_execution(guard_id)
                if _snapshot(registry.list()) != snapshot:
                    raise ArtifactIntegrityError("Registry changed during verification")
                if (
                    inspect_repository(request.repo, request.base, request.head, request.config)
                    != inspection
                ):
                    raise ArtifactIntegrityError("Repository/config changed during verification")
                verdict = {RunOutcome.PASSED: "pass", RunOutcome.TEST_FAILED: "violation"}.get(
                    run.outcome, "execution_error"
                )
                rows.append(
                    result(
                        verdict,
                        "runner_" + run.outcome.value if verdict == "execution_error" else None,
                    )
                )
            except StandaloneScopeUnknown as error:
                rows.append(result("unknown", str(error), scope_decision="unknown"))
            except UnsupportedRepositoryScope:
                rows.append(
                    result(
                        "unknown",
                        "repository_profile_outside_reviewed_scope",
                        scope_decision="unknown",
                    )
                )
            except GuardReplayIntegrityError as error:
                rows.append(
                    result("integrity_error", "post_execution_integrity_failure", run=error.run)
                )
            except ArtifactIntegrityError:
                rows.append(result("integrity_error", "verification_integrity_failure"))
            except RepositoryProblem as error:
                rows.append(
                    result(
                        "integrity_error" if error.rejected else "unknown",
                        error.code,
                        scope_decision="unknown",
                    )
                )
            except (OSError, ValueError):
                rows.append(result("execution_error", "docker_or_request_unavailable"))
    except ArtifactIntegrityError:
        issues.append(VerifyIssue(exit_code=5, reason_code="registry_or_input_integrity_failure"))
    except (OSError, ValueError):
        issues.append(VerifyIssue(exit_code=2, reason_code="invalid_or_unavailable_input"))
    code, counts = summarize(rows, issues)
    report = report_type(
        created_at=datetime.now(UTC),
        base_commit=inspection.base_commit if inspection else None,
        head_commit=inspection.head_commit if inspection else None,
        inspection_digest=inspection.artifact_digest if inspection else None,
        registry_snapshot_digest=snapshot,
        runner_id=review.runner_id if review else None,
        runner_image_digest=review.image_digest if review else None,
        runner_review_digest=review.artifact_digest if review else None,
        implementation_digests=inspection_implementation_digests(),
        rows=tuple(rows),
        issues=tuple(issues),
        counts=counts,
        exit_code=code,
        decision_digest=_decision_digest(rows, issues, counts, code),
        artifact_digest=ZERO,
    )
    report = report.model_copy(update={"artifact_digest": digest_json_artifact(report)})
    write_immutable(output / "report.json", canonical_json_bytes(report))
    write_immutable(output / "report.md", render_verify(report).encode())
    return report
