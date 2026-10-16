"""Offline Demo publication with immutable JSON facts and derived Markdown."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes, digest_file, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import Digest, FrozenModel, Guard, UtcDateTime
from counterguard.path_limits import require_publication
from counterguard.pipeline import ArtifactLink, PipelineManifest, run_pipeline, verify_pipeline
from counterguard.protocol import _load_model, _path
from counterguard.replay import ReplayResult
from counterguard.report import CommandReport, OutputFormat, present_replay, render_report
from counterguard.scope import ScopeLearningResult
from counterguard.workspace import EMPTY_DIGEST


class DemoReport(FrozenModel):
    schema_version: Literal["demo-report.v1"] = "demo-report.v1"
    created_at: UtcDateTime
    pipeline: ArtifactLink
    presentation_code_digests: dict[str, Digest]
    report: CommandReport
    artifact_digest: Digest


def _code() -> dict[str, str]:
    package = Path(__file__).parent
    return {name: digest_file(package / name) for name in ("demo.py", "report.py")}


def _facts(manifest: PipelineManifest, source: Path) -> CommandReport:
    rows = []
    for row in manifest.replays:
        result = _load_model(_path(Path(row.replay.ref), source), ReplayResult)
        rows.append(
            present_replay(
                result.model_dump(mode="json"), sample_id=row.sample_id, source_ref=row.replay.ref
            )
        )
    groups = []
    for group in manifest.groups:
        guard = _load_model(_path(Path(group.guard.ref), source), Guard)
        rules = {}
        for phase in ("initial", "refined"):
            link = getattr(group, phase + "_learning")
            learned = _load_model(_path(Path(link.ref), source), ScopeLearningResult)
            rules[phase] = learned.model_dump(mode="json")
        groups.append(
            {
                "guard_id": group.guard_id,
                "failed_case_ids": [case.case_id for case in guard.cases],
                "provenance": group.model_dump(mode="json"),
                "rules": rules,
            }
        )
    return CommandReport(
        operation="demo",
        replays=tuple(rows),
        payload={
            "run_id": manifest.run_id,
            "scenario_id": manifest.scenario_id,
            "scenario_ref": manifest.scenario_ref,
            "accepted": manifest.accepted,
            "replay_execution_count": manifest.execution_count,
            "verdict_counts": manifest.verdict_counts,
            "groups": groups,
            "scope": "frozen training examples; not a new holdout evaluation",
        },
    )


def _draft(manifest, output, source, created_at) -> DemoReport:
    draft = DemoReport(
        created_at=created_at,
        pipeline=ArtifactLink(
            ref=(output / "run_manifest.json").relative_to(source).as_posix(),
            artifact_digest=manifest.artifact_digest,
        ),
        presentation_code_digests=_code(),
        report=_facts(manifest, source),
        artifact_digest=EMPTY_DIGEST,
    )
    return draft.model_copy(update={"artifact_digest": digest_json_artifact(draft)})


def verify_demo(path: str | Path, *, cwd: str | Path) -> DemoReport:
    source = Path(cwd).resolve(strict=True)
    path = _path(Path(path), source)
    if path.name != "report.json":
        raise ArtifactIntegrityError("Demo completion marker must be report.json")
    record = _load_model(path, DemoReport)
    manifest = verify_pipeline(path.parent / "run_manifest.json", cwd=source)
    expected = _draft(manifest, path.parent, source, record.created_at)
    if record != expected:
        raise ArtifactIntegrityError("Demo facts/provenance differ from verified Pipeline")
    if record.created_at < manifest.created_at:
        raise ArtifactIntegrityError("Demo cannot predate its Pipeline")
    try:
        markdown = (path.parent / "report.md").read_bytes()
    except OSError as error:
        raise ArtifactIntegrityError("Demo Markdown is missing or unavailable") from error
    if markdown != render_report(record, OutputFormat.MARKDOWN).encode("utf-8"):
        raise ArtifactIntegrityError("Demo Markdown differs from its JSON facts")
    return record


def run_demo(scenario: str | Path, *, cwd: str | Path, workspace: str | Path) -> DemoReport:
    source = Path(cwd).resolve(strict=True)
    output = _path(Path(workspace), source)
    for name in ("report.json", "report.md"):
        require_publication(output / name)
    marker = output / "report.json"
    if marker.exists():
        result = verify_demo(marker, cwd=source)
        if (
            result.report.payload["scenario_ref"]
            != _path(Path(scenario), source).relative_to(source).as_posix()
        ):
            raise ArtifactIntegrityError("Demo workspace belongs to another scenario file")
        return result
    # A partial Demo is history, not an invitation to regenerate missing files.
    if output.exists() and any(output.iterdir()):
        raise ArtifactIntegrityError("Demo workspace must be empty; use a new version directory")
    manifest = run_pipeline(scenario, cwd=source, workspace=output)
    record = _draft(manifest, output, source, datetime.now(UTC))
    # Markdown first, JSON completion marker last; a partial publication never looks complete.
    write_immutable(output / "report.md", render_report(record, OutputFormat.MARKDOWN).encode())
    write_immutable(marker, canonical_json_bytes(record) + b"\n")
    return verify_demo(marker, cwd=source)
