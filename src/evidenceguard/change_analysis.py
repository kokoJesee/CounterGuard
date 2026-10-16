"""Map committed file changes to declared candidates; never infer Scope applicability."""

import json
from pathlib import Path
from typing import Literal

from evidenceguard.digests import digest_file, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.models import Digest, FrozenModel
from evidenceguard.project_config import ProjectConfig, RepositoryPath, load_project_config
from evidenceguard.repository import FileChange, FilePin, RepositorySnapshot, read_repository


class TargetImpact(FrozenModel):
    target_id: str
    guard_id: str
    source_ref: RepositoryPath
    symbol: str
    impact: Literal["affected", "unaffected", "unknown"]
    changed_inputs: tuple[RepositoryPath, ...]
    reason_codes: tuple[str, ...] = ()
    execution_allowed: Literal[False] = False


class InspectionReport(FrozenModel):
    schema_version: Literal["repository-inspection.v1"] = "repository-inspection.v1"
    project_id: str
    status: Literal["ready", "unknown", "rejected"]
    reason_codes: tuple[str, ...]
    requested_base: str
    requested_head: str
    base_commit: str | None
    head_commit: str | None
    shallow: bool
    git_version: str | None
    config_digest: Digest
    implementation_digests: dict[str, Digest]
    changes: tuple[FileChange, ...]
    files: tuple[FilePin, ...]
    unmapped_paths: tuple[RepositoryPath, ...]
    targets: tuple[TargetImpact, ...]
    source_selection: Literal["committed_objects_only"] = "committed_objects_only"
    mapping_trust: Literal["declared_not_semantically_verified"] = (
        "declared_not_semantically_verified"
    )
    execution_allowed: Literal[False] = False
    execution_outcome: Literal["not_run"] = "not_run"
    artifact_digest: Digest


def inspection_implementation_digests() -> dict[str, Digest]:
    """Hash every Python source file in the installed EvidenceGuard package."""
    package = Path(__file__).parent
    return {
        path.relative_to(package).as_posix(): digest_file(path)
        for path in sorted(package.rglob("*.py"))
    }


def verify_inspection_report(
    report: InspectionReport, *, require_current_implementation: bool = True
) -> InspectionReport:
    """Verify report integrity and, for execution admission, its current code binding."""
    if digest_json_artifact(report) != report.artifact_digest:
        raise ArtifactIntegrityError("Repository inspection artifact digest mismatch")
    if (
        require_current_implementation
        and report.implementation_digests != inspection_implementation_digests()
    ):
        raise ArtifactIntegrityError(
            "Repository inspection was produced by a different EvidenceGuard implementation"
        )
    return report


def analyze_changes(
    config: ProjectConfig, snapshot: RepositorySnapshot
) -> tuple[tuple[TargetImpact, ...], tuple[str, ...]]:
    """Exact file/dependency mapping, with uncertainty propagated to every candidate."""
    changed = {row.path for row in snapshot.changes}
    mapped = {ref for target in config.targets for ref in target.input_refs()} | set(
        config.audit_refs
    )
    unmapped = tuple(sorted(changed - mapped - set(config.ignored_paths)))
    present = {pin.path for pin in snapshot.files if pin.revision == "head"}
    targets = []
    for target in sorted(config.targets, key=lambda row: row.target_id):
        related = tuple(sorted(changed.intersection(target.input_refs())))
        reasons = set(snapshot.reason_codes)
        if unmapped:
            reasons.add("unmapped_changed_paths")
        if snapshot.status == "ready" and not (
            set(target.input_refs()) | set(config.audit_refs)
        ).issubset(present):
            reasons.add("missing_declared_head_input")
        impact = (
            "unknown"
            if reasons or snapshot.status != "ready"
            else "affected"
            if related
            else "unaffected"
        )
        targets.append(
            TargetImpact(
                target_id=target.target_id,
                guard_id=target.guard_id,
                source_ref=target.source_ref,
                symbol=target.symbol,
                impact=impact,
                changed_inputs=related,
                reason_codes=tuple(sorted(reasons)),
            )
        )
    return tuple(targets), unmapped


def inspect_repository(
    repo: str | Path, base: str, head: str, config_path: str | Path
) -> InspectionReport:
    config, digest = load_project_config(config_path)
    refs = tuple(
        sorted(
            {p for target in config.targets for p in target.input_refs()} | set(config.audit_refs)
        )
    )
    snapshot = read_repository(repo, base, head, refs)
    targets, unmapped = analyze_changes(config, snapshot)
    reasons = tuple(
        sorted(
            {reason for target in targets for reason in target.reason_codes}
            | set(snapshot.reason_codes)
        )
    )
    status = (
        "rejected" if snapshot.status == "rejected" else "unknown" if reasons else snapshot.status
    )
    report = InspectionReport(
        project_id=config.project_id,
        status=status,
        reason_codes=reasons,
        requested_base=base,
        requested_head=head,
        base_commit=snapshot.base_commit,
        head_commit=snapshot.head_commit,
        shallow=snapshot.shallow,
        git_version=snapshot.git_version,
        config_digest=digest,
        implementation_digests=inspection_implementation_digests(),
        changes=snapshot.changes,
        files=snapshot.files,
        unmapped_paths=unmapped,
        targets=targets,
        artifact_digest="sha256:" + "0" * 64,
    )
    return report.model_copy(update={"artifact_digest": digest_json_artifact(report)})


def render_inspection(report: InspectionReport, format: str) -> str:
    if format == "json":
        return (
            json.dumps(report.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, indent=2)
            + "\n"
        )
    if format not in {"text", "markdown"}:
        raise ValueError("Unsupported inspection format")
    lines = [
        ("# " if format == "markdown" else "") + "EvidenceGuard inspect",
        "",
        f"status: {report.status}",
        f"base: {report.base_commit or 'unknown'}",
        f"head: {report.head_commit or 'unknown'}",
        "execution: not_run; execution_allowed: false",
        "Impact candidates are declared file mappings, not Scope decisions.",
        "reasons: " + (", ".join(report.reason_codes) or "none"),
        "",
    ]
    lines.extend(
        f"{row.target_id} | {row.guard_id} | {row.impact} | "
        + (", ".join(row.reason_codes) or "exact mapped input comparison")
        for row in report.targets
    )
    lines.append("artifact_digest: " + report.artifact_digest)
    return "\n".join(lines) + "\n"
