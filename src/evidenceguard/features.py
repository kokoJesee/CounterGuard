"""Extract static target features and audit them against the frozen manual annotations."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from evidenceguard.artifacts import write_immutable
from evidenceguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError, FeatureExtractionError
from evidenceguard.evidence import parse_target_ref
from evidenceguard.models import ArtifactRef, Digest, FrozenModel, TargetRef
from evidenceguard.predicates import (
    EXTRACTOR_VERSION,
    METADATA_FIELDS,
    VOCABULARY_DIGEST,
    FeatureVector,
)


@dataclass(frozen=True, slots=True)
class FeatureContext:
    target: str
    contract_path: Path
    module_group: str
    cwd: Path


class FeatureRecord(FrozenModel):
    schema_version: Literal["feature-extraction.v1"] = "feature-extraction.v1"
    extractor_version: Literal["ast-features.v1"] = EXTRACTOR_VERSION
    vocabulary_digest: Digest
    target: TargetRef
    target_digest: Digest
    contract_ref: ArtifactRef
    contract_digest: Digest
    features: FeatureVector
    artifact_digest: Digest


def extract_features(context: FeatureContext) -> FeatureVector:
    """Return only features; source, identity, labels, and provenance are kept outside."""
    return extract_feature_record(context).features


def extract_feature_record(context: FeatureContext) -> FeatureRecord:
    try:
        workspace = context.cwd.resolve(strict=True)
        target, target_digest = parse_target_ref(context.target, cwd=workspace)
        contract_path = _path(context.contract_path, workspace)
        contract_bytes = contract_path.read_bytes()
        contract = json.loads(contract_bytes)
        if not isinstance(contract, dict) or contract.get("target_symbol") != target.symbol:
            raise ValueError("Contract target_symbol must match the selected target")
        metadata = {field: contract[field] for field in METADATA_FIELDS}
        source = (workspace / target.source_ref).read_bytes()
        if digest_bytes(source) != target_digest:
            raise ValueError("Target source changed during extraction")
        tokens = extract_ast_features(source, target.symbol)
        features = FeatureVector(**metadata, module_group=context.module_group, ast_features=tokens)
        draft = FeatureRecord(
            vocabulary_digest=VOCABULARY_DIGEST,
            target=target,
            target_digest=target_digest,
            contract_ref=contract_path.relative_to(workspace).as_posix(),
            contract_digest=digest_bytes(contract_bytes),
            features=features,
            artifact_digest="sha256:" + "0" * 64,
        )
        return FeatureRecord.model_validate_json(
            canonical_json_bytes(
                {
                    **draft.model_dump(mode="json"),
                    "artifact_digest": digest_json_artifact(draft),
                }
            )
        )
    except (OSError, ValueError, KeyError) as error:
        raise FeatureExtractionError(f"Cannot extract {context.target}: {error}") from error


def extract_ast_features(source: str | bytes, symbol: str) -> frozenset[str]:
    """Parse without importing or executing source. Empty sets are valid for plain code."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, UnicodeError) as error:
        raise FeatureExtractionError(f"Invalid Python source: {error}") from error
    definitions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol
    ]
    if "." in symbol or len(definitions) != 1:
        raise FeatureExtractionError("Target must resolve to one top-level function definition")
    function = definitions[0]
    if isinstance(function, ast.AsyncFunctionDef) or function.decorator_list:
        raise FeatureExtractionError(
            "Async or decorated targets are unsupported in ast-features.v1"
        )
    nodes = [node for statement in function.body for node in ast.walk(statement)]
    unsupported = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
        ast.Yield,
        ast.YieldFrom,
        ast.Await,
        ast.Match,
        ast.Try,
        ast.TryStar,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.With,
        ast.AsyncWith,
        ast.Import,
        ast.ImportFrom,
        ast.Global,
        ast.Nonlocal,
    )
    if any(isinstance(node, unsupported) for node in nodes):
        raise FeatureExtractionError("Unsupported control flow or nested scope in ast-features.v1")
    arguments = function.args
    parameter_names = [
        arg.arg for arg in arguments.posonlyargs + arguments.args + arguments.kwonlyargs
    ]
    parameter_names.extend(
        arg.arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None
    )
    if len(parameter_names) != len(set(parameter_names)):
        raise FeatureExtractionError("Duplicate formal parameter names")
    parameters = set(parameter_names)
    local_names = parameters | {
        node.id for node in nodes if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    bindings, module_names = _module_bindings(tree)
    tokens = set()
    for node in nodes:
        if isinstance(node, (ast.If, ast.IfExp)):
            test_nodes = tuple(ast.walk(node.test))
            if "is_member" in parameters and any(
                isinstance(part, ast.Name) and part.id == "is_member" for part in test_nodes
            ):
                tokens.add("branch:is_member")
            if any(_parameter_none_comparison(part, parameters) for part in test_nodes):
                tokens.add("branch:none")
            if _complete_range(node.test):
                tokens.add("range:check")
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Mult):
                tokens.add("decimal:multiply")
            elif isinstance(node.op, ast.Sub):
                tokens.add("decimal:subtract")
        if isinstance(node, ast.Call):
            if _resolved_name(node.func, bindings, local_names) == "builtins.int" or (
                isinstance(node.func, ast.Name)
                and node.func.id == "int"
                and "int" not in local_names | module_names
            ):
                tokens.add("int:parse")
            if _resolved_name(node.func, bindings, local_names) == "re.fullmatch":
                pattern = (
                    node.args[0]
                    if node.args
                    else next((kw.value for kw in node.keywords if kw.arg == "pattern"), None)
                )
                if isinstance(pattern, ast.Constant) and pattern.value in ("[0-9]", "[0-9]+"):
                    tokens.add("regex:ascii_digits")
            if isinstance(node.func, ast.Attribute) and node.func.attr in ("isascii", "isdecimal"):
                tokens.add(f"str:{node.func.attr}")
        if (
            isinstance(node, (ast.Name, ast.Attribute))
            and isinstance(node.ctx, ast.Load)
            and _resolved_name(node, bindings, local_names) == "decimal.ROUND_HALF_UP"
        ):
            tokens.add("round:half_up")
    return frozenset(tokens)


