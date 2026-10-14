"""Validate the frozen experiment and execute its two baseline methods."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Self

from pydantic import TypeAdapter, model_validator

from evidenceguard.artifacts import write_immutable
from evidenceguard.baselines import (
    ConfusionCounts,
    FeatureVector,
    ScopePredicate,
    count_predictions,
    decide_scope,
    make_baseline,
)
from evidenceguard.compiler import run_guard, verify_guard
from evidenceguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.models import ArtifactRef, Digest, FrozenModel, Guard, NonEmptyText, RunOutcome

METHODS = {
    "b1_always": "always",
    "b2_interface": "interface_kind_eq_frozen_guard_interface",
    "learned_initial": "fit_initial_train_only",
    "learned_refined": "refit_initial_plus_counterexamples_train_only",
}
EXPECTED_TRAIN = {
    "b1_always": {"tp": 4, "fp": 5, "tn": 0, "fn": 0},
    "b2_interface": {"tp": 4, "fp": 3, "tn": 2, "fn": 0},
}
GUARD_SEMANTIC_FIELDS = (
    "guard_id",
    "guard_version",
    "contract_id",
    "target_interface",
    "argument_types",
    "return_type",
    "cases",
    "generator_version",
    "test_digest",
)


class SampleTarget(FrozenModel):
    module: NonEmptyText
    symbol: NonEmptyText


class SampleLabels(FrozenModel):
    guard_id: NonEmptyText
    guard_applicable: bool
    guard_violation: bool | None
    contract_compliant: bool
    basis: NonEmptyText

    @model_validator(mode="after")
    def separate_labels(self) -> Self:
        if self.guard_applicable == (self.guard_violation is None):
            raise ValueError("Guard violation is defined only for applicable samples")
        return self


class BenchmarkSample(FrozenModel):
    sample_id: NonEmptyText
    contract_ref: ArtifactRef
    target: SampleTarget
    features: FeatureVector
    labels: SampleLabels


class DatasetFile(FrozenModel):
    path: ArtifactRef
    split: Literal["train", "holdout"]
    guard_id: NonEmptyText
    content_digest: Digest


class TrainingPhases(FrozenModel):
    initial: tuple[NonEmptyText, ...]
    refinement_additions: tuple[NonEmptyText, ...]
    holdout: tuple[NonEmptyText, ...]

    @model_validator(mode="after")
    def disjoint_phases(self) -> Self:
        lists = (self.initial, self.refinement_additions, self.holdout)
        if any(not values or len(values) != len(set(values)) for values in lists):
            raise ValueError("All phases must be nonempty with unique sample IDs")
        if len(set().union(*map(set, lists))) != sum(map(len, lists)):
            raise ValueError("Initial, refinement, and holdout IDs must be disjoint")
        return self


class SplitManifest(FrozenModel):
    schema_version: Literal["split-manifest.v1"] = "split-manifest.v1"
    split_id: Literal["scope_v1"] = "scope_v1"
    files: tuple[DatasetFile, ...]
    phases: dict[str, TrainingPhases]
    source_text_digests: dict[ArtifactRef, Digest]
    artifact_digest: Digest


class GuardBinding(FrozenModel):
    guard_id: NonEmptyText
    guard_ref: ArtifactRef
    contract_family: NonEmptyText
    frozen_interface_kind: Literal["final_price", "query_parameter"]
    semantic_digest: Digest


class ExperimentProtocol(FrozenModel):
    schema_version: Literal["experiment-protocol.v1"] = "experiment-protocol.v1"
    protocol_id: Literal["scope_v1"] = "scope_v1"
    unit: Literal["labeled_guard_sample_row"] = "labeled_guard_sample_row"
    split_ref: ArtifactRef
    split_digest: Digest
    methods: dict[str, str]
    guards: tuple[GuardBinding, ...]
    expected_train: dict[str, ConfusionCounts]
    artifact_digest: Digest

    @model_validator(mode="after")
    def fixed_methods(self) -> Self:
        if self.methods != METHODS:
            raise ValueError("scope_v1 method definitions are frozen; change the protocol version")
        if {k: v.model_dump() for k, v in self.expected_train.items()} != EXPECTED_TRAIN:
            raise ValueError("scope_v1 training acceptance counts are frozen")
        ids = [guard.guard_id for guard in self.guards]
        if len(ids) != 2 or len(ids) != len(set(ids)):
            raise ValueError("scope_v1 requires two distinct Guard bindings")
        return self


def guard_semantic_digest(guard: Guard) -> Digest:
    """Pin executable meaning while allowing fresh capture timestamps and run IDs."""
    return digest_bytes(
        canonical_json_bytes({field: getattr(guard, field) for field in GUARD_SEMANTIC_FIELDS})
    )


def json_content_digest(path: Path) -> Digest:
    return digest_bytes(canonical_json_bytes(json.loads(path.read_bytes())))


def source_text_digest(path: Path) -> Digest:
    """Corpus text pins normalize CRLF only; execution Evidence still hashes raw bytes."""
    return digest_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def verify_protocol(
    path: str | Path, *, cwd: str | Path
) -> tuple[ExperimentProtocol, SplitManifest, dict[str, Guard]]:
    workspace = Path(cwd).resolve(strict=True)
    protocol = _load_model(_path(Path(path), workspace), ExperimentProtocol)
    manifest = _load_model(_path(Path(protocol.split_ref), workspace), SplitManifest)
    if manifest.artifact_digest != protocol.split_digest:
        raise ArtifactIntegrityError("Protocol split digest mismatch")
    bindings = {binding.guard_id: binding for binding in protocol.guards}
    if set(manifest.phases) != set(bindings):
        raise ArtifactIntegrityError("Split phases and Guard bindings disagree")
    guards = {}
    for binding in protocol.guards:
        guard = verify_guard(_path(Path(binding.guard_ref), workspace), cwd=workspace)
        if (
            guard.guard_id != binding.guard_id
            or guard_semantic_digest(guard) != binding.semantic_digest
            or guard.target_interface.contract_family != binding.contract_family
            or guard.target_interface.interface_kind != binding.frozen_interface_kind
        ):
            raise ArtifactIntegrityError("Frozen Guard semantics/interface mismatch")
        guards[guard.guard_id] = guard
    observed = {guard_id: {"train": set(), "holdout": set()} for guard_id in bindings}
    seen_ids = set()
    for item in manifest.files:
        file_path = _path(Path(item.path), workspace)
        if item.guard_id not in bindings or json_content_digest(file_path) != item.content_digest:
            raise ArtifactIntegrityError("Dataset file identity/content digest mismatch")
        for sample in _read_samples(file_path):
            if (
                sample.sample_id in seen_ids
                or sample.labels.guard_id != item.guard_id
                or sample.features.contract_family != bindings[item.guard_id].contract_family
            ):
                raise ArtifactIntegrityError(
                    "Duplicate sample ID or cross-Guard dataset contamination"
                )
            seen_ids.add(sample.sample_id)
            observed[item.guard_id][item.split].add(sample.sample_id)
            source_ref = sample.target.module.replace(".", "/") + ".py"
            if (
                source_ref not in manifest.source_text_digests
                or sample.contract_ref not in manifest.source_text_digests
            ):
                raise ArtifactIntegrityError(
                    "Sample target/contract is missing from the frozen source manifest"
                )
    for guard_id, phase in manifest.phases.items():
        if observed[guard_id]["train"] != set(
            phase.initial + phase.refinement_additions
        ) or observed[guard_id]["holdout"] != set(phase.holdout):
            raise ArtifactIntegrityError("Training/refinement/holdout membership mismatch")
    for ref, expected in manifest.source_text_digests.items():
        if source_text_digest(_path(Path(ref), workspace)) != expected:
            raise ArtifactIntegrityError(f"Frozen target/contract text changed: {ref}")
    return protocol, manifest, guards


def run_train_baselines(
    path: str | Path,
    *,
    cwd: str | Path,
    artifact_root: str | Path = "artifacts",
    split: str = "train",
) -> dict:
    if split != "train":
        raise ValueError("D5 accepts train only; holdout evaluation is reserved for D9")
    workspace = Path(cwd).resolve(strict=True)
    protocol, manifest, guards = verify_protocol(path, cwd=workspace)
    root = _path(Path(artifact_root), workspace)
    samples = sorted(
        [
            sample
            for item in manifest.files
            if item.split == "train"
            for sample in _read_samples(_path(Path(item.path), workspace))
        ],
        key=lambda sample: (sample.labels.guard_id, sample.sample_id),
    )
    scopes = {}
    for method in ("b1_always", "b2_interface"):
        for binding in protocol.guards:
            scope = make_baseline(
                guards[binding.guard_id],
                method,
                interface_kind=binding.frozen_interface_kind,
                protocol_digest=protocol.artifact_digest,
            )
            scope_path = (
                root
                / "scopes/scope-v1"
                / ("b1" if method == "b1_always" else "b2")
                / f"{binding.guard_id}.json"
            )
            if scope_path.exists():
                existing = _load_model(scope_path, ScopePredicate)
                keys = (
                    "scope_id",
                    "guard_id",
                    "guard_digest",
                    "protocol_digest",
                    "strategy",
                    "clauses",
                    "learner_version",
                )
                if any(getattr(existing, key) != getattr(scope, key) for key in keys):
                    raise ArtifactIntegrityError(
                        "Existing baseline scope has different immutable inputs"
                    )
                scope = existing
            else:
                write_immutable(scope_path, canonical_json_bytes(scope))
            scopes[(method, binding.guard_id)] = scope
    predictions, replays = [], []
    counts = {}
    infrastructure_errors = 0
    for method in ("b1_always", "b2_interface"):
        method_rows = []
        for sample in samples:
            guard_id = sample.labels.guard_id
            scope = scopes[(method, guard_id)]
            decision = decide_scope(scope, sample.features.model_dump(mode="json"))
            method_rows.append((sample.labels.guard_applicable, decision.decision))
            row = {
                "method": method,
                "guard_id": guard_id,
                "sample_id": sample.sample_id,
                "scope_id": scope.scope_id,
                "scope_decision": decision.decision,
                "trace": [trace.model_dump(mode="json") for trace in decision.trace],
                "execution_outcome": "not_run",
            }
            if decision.decision == "applicable":
                binding = next(
                    binding for binding in protocol.guards if binding.guard_id == guard_id
                )
                run = run_guard(
                    binding.guard_ref,
                    f"{sample.target.module}:{sample.target.symbol}",
                    cwd=workspace,
                    artifact_root=root,
                )
                row["execution_outcome"] = run.outcome.value
                if run.outcome not in {RunOutcome.PASSED, RunOutcome.TEST_FAILED}:
                    infrastructure_errors += 1
                replays.append(
                    {
                        "method": method,
                        "guard_id": guard_id,
                        "sample_id": sample.sample_id,
                        "run": run.model_dump(mode="json"),
                    }
                )
            predictions.append(row)
        actual = count_predictions(method_rows)
        if actual != protocol.expected_train[method]:
            raise ArtifactIntegrityError(
                "Baseline confusion counts differ from the frozen acceptance"
            )
        counts[method] = actual.model_dump()
    report = {
        "schema_version": "baseline-train-report.v1",
        "protocol_id": protocol.protocol_id,
        "protocol_digest": protocol.artifact_digest,
        "split_digest": manifest.artifact_digest,
        "split": "train",
        "sample_count": len(samples),
        "counts": counts,
        "execution_count": len(replays),
        "infrastructure_errors": infrastructure_errors,
        "predictions": predictions,
    }
    output = root / "experiments/scope-v1/train-baselines"
    output.mkdir(parents=True, exist_ok=True)
    (output / "predictions.jsonl").write_bytes(
        b"".join(canonical_json_bytes(row) + b"\n" for row in predictions)
    )
    (output / "replays.jsonl").write_bytes(
        b"".join(canonical_json_bytes(row) + b"\n" for row in replays)
    )
    (output / "report.json").write_bytes(canonical_json_bytes(report))
    return report


def _read_samples(path: Path) -> list[BenchmarkSample]:
    return TypeAdapter(list[BenchmarkSample]).validate_json(path.read_bytes())


def _path(path: Path, workspace: Path) -> Path:
    resolved = (path if path.is_absolute() else workspace / path).resolve()
    if not resolved.is_relative_to(workspace):
        raise ValueError("Protocol path must stay within the workspace")
    return resolved


def _load_model(path: Path, model):
    try:
        value = model.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as error:
        raise ArtifactIntegrityError(f"Invalid {model.__name__}: {path}") from error
    if digest_json_artifact(value) != value.artifact_digest:
        raise ArtifactIntegrityError(f"{model.__name__} artifact digest mismatch")
    return value
