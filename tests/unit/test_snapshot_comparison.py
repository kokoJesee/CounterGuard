"""Pure mapping/oracle/decision boundaries; no real Git, Docker or candidate imports."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.snapshot_admission import seal
from counterguard.snapshot_comparison import (
    SnapshotComparisonSession,
    decide_comparison,
    render_comparison_test,
)
from counterguard.snapshot_comparison_data import (
    create_comparison_map,
    validate_comparison_map,
    validate_own_witness,
)
from counterguard.snapshot_comparison_models import (
    SnapshotComparisonPlan,
    SnapshotOwnWitness,
    SnapshotTargetEntry,
)
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_models import ZERO, SnapshotReview
from counterguard.snapshot_projection import project_snapshot_test
from counterguard.study_models import StudyTarget


def projected():
    raw = (
        b"import pytest\nfrom sample.core import check\n"
        b"@pytest.mark.parametrize('value', [pytest.param(-1,id='low'),"
        b"pytest.param(256,id='high')])\ndef test_invalid(value):\n"
        b" with pytest.raises(ValueError, match='outside range'): check(value)\n"
    )
    return project_snapshot_test(
        raw, test_function="test_invalid", target_module="sample.core", target_symbol="check"
    )["cases"]


def plan(**update):
    values = dict(
        evidence_ref="capture/evidence.json",
        guard_ref="guard/guard.json",
        target_ref="target.json",
        map_ref="map.json",
        review_ref="comparison-review.json",
        witness_ref="witness.json",
        method="b1_always",
        artifact_digest=ZERO,
    )
    return seal(SnapshotComparisonPlan(**(values | update)))


def facts():
    cases = projected()
    contract = SimpleNamespace(cases=cases)
    guard = SimpleNamespace(
        case_ids=tuple(c.case_id for c in cases), artifact_digest="sha256:" + "1" * 64
    )
    target = SimpleNamespace(
        artifact_digest="sha256:" + "2" * 64,
        interface_kind="value_return",
        entry=SnapshotTargetEntry(
            target_module="other.core",
            target_symbol="normalize",
            source_ref="src/other/core.py",
            import_root="src",
        ),
        package_refs=("src/other/core.py",),
    )
    mapping = create_comparison_map(guard, contract, target)
    witness = seal(
        SnapshotOwnWitness(
            target_digest=target.artifact_digest,
            map_digest=mapping.artifact_digest,
            basis_refs=("README.md",),
            cases=tuple(c.model_copy(update={"exception_match": "own API rejects"}) for c in cases),
            artifact_digest=ZERO,
        )
    )
    return SimpleNamespace(
        guard=guard,
        contract=contract,
        target=target,
        mapping=mapping,
        witness=witness,
        cases=cases,
        target_files={"src/other/core.py": b"# never imported\n", "README.md": b"own policy"},
        source_contract=b"original H contract",
    )


def review(**update):
    return SimpleNamespace(
        **(
            dict(
                action="approve",
                source_interface="value_return",
                artifact_digest="sha256:" + "3" * 64,
            )
            | update
        )
    )


def test_identity_map_and_witness_preserve_full_inputs_and_do_not_replace_source_oracle():
    f = facts()
    assert validate_comparison_map(f.guard, f.contract, f.target, f.mapping) == f.cases
    validate_own_witness(f.witness, f.target, f.mapping, f.cases, f.target_files)
    assert b"outside range" in render_comparison_test(f, "guard")
    assert b"own API rejects" not in render_comparison_test(f, "guard")
    assert b"own API rejects" in render_comparison_test(f, "own_contract")
    assert b"MODULE = 'other.core'" in render_comparison_test(f, "guard")
    for _ in range(20):
        assert create_comparison_map(f.guard, f.contract, f.target) == f.mapping
        assert decide_comparison(plan(), f, review()) == decide_comparison(plan(), f, review())


@pytest.mark.parametrize(
    "field",
    [
        "case_id",
        "assertion_digest",
        "source_line",
        "assertion_index",
        "parameter_index",
        "positional_args",
        "keyword_args",
    ],
)
def test_independent_oracle_cannot_change_input_or_identity(field):
    f = facts()
    case = f.witness.cases[0]
    replacement = {
        "case_id": f.witness.cases[1].case_id,
        "assertion_digest": ZERO,
        "source_line": 999,
        "assertion_index": 99,
        "parameter_index": 99,
        "positional_args": (),
        "keyword_args": (SimpleNamespace(name="extra"),),
    }[field]
    altered = f.witness.model_copy(
        update={"cases": (case.model_copy(update={field: replacement}), *f.witness.cases[1:])}
    )
    with pytest.raises(ArtifactIntegrityError):
        validate_own_witness(altered, f.target, f.mapping, f.cases, f.target_files)


@pytest.mark.parametrize("kind", ["dropped", "reordered", "case_digest", "target", "guard"])
def test_resigned_identity_mapping_forgery_is_not_accepted(kind):
    f = facts()
    changes = {
        "dropped": {"cases": f.mapping.cases[:1]},
        "reordered": {"cases": tuple(reversed(f.mapping.cases))},
        "case_digest": {
            "cases": (
                f.mapping.cases[0].model_copy(update={"source_case_digest": ZERO}),
                *f.mapping.cases[1:],
            )
        },
        "target": {"target_digest": ZERO},
        "guard": {"guard_digest": ZERO},
    }[kind]
    altered = seal(f.mapping.model_copy(update=changes))
    with pytest.raises(ArtifactIntegrityError):
        validate_comparison_map(f.guard, f.contract, f.target, altered)


@pytest.mark.parametrize(
    "method,interface,action,lane,expected",
    [
        ("b1_always", "stdout_write", "approve", "guard", "applicable"),
        ("b2_interface", "value_return", "approve", "guard", "applicable"),
        ("b2_interface", "stdout_write", "approve", "guard", "inapplicable"),
        ("learned_initial", "value_return", "approve", "guard", "unknown"),
        ("learned_refined", "value_return", "approve", "guard", "unknown"),
        ("b1_always", "value_return", "withdraw", "guard", "unknown"),
        ("b2_interface", "value_return", "approve", "own_contract", "unknown"),
    ],
)
def test_methods_and_withdrawal_do_not_grant_implicit_permission(
    method, interface, action, lane, expected
):
    f = facts()
    f.target.interface_kind = interface
    assert (
        decide_comparison(plan(method=method, lane=lane), f, review(action=action)).decision
        == expected
    )


@pytest.mark.parametrize(
    "method,lane,missing_witness",
    [
        ("learned_initial", "guard", False),
        ("learned_refined", "guard", False),
        ("b2_interface", "guard", False),
        ("b1_always", "own_contract", True),
    ],
)
def test_skip_writes_null_run_without_docker_discovery_or_rendering(
    tmp_path, monkeypatch, method, lane, missing_witness
):
    from counterguard import snapshot_comparison as module

    f = facts()
    f.target.interface_kind = "stdout_write"
    if missing_witness:
        f.witness = None
    p = plan(method=method, lane=lane, witness_ref=None if missing_witness else "witness.json")
    r = review()
    admission = decide_comparison(p, f, r)
    source = SnapshotSession(
        tmp_path / "repo", tmp_path, tmp_path / "binding.json", tmp_path / "review.json", ZERO
    )
    engine = SnapshotComparisonSession(source, tmp_path / "target", ZERO)
    monkeypatch.setattr(SnapshotComparisonSession, "_load", lambda self, value: (admission, f, r))
    monkeypatch.setattr(
        module, "_docker_executable", lambda: pytest.fail("Docker discovery is forbidden")
    )
    monkeypatch.setattr(
        module,
        "render_comparison_test",
        lambda *a: pytest.fail("skip must not render an executable test"),
    )
    result = engine.run(p, output="skip")
    assert (
        result.run is result.workspace_ref is result.authorization_ref is result.record_ref is None
    )
    assert result.outcome == "skipped_" + admission.decision
    assert not (tmp_path / "skip/runtime").exists()
    assert engine.verify(tmp_path / "skip/replay.json") == result


def test_plan_types_and_cli_namespace_do_not_widen_old_parsers():
    p = json.loads(canonical_json_bytes(plan()))
    for change in [
        {"purpose": "external_observation"},
        {"fit_ref": "invented"},
        {"method": "always_bypass"},
    ]:
        with pytest.raises(ValidationError):
            SnapshotComparisonPlan.model_validate_json(json.dumps(p | change))
    with pytest.raises(ValidationError):
        SnapshotReview.model_validate_json(canonical_json_bytes(plan()))
    with pytest.raises(ValidationError):
        StudyTarget.model_validate_json(canonical_json_bytes(plan()))
    result = CliRunner().invoke(app, ["research-snapshot", "comparison", "--help"])
    assert result.exit_code == 0 and "fixture" in result.output.lower()
    assert "inspect-target" in result.output and "verify" in result.output


def test_invalid_or_reserved_target_refuses_before_git(monkeypatch, tmp_path):
    from counterguard import snapshot_comparison_data as module

    monkeypatch.setattr(
        module, "read_snapshot", lambda *a, **k: pytest.fail("invalid target reached Git")
    )
    for target in ["CG_CONTROL", "pytest", "SiteCustomize"]:
        with pytest.raises(ArtifactIntegrityError):
            module.inspect_snapshot_target(
                tmp_path,
                "a" * 40,
                target_id="x",
                entry=SnapshotTargetEntry(
                    target_module=target,
                    target_symbol="check",
                    source_ref=f"src/{target}/__init__.py",
                    import_root="src",
                ),
                license_ref="LICENSE",
                interface_kind="value_return",
                interface_basis_ref="README.md",
            )
