"""Architectural context is pinned and never inferred from benchmark labels."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.module_context import SCOPE_V1_CONTEXT_DIGEST, ModuleContext, load_module_context

ROOT = Path(__file__).resolve().parents[2]


def test_current_context_is_independently_pinned_and_maps_packages():
    context = load_module_context(ROOT / "benchmarks/context/scope_v1.json")
    assert context.artifact_digest == SCOPE_V1_CONTEXT_DIGEST
    assert (
        context.resolve_group("examples.discount.implementations.final_price_v2_correct")
        == "retail"
    )
    assert (
        context.resolve_group("examples.validation.implementations.query_limit_v1_buggy")
        == "shared_validation"
    )
    with pytest.raises(ValueError, match="exactly one"):
        context.resolve_group("examples.discounted.other")


def test_rehashed_context_change_cannot_silently_change_frozen_features(tmp_path):
    payload = json.loads((ROOT / "benchmarks/context/scope_v1.json").read_bytes())
    payload["rules"][0]["module_group"] = "buggy_group"
    payload["artifact_digest"] = digest_json_artifact(payload)
    path = tmp_path / "context.json"
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="Frozen scope_v1"):
        load_module_context(path)


def test_overlapping_rules_or_label_fields_are_rejected():
    payload = json.loads((ROOT / "benchmarks/context/scope_v1.json").read_bytes())
    payload["rules"].append(
        {**payload["rules"][0], "module_prefix": "examples.discount.implementations"}
    )
    with pytest.raises(ValidationError, match="Overlapping"):
        ModuleContext.model_validate_json(json.dumps(payload))
    payload["rules"] = [{**payload["rules"][0], "guard_applicable": True}]
    with pytest.raises(ValidationError):
        ModuleContext.model_validate_json(json.dumps(payload))