def _module_bindings(tree: ast.Module) -> tuple[dict[str, str], set[str]]:
    bindings, names = {}, set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                names.add(name)
                bindings[name] = alias.name if alias.asname else alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                names.add(name)
                bindings[name] = f"{node.module}.{alias.name}" if not node.level else ""
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            bindings.pop(node.name, None)
        else:
            for part in ast.walk(node):
                if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Store):
                    names.add(part.id)
                    bindings.pop(part.id, None)
    return bindings, names


def _resolved_name(node, bindings, local_names) -> str | None:
    if isinstance(node, ast.Name) and node.id not in local_names:
        return bindings.get(node.id)
    if isinstance(node, ast.Attribute):
        parent = _resolved_name(node.value, bindings, local_names)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _parameter_none_comparison(node, parameters: set[str]) -> bool:
    if not isinstance(node, ast.Compare):
        return False
    values = (node.left, *node.comparators)
    for left, op, right in zip(values, node.ops, values[1:], strict=False):
        if not isinstance(op, (ast.Is, ast.IsNot)):
            continue
        for candidate, other in ((left, right), (right, left)):
            if (
                isinstance(candidate, ast.Name)
                and candidate.id in parameters
                and (isinstance(other, ast.Constant) and other.value is None)
            ):
                return True
    return False


def _complete_range(test: ast.expr) -> bool:
    bounds: dict[str, set[str]] = {}
    for node in ast.walk(test):
        if not isinstance(node, ast.Compare):
            continue
        values = (node.left, *node.comparators)
        for left, op, right in zip(values, node.ops, values[1:], strict=False):
            if not isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                continue
            for value, bound, reversed_order in ((left, right, False), (right, left, True)):
                numeric = isinstance(bound, ast.Constant) and type(bound.value) in (int, float)
                numeric |= (
                    isinstance(bound, ast.UnaryOp)
                    and isinstance(bound.op, (ast.USub, ast.UAdd))
                    and (
                        isinstance(bound.operand, ast.Constant)
                        and type(bound.operand.value) in (int, float)
                    )
                )
                if not numeric or not isinstance(value, (ast.Name, ast.Attribute, ast.Subscript)):
                    continue
                lower = isinstance(op, (ast.Gt, ast.GtE)) != reversed_order
                bounds.setdefault(ast.dump(value), set()).add("lower" if lower else "upper")
    return any(kinds == {"lower", "upper"} for kinds in bounds.values())


