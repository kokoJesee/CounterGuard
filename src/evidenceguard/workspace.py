"""Prepare a pinned input mirror without importing old runtime artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, ValidationError, model_validator

from evidenceguard.artifacts import write_immutable
from evidenceguard.digests import canonical_json_bytes, digest_file, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.evidence import parse_target_ref
from evidenceguard.independent_verifier import VerificationRequest
from evidenceguard.models import ArtifactRef, Digest, FrozenModel, NonEmptyText, UtcDateTime
from evidenceguard.module_context import SCOPE_V1_CONTEXT_DIGEST, load_module_context
from evidenceguard.path_limits import (
    PLACEHOLDER_ID,
    require_publication,
    require_replay_directory,
    require_run_directory,
)
from evidenceguard.predicates import EXTRACTOR_VERSION
from evidenceguard.protocol import (
    BenchmarkSample,
    ExperimentProtocol,
    SplitManifest,
    _load_model,
    _path,
    _read_samples,
    json_content_digest,
    source_text_digest,
)
from evidenceguard.scope import SCOPE_V1_PROTOCOL_DIGEST
from evidenceguard.verification_gate import _layout, _preflight

EMPTY_DIGEST = "sha256:" + "0" * 64


class ScenarioGuard(FrozenModel):
    guard_id: NonEmptyText
    request_ref: ArtifactRef
    replay_sample_ids: Annotated[tuple[NonEmptyText, ...], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def distinct_samples(self) -> Self:
        if len(set(self.replay_sample_ids)) != 3:
            raise ValueError("Each Guard requires three distinct training replay samples")
        return self


class PipelineScenario(FrozenModel):
    schema_version: Literal["pipeline-scenario.v1"] = "pipeline-scenario.v1"
    scenario_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=48)]
    protocol_ref: ArtifactRef
    guards: Annotated[tuple[ScenarioGuard, ...], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def distinct_guards(self) -> Self:
        if len({group.guard_id for group in self.guards}) != 2:
            raise ValueError("Scenario requires the two distinct frozen Guard bindings")
        if len({group.request_ref for group in self.guards}) != 2:
            raise ValueError("Guards must use distinct verification requests")
        return self


class InputPin(FrozenModel):
    """The same relative path is used in the source and mirrored workspaces."""

    ref: ArtifactRef
    content_digest: Digest


class WorkspaceManifest(FrozenModel):
    schema_version: Literal["pipeline-workspace.v1"] = "pipeline-workspace.v1"
    created_at: UtcDateTime
    runtime_ref: ArtifactRef
    scenario_ref: ArtifactRef
    scenario_digest: Digest
    files: Annotated[tuple[InputPin, ...], Field(min_length=1)]
    artifact_digest: Digest

    @model_validator(mode="after")
    def canonical_pins(self) -> Self:
        refs = [pin.ref for pin in self.files]
        if refs != sorted(set(refs)):
            raise ValueError("Workspace inputs must be sorted and unique")
        if (self.scenario_ref, self.scenario_digest) not in {
            (pin.ref, pin.content_digest) for pin in self.files
        }:
            raise ValueError("Workspace must pin its source scenario")
        return self


def load_scenario(path: Path) -> PipelineScenario:
    """mvp.yaml deliberately uses the JSON subset; no general YAML parser is installed."""
    try:
        return PipelineScenario.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise ValueError(
            "Scenario must match pipeline-scenario.v1 in JSON-compatible YAML"
        ) from error


def scenario_inputs(
    scenario: PipelineScenario,
    *,
    cwd: Path,
) -> tuple[
    ExperimentProtocol,
    SplitManifest,
    dict[str, BenchmarkSample],
    dict[str, VerificationRequest],
    set[str],
]:
    """Validate frozen data before any capture; no existing Guard is required."""
    protocol = _load_model(_path(Path(scenario.protocol_ref), cwd), ExperimentProtocol)
    split = _load_model(_path(Path(protocol.split_ref), cwd), SplitManifest)
    if (
        protocol.artifact_digest != SCOPE_V1_PROTOCOL_DIGEST
        or split.artifact_digest != protocol.split_digest
        or {group.guard_id for group in scenario.guards} != {b.guard_id for b in protocol.guards}
        or set(split.phases) != {b.guard_id for b in protocol.guards}
    ):
        raise ArtifactIntegrityError("Pipeline requires the unchanged scope_v1 protocol/split")
    context_ref = "benchmarks/context/scope_v1.json"
    context = load_module_context(_path(Path(context_ref), cwd))
    if context.artifact_digest != SCOPE_V1_CONTEXT_DIGEST:
        raise ArtifactIntegrityError("Pipeline module context changed")
    refs = {scenario.protocol_ref, protocol.split_ref, context_ref, *split.source_text_digests}
    train = {}
    observed = {guard_id: {"train": set(), "holdout": set()} for guard_id in split.phases}
    seen = set()
    for file in split.files:
        path = _path(Path(file.path), cwd)
        refs.add(file.path)
        if file.guard_id not in observed or json_content_digest(path) != file.content_digest:
            raise ArtifactIntegrityError("Pipeline dataset digest/identity mismatch")
        for sample in _read_samples(path):
            if sample.sample_id in seen or sample.labels.guard_id != file.guard_id:
                raise ArtifactIntegrityError("Pipeline duplicate or cross-Guard sample")
            seen.add(sample.sample_id)
            observed[file.guard_id][file.split].add(sample.sample_id)
            if file.split == "train":
                train[sample.sample_id] = sample
    for guard_id, phase in split.phases.items():
        if observed[guard_id]["train"] != set(
            phase.initial + phase.refinement_additions
        ) or observed[guard_id]["holdout"] != set(phase.holdout):
            raise ArtifactIntegrityError("Pipeline frozen phase membership changed")
    for ref, digest in split.source_text_digests.items():
        if source_text_digest(_path(Path(ref), cwd)) != digest:
            raise ArtifactIntegrityError("Pipeline frozen source/contract changed")
    requests = {}
    for group in scenario.guards:
        try:
            request = VerificationRequest.model_validate_json(
                _path(Path(group.request_ref), cwd).read_bytes()
            )
        except ValidationError as error:
            raise ValueError("Pipeline verification request schema is invalid") from error
        requests[group.guard_id] = request
        refs.update((group.request_ref, request.response_ref))
        targets = {}
        for role, spec in (("buggy", request.buggy_target), ("fixed", request.fixed_target)):
            target, _ = parse_target_ref(spec, cwd=cwd)
            if target.source_ref not in split.source_text_digests:
                raise ArtifactIntegrityError("Pipeline capture source is outside frozen corpus")
            targets[role] = (target.module, target.symbol)
        selected = [train.get(sample_id) for sample_id in group.replay_sample_ids]
        if any(sample is None or sample.labels.guard_id != group.guard_id for sample in selected):
            raise ValueError("Pipeline replay selectors must be matching training members")
        buggy = [s for s in selected if s.labels.guard_applicable and s.labels.guard_violation]
        fixed = [s for s in selected if s.labels.guard_applicable and not s.labels.guard_violation]
        legal = [
            s for s in selected if not s.labels.guard_applicable and s.labels.contract_compliant
        ]
        if len(buggy) != 1 or len(fixed) != 1 or len(legal) != 1:
            raise ValueError(
                "Pipeline requires a source bug, fixed positive and confirmed legal counterexample"
            )
        if (
            (buggy[0].target.module, buggy[0].target.symbol) != targets["buggy"]
            or (fixed[0].target.module, fixed[0].target.symbol) != targets["fixed"]
            or buggy[0].contract_ref != request.contract_ref
            or fixed[0].contract_ref != request.contract_ref
        ):
            raise ArtifactIntegrityError("Pipeline replay/source pair differs from capture inputs")
    if len({request.request_id for request in requests.values()}) != len(requests):
        raise ValueError("Pipeline verification request IDs must be unique")
    # Only required package initializers, never an unrestricted directory copy.
    for ref in tuple(refs):
        if ref.endswith(".py"):
            for parent in Path(ref).parents:
                if parent == Path("."):
                    continue
                initializer = parent / "__init__.py"
                if _path(initializer, cwd).is_file():
                    refs.add(initializer.as_posix())
    return protocol, split, train, requests, refs


def preflight_workspace(
    root: Path,
    pins: tuple[InputPin, ...],
    scenario: PipelineScenario,
    requests: dict[str, VerificationRequest],
    samples: dict[str, BenchmarkSample],
) -> None:
    runtime = root / "w"
    for name in ("workspace_manifest.json", "run_manifest.json", "failure.json"):
        require_publication(root / name)
    for pin in pins:
        require_publication(runtime / pin.ref)
    for request in requests.values():
        directory, evidence, identity = _layout(runtime / "artifacts", request)
        _preflight(directory, evidence, identity)
    for group in scenario.guards:
        directory = runtime / "artifacts/guards" / group.guard_id
        require_publication(directory / "guard.json")
        require_publication(directory / "test_guard.py")
        for phase in ("initial", "refined"):
            fitted = runtime / "artifacts/fitted" / phase
            require_publication(fitted / f"{group.guard_id}.json")
            require_publication(fitted / f"{group.guard_id}.learning.json")
            require_publication(fitted / "fit-manifest.json")
        for sample_id in group.replay_sample_ids:
            require_publication(
                runtime
                / "artifacts/features"
                / EXTRACTOR_VERSION
                / SCOPE_V1_CONTEXT_DIGEST.split(":")[1][:16]
                / f"{sample_id}.json"
            )
    require_run_directory(runtime / "artifacts/runs" / f"run_{PLACEHOLDER_ID}")
    require_replay_directory(runtime / "artifacts/replays" / f"rpl_{PLACEHOLDER_ID}")
    for directory in ("history", "snapshots"):
        require_publication(runtime / "artifacts/audits" / directory / ("0" * 64 + ".json"))
    require_publication(runtime / "artifacts/audits/scope-v1-features-context.json")
    # Feature audit includes all 15 annotations, not only the six demo selections.
    for sample in samples.values():
        require_publication(
            runtime
            / "artifacts/features"
            / EXTRACTOR_VERSION
            / SCOPE_V1_CONTEXT_DIGEST.split(":")[1][:16]
            / f"{sample.sample_id}.json"
        )


def prepare_workspace(scenario_path: Path, *, cwd: Path, output: Path) -> WorkspaceManifest:
    source = _path(scenario_path, cwd)
    scenario = load_scenario(source)
    _, split, train, requests, refs = scenario_inputs(scenario, cwd=cwd)
    refs.add(source.relative_to(cwd).as_posix())
    pins = tuple(
        InputPin(ref=ref, content_digest=digest_file(_path(Path(ref), cwd))) for ref in sorted(refs)
    )
    all_samples = {
        s.sample_id: s for file in split.files for s in _read_samples(_path(Path(file.path), cwd))
    }
    preflight_workspace(output, pins, scenario, requests, all_samples)
    if output == cwd or (output.exists() and any(output.iterdir())):
        raise ArtifactIntegrityError(
            "Pipeline workspace must be empty; use a new version directory"
        )
    runtime = output / "w"
    draft = WorkspaceManifest(
        created_at=datetime.now(UTC),
        runtime_ref=runtime.relative_to(cwd).as_posix(),
        scenario_ref=source.relative_to(cwd).as_posix(),
        scenario_digest=digest_file(source),
        files=pins,
        artifact_digest=EMPTY_DIGEST,
    )
    manifest = draft.model_copy(update={"artifact_digest": digest_json_artifact(draft)})
    for pin in pins:
        raw = _path(Path(pin.ref), cwd).read_bytes()
        write_immutable(runtime / pin.ref, raw)
    verify_workspace(manifest, cwd=cwd)
    write_immutable(output / "workspace_manifest.json", canonical_json_bytes(manifest) + b"\n")
    return manifest


def verify_workspace(manifest: WorkspaceManifest, *, cwd: Path) -> Path:
    if digest_json_artifact(manifest) != manifest.artifact_digest:
        raise ArtifactIntegrityError("Pipeline workspace self digest mismatch")
    runtime = _path(Path(manifest.runtime_ref), cwd)
    if runtime.name != "w" or runtime == cwd:
        raise ArtifactIntegrityError("Pipeline runtime namespace changed")
    for pin in manifest.files:
        for base in (cwd, runtime):
            try:
                actual = digest_file(_path(Path(pin.ref), base))
            except OSError as error:
                raise ArtifactIntegrityError("Pipeline workspace input is missing") from error
            if actual != pin.content_digest:
                raise ArtifactIntegrityError("Pipeline source/snapshot input digest mismatch")
    scenario = load_scenario(_path(Path(manifest.scenario_ref), cwd))
    _, _, _, _, required = scenario_inputs(scenario, cwd=cwd)
    required.add(manifest.scenario_ref)
    if {pin.ref for pin in manifest.files} != required:
        raise ArtifactIntegrityError("Pipeline workspace input coverage mismatch")
    return runtime
