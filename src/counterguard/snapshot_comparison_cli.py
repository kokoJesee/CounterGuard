"""Comparison commands expose only the approved tool-owned fixture purpose."""

from pathlib import Path
from typing import Annotated

import typer

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes
from counterguard.snapshot_admission import read_value
from counterguard.snapshot_cli import _emit, _session
from counterguard.snapshot_comparison import SnapshotComparisonSession
from counterguard.snapshot_comparison_data import (
    create_comparison_map,
    inspect_snapshot_target,
    issue_comparison_review,
)
from counterguard.snapshot_comparison_models import (
    SnapshotComparisonPlan,
    SnapshotComparisonTarget,
    SnapshotTargetEntry,
)

app = typer.Typer(
    no_args_is_help=True, help="Fixture-only independent snapshot comparisons; no external targets."
)


@app.command("inspect-target")
def inspect_target(
    repo: Annotated[Path, typer.Option()],
    revision: Annotated[str, typer.Option()],
    target_id: Annotated[str, typer.Option()],
    target: Annotated[str, typer.Option()],
    source_ref: Annotated[str, typer.Option()],
    import_root: Annotated[str, typer.Option()],
    license_ref: Annotated[str, typer.Option()],
    interface: Annotated[str, typer.Option()],
    interface_basis_ref: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
):
    """Read complete committed target snapshots; inspection grants no execution authority."""

    def call():
        if target.count(":") != 1:
            raise ValueError("Expected module:symbol")
        module, symbol = target.split(":")
        return inspect_snapshot_target(
            repo,
            revision,
            target_id=target_id,
            entry=SnapshotTargetEntry(
                target_module=module,
                target_symbol=symbol,
                source_ref=source_ref,
                import_root=import_root,
            ),
            license_ref=license_ref,
            interface_kind=interface,
            interface_basis_ref=interface_basis_ref,
            output=output,
        )[0]

    _emit(call)


@app.command("map")
def mapping(
    repo: Annotated[Path, typer.Option()],
    binding: Annotated[Path, typer.Option()],
    review: Annotated[Path, typer.Option()],
    review_digest: Annotated[str, typer.Option()],
    evidence: Annotated[Path, typer.Option()],
    guard: Annotated[Path, typer.Option()],
    target: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
):
    """Map every minimal source case identically; cannot rename/drop inputs or change oracle."""

    def call():
        source = _session(repo, binding, review, review_digest)
        value = source.verify_guard(guard, evidence_path=evidence)
        bound = source.context()[0]
        result = create_comparison_map(
            value, bound.contract, read_value(target, SnapshotComparisonTarget)
        )
        write_immutable(output, canonical_json_bytes(result))
        return result

    _emit(call)


@app.command("review")
def review_comparison(
    repo: Annotated[Path, typer.Option()],
    binding: Annotated[Path, typer.Option()],
    review: Annotated[Path, typer.Option()],
    review_digest: Annotated[str, typer.Option()],
    target_repo: Annotated[Path, typer.Option()],
    plan: Annotated[Path, typer.Option()],
    source_interface: Annotated[str, typer.Option()],
    source_interface_basis_ref: Annotated[str, typer.Option()],
    reason: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
    action: str = "approve",
):
    """Separate local comparison review; retain returned digest outside mutable plan files."""
    _emit(
        lambda: issue_comparison_review(
            _session(repo, binding, review, review_digest),
            target_repo,
            read_value(plan, SnapshotComparisonPlan),
            output=output,
            reason=reason,
            source_interface=source_interface,
            source_interface_basis_ref=source_interface_basis_ref,
            action=action,
        )
    )


@app.command("run")
def run(
    repo: Annotated[Path, typer.Option()],
    binding: Annotated[Path, typer.Option()],
    review: Annotated[Path, typer.Option()],
    review_digest: Annotated[str, typer.Option()],
    target_repo: Annotated[Path, typer.Option()],
    plan: Annotated[Path, typer.Option()],
    comparison_digest: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
    audit_only: bool = False,
):
    """Audited Docker replay or read-only decision; unknown/inapplicable never start Docker."""

    def call():
        source = _session(repo, binding, review, review_digest)
        engine = SnapshotComparisonSession(
            source, target_repo.resolve(strict=True), comparison_digest
        )
        value = read_value(plan, SnapshotComparisonPlan)
        return engine.audit(value) if audit_only else engine.run(value, output=output)

    value = _emit(call)
    if audit_only:
        if value.decision == "unknown":
            raise typer.Exit(4)
        return
    code = {
        "passed": 0,
        "test_failed": 1,
        "skipped_inapplicable": 0,
        "skipped_unknown": 4,
        "infrastructure_error": 3,
        "integrity_error": 5,
    }[value.outcome]
    if code:
        raise typer.Exit(code)


@app.command("verify")
def verify(
    repo: Annotated[Path, typer.Option()],
    binding: Annotated[Path, typer.Option()],
    review: Annotated[Path, typer.Option()],
    review_digest: Annotated[str, typer.Option()],
    target_repo: Annotated[Path, typer.Option()],
    comparison_digest: Annotated[str, typer.Option()],
    replay: Annotated[Path, typer.Option()],
):
    """Read-only provenance and raw JUnit reconstruction; never launches Docker."""
    _emit(
        lambda: SnapshotComparisonSession(
            _session(repo, binding, review, review_digest),
            target_repo.resolve(strict=True),
            comparison_digest,
        ).verify(replay)
    )
