"""External authority cannot be supplied through old fixture inputs or a toggle."""

from dataclasses import fields

import pytest
from pydantic import TypeAdapter, ValidationError

from counterguard.errors import ArtifactIntegrityError
from counterguard.external_snapshot import ExternalSnapshotSession
from counterguard.external_snapshot_comparison import ExternalSnapshotComparisonSession
from counterguard.external_snapshot_models import (
    ExternalComparisonAdmission,
    ExternalComparisonAuthorization,
    ExternalComparisonPlan,
    ExternalComparisonReplay,
    ExternalComparisonReview,
    ExternalSnapshotAuthorization,
    ExternalSnapshotEvidence,
    ExternalSnapshotGuard,
    ExternalSnapshotMap,
    ExternalSnapshotReview,
    ExternalSnapshotTarget,
    ExternalSnapshotWitness,
    RepositoryUrl,
)
from counterguard.snapshot_admission import seal
from counterguard.snapshot_comparison import _decide_comparison
from counterguard.snapshot_comparison_models import (
    SnapshotComparisonAdmission,
    SnapshotComparisonAuthorization,
    SnapshotComparisonMap,
    SnapshotComparisonPlan,
    SnapshotComparisonReplay,
    SnapshotComparisonReview,
    SnapshotComparisonTarget,
    SnapshotOwnWitness,
)
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_models import (
    ZERO,
    SnapshotAuthorization,
    SnapshotEvidence,
    SnapshotGuard,
    SnapshotReview,
)
from tests.unit.test_snapshot_comparison import facts, plan, review

PAIRS = (
    (SnapshotReview, ExternalSnapshotReview),
    (SnapshotAuthorization, ExternalSnapshotAuthorization),
    (SnapshotEvidence, ExternalSnapshotEvidence),
    (SnapshotGuard, ExternalSnapshotGuard),
    (SnapshotComparisonTarget, ExternalSnapshotTarget),
    (SnapshotComparisonMap, ExternalSnapshotMap),
    (SnapshotOwnWitness, ExternalSnapshotWitness),
    (SnapshotComparisonReview, ExternalComparisonReview),
    (SnapshotComparisonPlan, ExternalComparisonPlan),
    (SnapshotComparisonAdmission, ExternalComparisonAdmission),
    (SnapshotComparisonAuthorization, ExternalComparisonAuthorization),
    (SnapshotComparisonReplay, ExternalComparisonReplay),
)


def external_plan(**update):
    data = plan().model_dump(exclude={"schema_version", "purpose"})
    return seal(ExternalComparisonPlan(**(data | update)))


@pytest.mark.parametrize("old,new", PAIRS)
def test_external_namespace_is_disjoint_and_old_schemas_are_not_widened(old, new):
    assert not issubclass(new, old)
    for model, other in ((old, new), (new, old)):
        with pytest.raises(ValidationError):
            model.model_validate(other.model_construct())
    old_version = old.model_fields["schema_version"]
    new_version = new.model_fields["schema_version"]
    assert old_version.default != new_version.default
    for target, other in ((old_version, new_version), (new_version, old_version)):
        with pytest.raises(ValidationError):
            TypeAdapter(target.annotation).validate_python(other.default)
    if "purpose" in old.model_fields and "purpose" in new.model_fields:
        old_purpose = old.model_fields["purpose"].annotation
        new_purpose = new.model_fields["purpose"].annotation
        assert not set(old_purpose.__args__) & set(new_purpose.__args__)


@pytest.mark.parametrize("method", ["b2_interface", "learned_initial", "learned_refined"])
def test_external_observation_does_not_mint_four_method_research_predictions(method):
    with pytest.raises(ValidationError):
        external_plan(method=method)


def test_plan_parsers_reject_opposite_purpose_in_both_directions():
    with pytest.raises(ValidationError):
        SnapshotComparisonPlan.model_validate_json(external_plan().model_dump_json())
    with pytest.raises(ValidationError):
        ExternalComparisonPlan.model_validate_json(plan().model_dump_json())
    with pytest.raises(ValidationError):
        SnapshotComparisonPlan.model_validate(external_plan())
    with pytest.raises(ValidationError):
        ExternalComparisonPlan.model_validate(plan())


def test_external_witness_keeps_shared_constraints_after_ancestry_is_separated():
    values = facts().witness.model_dump(exclude={"schema_version"})
    ExternalSnapshotWitness(**values)
    for changes in ({"basis_refs": ("z", "a")}, {"cases": ()}):
        with pytest.raises(ValidationError):
            ExternalSnapshotWitness(**(values | changes))


def test_no_public_constructor_toggle_and_no_external_exact_source_replay(tmp_path, monkeypatch):
    assert [f.name for f in fields(SnapshotSession)] == [
        "repo",
        "workspace",
        "binding_path",
        "review_path",
        "trusted_digest",
    ]
    engine = ExternalSnapshotSession(
        tmp_path / "repo", tmp_path, tmp_path / "binding", tmp_path / "review", ZERO
    )
    monkeypatch.setattr(
        ExternalSnapshotSession, "context", lambda *a: pytest.fail("must reject before loading")
    )
    for operation in (engine.replay, engine.verify_replay):
        with pytest.raises(ArtifactIntegrityError, match="independent_comparison_review"):
            operation()
    assert "fixture_capture" not in engine._PURPOSES
    with pytest.raises(ArtifactIntegrityError, match="source_type_required"):
        ExternalSnapshotComparisonSession(
            SnapshotSession(tmp_path / "repo", tmp_path, tmp_path / "b", tmp_path / "r", ZERO),
            tmp_path / "target",
            ZERO,
        )


@pytest.mark.parametrize("lane", ["guard", "own_contract"])
def test_withdrawn_external_review_writes_null_run_without_any_docker_or_test(
    tmp_path, monkeypatch, lane
):
    from counterguard import snapshot_comparison as module

    p = external_plan(lane=lane)
    f, r = facts(), review(action="withdraw")
    admission = _decide_comparison(p, f, r, ExternalComparisonAdmission)
    source = ExternalSnapshotSession(
        tmp_path / "repo", tmp_path, tmp_path / "binding", tmp_path / "review", ZERO
    )
    engine = ExternalSnapshotComparisonSession(source, tmp_path / "target", ZERO)
    monkeypatch.setattr(ExternalSnapshotComparisonSession, "_load", lambda *a: (admission, f, r))
    monkeypatch.setattr(module, "_docker_executable", lambda: pytest.fail("Docker discovery"))
    monkeypatch.setattr(module, "render_comparison_test", lambda *a: pytest.fail("render"))
    result = engine.run(p, output="unknown")
    assert type(result) is ExternalComparisonReplay
    assert (
        result.run is result.workspace_ref is result.record_ref is result.authorization_ref is None
    )
    assert result.outcome == "skipped_unknown" and result.admission.decision == "unknown"
    assert not (tmp_path / "unknown/runtime").exists()
    assert engine.verify(tmp_path / "unknown/replay.json") == result


@pytest.mark.parametrize(
    "url",
    [
        "https://user:token@github.com/a/b",
        "http://github.com/a/b",
        "https://github.com/a/b?token=x",
        "https://other.invalid/a/b",
        "file:///repo",
    ],
)
def test_repository_declarations_do_not_accept_credentials_or_arbitrary_hosts(url):
    with pytest.raises(ValidationError):
        TypeAdapter(RepositoryUrl).validate_python(url)