def audit_features(
    *,
    benchmark_root: str | Path,
    output: str | Path,
    cwd: str | Path,
    artifact_root: str | Path = "artifacts",
) -> dict:
    workspace = Path(cwd).resolve(strict=True)
    root = _path(Path(benchmark_root), workspace)
    destination = _path(Path(output), workspace)
    artifact_path = _path(Path(artifact_root), workspace) / "features" / EXTRACTOR_VERSION
    files = sorted(
        path
        for split in ("train", "holdout")
        for path in (root / split).glob("*_scope_samples.json")
    )
    entries, inputs, seen = [], {}, set()
    if not files:
        entries.append(
            {
                "sample_id": None,
                "status": "error",
                "exit_code": 2,
                "error": "No benchmark sample files found",
            }
        )
    for path in files:
        try:
            data = json.loads(path.read_bytes())
            if not isinstance(data, list) or not data:
                raise ValueError("Benchmark file must contain a nonempty list")
            inputs[path.relative_to(workspace).as_posix()] = digest_bytes(
                canonical_json_bytes(data)
            )
        except (OSError, ValueError) as error:
            entries.append(
                {
                    "sample_id": None,
                    "status": "error",
                    "exit_code": 2,
                    "error": str(error),
                    "file": path.relative_to(workspace).as_posix(),
                }
            )
            continue
        for sample in data:
            sample_id = sample.get("sample_id") if isinstance(sample, dict) else None
            row = {"sample_id": sample_id, "status": "error", "exit_code": 2}
            try:
                if (
                    not isinstance(sample_id, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]+", sample_id)
                    or sample_id in seen
                ):
                    raise ValueError("Sample IDs must be unique, safe, nonempty strings")
                seen.add(sample_id)
                expected = FeatureVector.model_validate_json(json.dumps(sample["features"]))
                # Only the explicit module group comes from annotation metadata. The
                # extractor never receives manual AST tokens or applicability labels.
                context = FeatureContext(
                    target=f"{sample['target']['module']}:{sample['target']['symbol']}",
                    contract_path=Path(sample["contract_ref"]),
                    module_group=expected.module_group,
                    cwd=workspace,
                )
                record = extract_feature_record(context)
                actual = record.features
                missing = sorted(expected.ast_features - actual.ast_features)
                unexpected = sorted(actual.ast_features - expected.ast_features)
                metadata_diff = {
                    field: {"expected": getattr(expected, field), "actual": getattr(actual, field)}
                    for field in METADATA_FIELDS
                    if getattr(expected, field) != getattr(actual, field)
                }
                matched = not missing and not unexpected and not metadata_diff
                ref = artifact_path / f"{sample_id}.json"
                write_immutable(ref, canonical_json_bytes(record))
                row.update(
                    status="matched" if matched else "mismatched",
                    exit_code=0 if matched else 1,
                    missing=missing,
                    unexpected=unexpected,
                    metadata_diff=metadata_diff,
                    expected=expected.model_dump(mode="json"),
                    actual=actual.model_dump(mode="json"),
                    feature_ref=ref.relative_to(workspace).as_posix(),
                    feature_digest=record.artifact_digest,
                )
            except FeatureExtractionError as error:
                row.update(exit_code=3, error=str(error))
            except ArtifactIntegrityError as error:
                row.update(exit_code=5, error=str(error))
            except (KeyError, TypeError, ValueError, OSError) as error:
                row.update(exit_code=2, error=str(error))
            entries.append(row)
    report = {
        "schema_version": "feature-audit.v1",
        "extractor_version": EXTRACTOR_VERSION,
        "vocabulary_digest": VOCABULARY_DIGEST,
        "dataset_digests": inputs,
        "sample_count": sum(row["sample_id"] is not None for row in entries),
        "matched": sum(row["status"] == "matched" for row in entries),
        "mismatched": sum(row["status"] == "mismatched" for row in entries),
        "errors": sum(row["status"] == "error" for row in entries),
        "entries": entries,
    }
    report["artifact_digest"] = digest_json_artifact(report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical_json_bytes(report))
    return report


def _path(path: Path, workspace: Path) -> Path:
    resolved = (path if path.is_absolute() else workspace / path).resolve()
    if not resolved.is_relative_to(workspace):
        raise ValueError("Feature input/output paths must stay within the workspace")
    return resolved
