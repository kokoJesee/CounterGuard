"""Explicit fixture-only research namespace; never routed through production verify."""

from pathlib import Path
from typing import Annotated

import typer

from counterguard.diagnostics import public_diagnostic
from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.repository import RepositoryProblem
from counterguard.snapshot_admission import (
    bind_snapshot,
    issue_snapshot_review,
    prepare_snapshot_contract,
    verify_snapshot_binding,
)
from counterguard.snapshot_execution import SnapshotSession

app = typer.Typer(
    no_args_is_help=True, help="Fixture-only research snapshots; not production admission."
)


def _emit(call):
    try:
        value = call()
    except (ArtifactIntegrityError, RepositoryProblem) as error:
        typer.echo("Rejected: " + public_diagnostic(str(error)), err=True)
        raise typer.Exit(5) from error
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        typer.echo("Error: " + public_diagnostic(str(error)), err=True)
        raise typer.Exit(2) from error
    typer.echo(canonical_json_bytes(value).decode())
    return value


@app.command("prepare")
def prepare(
    repo: Annotated[Path, typer.Option()],
    buggy: Annotated[str, typer.Option()],
    fixed: Annotated[str, typer.Option()],
    test_ref: Annotated[str, typer.Option()],
    test_function: Annotated[str, typer.Option()],
    target: Annotated[str, typer.Option()],
    source_ref: Annotated[str, typer.Option()],
    import_root: Annotated[str, typer.Option()],
    contract_id: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
):
    """Statically prepare every assertion/parameter from the selected original test."""

    def call():
        if target.count(":") != 1:
            raise ValueError("Expected module:symbol")
        module, symbol = target.split(":")
        return prepare_snapshot_contract(
            repo,
            buggy=buggy,
            fixed=fixed,
            test_ref=test_ref,
            test_function=test_function,
            target_module=module,
            target_symbol=symbol,
            source_ref=source_ref,
            import_root=import_root,
            contract_id=contract_id,
            output=output,
        )

    _emit(call)


@app.command("bind")
def bind(
    repo: Annotated[Path, typer.Option()],
    head: Annotated[str, typer.Option()],
    contract_ref: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
):
    """Reconstruct B/F/H and bind the contract present in H; does not authorize execution."""
    _emit(lambda: bind_snapshot(repo, head=head, contract_ref=contract_ref, output=output))


@app.command("review")
def review(
    repo: Annotated[Path, typer.Option()],
    binding: Annotated[Path, typer.Option()],
    kind: Annotated[str, typer.Option()],
    reason: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
    timeout: float = 10.0,
):
    """Trusted operator review of tool-owned fixtures only. Retain its digest separately."""
    _emit(
        lambda: issue_snapshot_review(
            repo, binding, kind=kind, reason=reason, output=output, timeout=timeout
        )
    )


def _session(repo, binding, review, review_digest):
    return SnapshotSession(
        repo.resolve(strict=True),
        Path.cwd().resolve(strict=True),
        binding.resolve(strict=True),
        review.resolve(strict=True),
        review_digest,
    )


@app.command("capture")
def capture(
    repo: Annotated[Path, typer.Option()],
    binding: Annotated[Path, typer.Option()],
    review: Annotated[Path, typer.Option()],
    review_digest: Annotated[str, typer.Option()],
    evidence_id: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
):
    """Capture B/F in reviewed Docker. External targets are not authorized by this version."""
    value = _emit(
        lambda: _session(repo, binding, review, review_digest).capture(
            evidence_id=evidence_id, output=output
        )
    )
    if not value.reproduced:
        raise typer.Exit(3)


@app.command("compile")
def compile_guard(
    repo: Annotated[Path, typer.Option()],
    binding: Annotated[Path, typer.Option()],
    review: Annotated[Path, typer.Option()],
    review_digest: Annotated[str, typer.Option()],
    evidence: Annotated[Path, typer.Option()],
    guard_id: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
):
    """Retain exactly the observed failing cases, then self-check both source snapshots."""
    _emit(
        lambda: _session(repo, binding, review, review_digest).compile(
            evidence, guard_id=guard_id, output=output
        )
    )


@app.command("replay")
def replay(
    repo: Annotated[Path, typer.Option()],
    binding: Annotated[Path, typer.Option()],
    review: Annotated[Path, typer.Option()],
    review_digest: Annotated[str, typer.Option()],
    evidence: Annotated[Path, typer.Option()],
    guard: Annotated[Path, typer.Option()],
    role: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
):
    """Replay only exact reviewed B/F fixture snapshots; no learned applicability claim."""
    value = _emit(
        lambda: _session(repo, binding, review, review_digest).replay(
            guard, evidence_path=evidence, role=role, output=output
        )
    )
    if value.execution.run.pytest_exit_code != 0:
        raise typer.Exit(1 if value.execution.run.pytest_exit_code == 1 else 3)


@app.command("audit-binding")
def audit_binding(repo: Annotated[Path, typer.Option()], binding: Annotated[Path, typer.Option()]):
    """Read-only reconstruction; no Docker or candidate imports."""
    _emit(lambda: verify_snapshot_binding(repo, binding))


@app.command("audit")
def audit(
    repo: Annotated[Path, typer.Option()],
    binding: Annotated[Path, typer.Option()],
    review: Annotated[Path, typer.Option()],
    review_digest: Annotated[str, typer.Option()],
    evidence: Annotated[Path, typer.Option()],
    guard: Path | None = None,
    replay: Path | None = None,
):
    """Read-only rebuild of Evidence, optional Guard and Replay; never starts Docker."""

    def call():
        engine = _session(repo, binding, review, review_digest)
        if replay is not None:
            if guard is None:
                raise ValueError("Replay audit requires --guard")
            return engine.verify_replay(replay, guard_path=guard, evidence_path=evidence)
        if guard is not None:
            return engine.verify_guard(guard, evidence_path=evidence)
        return engine.verify_evidence(evidence)

    _emit(call)
