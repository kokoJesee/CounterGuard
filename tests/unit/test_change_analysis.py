"""File impact remains distinct from Scope applicability and execution eligibility."""

import json

import pytest

from counterguard.change_analysis import InspectionReport, TargetImpact, analyze_changes
from counterguard.project_config import ProjectConfig
from counterguard.repository import FileChange, FilePin, RepositorySnapshot
from tests.unit.test_project_config import project


def snapshot(*changed, missing=(), status="ready", reasons=()):
    return RepositorySnapshot(
        status=status,
        reason_codes=reasons,
        changes=tuple(
            FileChange(path=p, kind="M", old_mode="100644", new_mode="100644") for p in changed
        ),
        files=tuple(
            FilePin(
                revision="head", path=p, object_id="a" * 40, content_digest="sha256:" + "0" * 64
            )
            for p in ("src/pricing.py", "contracts/price.json")
            if p not in missing
        ),
    )


def test_source_and_contract_changes_are_declared_candidates():
    config = ProjectConfig.model_validate_json(json.dumps(project()))
    for path in ("src/pricing.py", "contracts/price.json"):
        targets, unmapped = analyze_changes(config, snapshot(path))
        assert targets[0].impact == "affected" and not unmapped
        assert targets[0].execution_allowed is False
        assert targets[0].changed_inputs == (path,)


def test_unmapped_change_propagates_unknown_instead_of_selecting_all():
    config = ProjectConfig.model_validate_json(json.dumps(project()))
    targets, unmapped = analyze_changes(config, snapshot("src/pricing.py", "src/unknown.py"))
    assert unmapped == ("src/unknown.py",)
    assert targets[0].impact == "unknown"
    assert "unmapped_changed_paths" in targets[0].reason_codes


def test_deleted_or_missing_declared_input_is_unknown():
    config = ProjectConfig.model_validate_json(json.dumps(project()))
    targets, _ = analyze_changes(config, snapshot("src/pricing.py", missing=("src/pricing.py",)))
    assert targets[0].impact == "unknown"
    assert "missing_declared_head_input" in targets[0].reason_codes


def test_ignored_documentation_is_explicit_and_unaffected_does_not_mean_inapplicable():
    config = ProjectConfig.model_validate_json(json.dumps(project(ignored_paths=["README.md"])))
    targets, unmapped = analyze_changes(config, snapshot("README.md"))
    assert not unmapped and targets[0].impact == "unaffected"
    assert targets[0].execution_allowed is False


def test_explicit_ci_control_change_does_not_hide_a_mapped_source_change():
    config = ProjectConfig.model_validate_json(
        json.dumps(project(ignored_paths=[".github/workflows/ci.yml"]))
    )
    targets, unmapped = analyze_changes(
        config, snapshot("src/pricing.py", ".github/workflows/ci.yml")
    )
    assert not unmapped
    assert targets[0].impact == "affected"
    assert targets[0].changed_inputs == ("src/pricing.py",)
    assert targets[0].execution_allowed is False


def test_inspection_execution_flag_is_structurally_false():
    impact_schema = TargetImpact.model_json_schema()["properties"]["execution_allowed"]
    report_schema = InspectionReport.model_json_schema()["properties"]["execution_allowed"]
    assert impact_schema["const"] is False and report_schema["const"] is False
    with pytest.raises(ValueError):
        TargetImpact(
            target_id="pricing",
            guard_id="grd_price",
            source_ref="src/pricing.py",
            symbol="price",
            impact="affected",
            changed_inputs=("src/pricing.py",),
            execution_allowed=True,
        )


def test_repository_uncertainty_is_not_a_negative_scope_label():
    config = ProjectConfig.model_validate_json(json.dumps(project()))
    targets, _ = analyze_changes(
        config, snapshot(status="unknown", reasons=("missing_base_commit",))
    )
    assert targets[0].impact == "unknown"
    assert targets[0].reason_codes == ("missing_base_commit",)
