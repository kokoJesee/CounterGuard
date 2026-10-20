"""Committed comparison targets have no invented B/F/H and no execution capability."""

import json
from pathlib import Path

from pydantic import TypeAdapter

from counterguard.artifacts import write_immutable
from counterguard.bootstrap_binding import _new_output, assess_runtime_source
from counterguard.bootstrap_plan import describe_bootstrap_files
from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.project_config import Module, Symbol
from counterguard.repository import read_committed_files


def inspect_static_target(
    repo: Path,
    revision: str,
    *,
    target: str,
    import_root: str,
    profile: str,
    output: Path,
    cwd: Path | None = None,
) -> dict:
    """Review one full committed tree, without test extraction, checkout or import."""
    if profile != "static-reexport-v2":
        raise ValueError("Target inspection requires explicit profile static-reexport-v2")
    if target.count(":") != 1 or import_root not in {".", "src"}:
        raise ValueError("Select module:symbol and .|src import root")
    module, symbol = target.split(":")
    TypeAdapter(Module).validate_python(module)
    TypeAdapter(Symbol).validate_python(symbol)
    output = _new_output(repo, output, cwd)
    commit, files, pins = read_committed_files(repo, revision)
    prefix = "" if import_root == "." else "src/"
    assessment = assess_runtime_source(
        files,
        module=module,
        symbol=symbol,
        source_ref=prefix + module + "/__init__.py",
        import_root=import_root,
        closure_algorithm="module-import-closure.v2",
        export_algorithm="static-root-reexport.v2",
    )
    value = {
        "schema_version": "static-target-inspection.v1",
        "profile": "standalone-static-reexport.v2",
        "requested_revision": revision,
        "commit": commit,
        "target": target,
        "import_root": import_root,
        "files": [pin.model_dump(mode="json") for pin in sorted(pins, key=lambda x: x.path)],
        "runtime_assessment": assessment,
        "bootstrap_observations": describe_bootstrap_files(
            files, {item["path"] for item in assessment["files"]}
        ),
        "human_review_required": True,
        "execution_allowed": False,
        "execution_outcome": "not_run",
        "cross_repository_execution_supported": False,
        "next_action": "Review every pinned initializer, class/metaclass and environment/native "
        "branch. This inspection has no B/F/H, contract, labels or execution authority. "
        "A separately versioned research mapping and authorization bridge is required before "
        "cross-repository execution; do not reuse production snapshot Scope to switch targets.",
        "implementation_digests": inspection_implementation_digests(),
    }
    value["artifact_digest"] = digest_json_artifact(value)
    raw = canonical_json_bytes(value)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("Target inspection byte budget exceeded")
    write_immutable(output / "target.json", raw)
    return json.loads(raw)
