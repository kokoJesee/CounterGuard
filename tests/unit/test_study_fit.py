"""Fast training-only provenance with source/Git doubles; never execute targets."""

import json
import random
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

import counterguard.study_fit as fit_module
from counterguard.digests import canonical_json_bytes, digest_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import FrozenModel
from counterguard.standalone_capture import ZERO, _seal
from counterguard.study_data import StudyNotReady, repository_identity
from counterguard.study_fit import StudyFitSession, issue_fit_review
from counterguard.study_fit_models import StudyFit, StudyFitProtocol, StudySplit
from counterguard.study_models import StudyReplayPlan, StudySource
from scripts.fit_scope_study import main as fit_command
from tests.study_fit_support import prepare_training
from tests.unit.test_bootstrap_binding import pins


def source_fixture(repo):
    return _seal(
        StudySource(
            source_id="source",
            repository_identity_digest=repository_identity(repo),
            guard_ref="g/guard.json",
            guard_digest=digest_bytes(b"fixture guard"),
            evidence_digest=digest_bytes(b"fixture evidence"),
            binding_digest=digest_bytes(b"fixture binding"),
            buggy_commit="a" * 40,
            fixed_commit="b" * 40,
            assertion_head="c" * 40,
            contract_ref="contracts/fixture.json",
            contract_digest=ZERO,
            case_ids=("case_" + "a" * 24,),
            artifact_digest=ZERO,
        )
    )


@pytest.fixture
def training(tmp_path, monkeypatch):
    import counterguard.study_data as data

    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    source = source_fixture(source_repo)
    monkeypatch.setattr(fit_module, "inspect_source", lambda *a, **kw: (source, None, ()))
    trees = {}

    def commit_files(name, files):
        repo = tmp_path / ("repo-" + name)
        repo.mkdir()
        revision = digest_bytes(name.encode()).split(":")[1][:40]
        trees[repo.resolve()] = (revision, files, pins(files))
        return repo, revision

    def committed(repo, revision):
        result = trees[repo.resolve()]
        assert result[0] == revision
        return result[0], result[1], pins(result[1])

    monkeypatch.setattr(data, "read_committed_files", committed)
    protocol, split, repositories, snapshots = prepare_training(tmp_path, source, commit_files)
    review = issue_fit_review(
        source_repo,
        tmp_path,
        "protocol.json",
        output_ref="review.json",
        operator="fixture reviewer",
        reason="Freeze synthetic training membership before fitting",
    )
    session = StudyFitSession(source_repo, tmp_path, repositories, review.artifact_digest)
    return session, protocol, split, review, snapshots


def rewrite(path, change):
    data = json.loads(path.read_bytes())
    change(data)
    from counterguard.digests import digest_json_artifact

    data["artifact_digest"] = digest_json_artifact(data)
    path.write_bytes(canonical_json_bytes(data))


def reapprove(training, *, mutate_split=None, mutate_protocol=None):
    session, _, _, _, _ = training
    root = session.workspace
    if mutate_split:
        rewrite(root / "split.json", mutate_split)
        digest = json.loads((root / "split.json").read_bytes())["artifact_digest"]
        rewrite(root / "protocol.json", lambda row: row.update(split_digest=digest))
    if mutate_protocol:
        rewrite(root / "protocol.json", mutate_protocol)
    review = issue_fit_review(
        session.source_repo,
        root,
        "protocol.json",
        output_ref="updated-review.json",
        operator="fixture reviewer",
        reason="Explicit new fixture review before new fit",
    )
    return replace(session, review_anchor=review.artifact_digest), "updated-review.json"


def test_initial_refined_and_independent_rebuild_preserve_core_learning_guarantees(training):
    session, _, _, _, _ = training
    initial = session.fit(
        "protocol.json", "review.json", phase="initial", output=Path("initial.json")
    )
    refined = session.fit(
        "protocol.json", "review.json", phase="refined", output=Path("refined.json")
    )
    assert initial.status == refined.status == "fitted"
    assert [(c.field, c.value) for c in initial.scope.clauses] == [("contract_version", "v2")]
    assert [(c.field, c.value) for c in refined.scope.clauses] == [
        ("contract_version", "v2"),
        ("interface_kind", "value_return"),
    ]
    assert initial.learning.training_confusion.model_dump() == {"tp": 2, "fp": 0, "tn": 1, "fn": 0}
    assert refined.learning.training_confusion.model_dump() == {"tp": 2, "fp": 0, "tn": 2, "fn": 0}
    assert len(refined.explanation.clause_witnesses) == 2
    assert not initial.execution_allowed and not refined.scope.execution_allowed
    assert session.verify(Path("initial.json")) == initial
    assert session.verify(Path("refined.json")) == refined
    assert "created_at" not in type(initial).model_fields
    assert (
        session.fit("protocol.json", "review.json", phase="refined", output=Path("refined.json"))
        == refined
    )


def test_future_phase_and_holdout_are_not_opened_even_when_fitting_refined(training, monkeypatch):
    session, _, _, _, _ = training
    original = fit_module._model
    opened = []

    def read(workspace, ref, model):
        assert "holdout" not in ref
        opened.append(ref)
        return original(workspace, ref, model)

    monkeypatch.setattr(fit_module, "_model", read)
    session.fit("protocol.json", "review.json", phase="initial")
    assert not any(ref.startswith("d/") for ref in opened)
    opened.clear()
    session.fit("protocol.json", "review.json", phase="refined")
    assert "d/sample.json" in opened and "d/label.json" in opened
    opened.clear()
    with pytest.raises(ValidationError):
        session.fit("protocol.json", "review.json", phase="holdout")
    assert opened == []


def test_fit_review_freezes_inputs_without_running_the_learner(training, monkeypatch):
    session, _, _, _, _ = training

    def forbidden(*args, **kwargs):
        pytest.fail("Review must precede outcomes and cannot fit")

    monkeypatch.setattr(fit_module, "learn_scope", forbidden)
    review = issue_fit_review(
        session.source_repo,
        session.workspace,
        "protocol.json",
        output_ref="before-fit.json",
        operator="operator",
        reason="Approve inputs, not an outcome",
    )
    assert review.action == "approve"


def test_twenty_training_iteration_orders_keep_rule_fit_digest_and_original_inputs(
    training, monkeypatch
):
    session, _, _, _, _ = training
    baseline = session.fit("protocol.json", "review.json", phase="refined")
    original = fit_module.learn_scope
    calls = []

    def shuffled(examples):
        values = list(examples)
        random.Random(len(calls)).shuffle(values)
        calls.append(tuple(row.guard_applicable for row in values))
        assert all(type(row.features).__name__ == "FeatureVector" for row in values)
        return original(tuple(values))

    monkeypatch.setattr(fit_module, "learn_scope", shuffled)
    for _ in range(20):
        current = session.fit("protocol.json", "review.json", phase="refined")
        assert current == baseline
    assert len(set(calls)) > 1


@pytest.mark.parametrize(
    "path,field",
    [
        ("a/sample.json", "project_group"),
        ("a/context.json", "module_group"),
        ("a/label.json", "reason"),
        ("a/audit.json", "matched"),
        ("a/target.json", "assessment_digest"),
        ("protocol.json", "source_project_group"),
        ("split.json", "split_id"),
        ("review.json", "reason"),
    ],
)
def test_resigned_pinned_inputs_are_not_authority(training, path, field):
    session, _, _, _, _ = training
    rewrite(
        session.workspace / path,
        lambda row: row.update({field: False if field == "matched" else "changed"}),
    )
    with pytest.raises((ArtifactIntegrityError, ValidationError)):
        session.fit("protocol.json", "review.json", phase="initial")


@pytest.mark.parametrize("part", ["scope", "learning", "explanation", "implementation", "inputs"])
def test_resigned_fit_results_must_rebuild_every_fact(training, part):
    session, _, _, _, _ = training
    session.fit("protocol.json", "review.json", phase="refined", output=Path("fit.json"))

    def mutate(row):
        if part == "scope":
            row["scope"]["clauses"][0]["value"] = "forged"
        elif part == "learning":
            row["learning"]["training_dataset_digest"] = ZERO
        elif part == "explanation":
            row["explanation"]["negative_count"] += 1
        elif part == "implementation":
            row["implementation_digests"] = {"fake.py": ZERO}
        else:
            row["inputs"][0]["context_digest"] = ZERO

    rewrite(session.workspace / "fit.json", mutate)
    with pytest.raises((ArtifactIntegrityError, ValidationError)):
        session.verify(Path("fit.json"))


def test_no_negative_is_a_retained_verifiable_refusal_not_global_scope(training):
    session, ref = reapprove(
        training, mutate_split=lambda row: row.update(initial=row["initial"][:2])
    )
    result = session.fit("protocol.json", ref, phase="initial", output=Path("refusal.json"))
    assert result.status == "refused" and result.refusal_code == "no_counterexample"
    assert result.scope is result.learning is result.explanation is None
    assert session.verify(Path("refusal.json")) == result


def test_too_few_positives_and_no_refinement_do_not_invent_rules(training):
    session, ref = reapprove(
        training,
        mutate_split=lambda row: row.update(initial=[row["initial"][0]], refinement_additions=[]),
    )
    result = session.fit("protocol.json", ref, phase="initial")
    assert result.status == "refused" and result.refusal_code == "too_few_positives"
    with pytest.raises(StudyNotReady, match="refinement_missing"):
        session.fit("protocol.json", ref, phase="refined")


def test_missing_repository_and_changed_committed_source_are_distinct(training):
    session, _, _, _, snapshots = training
    with pytest.raises(StudyNotReady, match="repository_missing"):
        replace(session, repositories={}).fit("protocol.json", "review.json", phase="initial")
    snapshots["a"]["src/fixture_target/core.py"] += b"# changed\n"
    with pytest.raises(ArtifactIntegrityError, match="not_rebuilt"):
        session.fit("protocol.json", "review.json", phase="initial")


def test_review_withdrawal_stale_implementation_and_output_boundaries(training):
    session, _, _, review, _ = training
    for path in (Path("../escape.json"), session.source_repo / "fit.json"):
        with pytest.raises(ArtifactIntegrityError, match="output_"):
            session.fit("protocol.json", "review.json", phase="initial", output=path)
    withdrawn = issue_fit_review(
        session.source_repo,
        session.workspace,
        "protocol.json",
        output_ref="withdraw.json",
        operator="operator",
        reason="Withdraw fixture use",
        action="withdraw",
        previous_ref="review.json",
        previous_anchor=review.artifact_digest,
    )
    with pytest.raises(StudyNotReady, match="withdrawn"):
        replace(session, review_anchor=withdrawn.artifact_digest).fit(
            "protocol.json", "withdraw.json", phase="initial"
        )
    rewrite(
        session.workspace / "review.json",
        lambda row: row.update(implementation_digests={"fake": ZERO}),
    )
    raw = json.loads((session.workspace / "review.json").read_bytes())
    with pytest.raises(ArtifactIntegrityError, match="implementation_stale"):
        replace(session, review_anchor=raw["artifact_digest"]).fit(
            "protocol.json", "review.json", phase="initial"
        )


def test_split_rejects_alias_targets_groups_and_holdout_references(training):
    _, _, split, _, _ = training
    data = split.model_dump(mode="json")
    for field in ("sample_id", "target_key", "project_group", "repository_identity_digest"):
        bad = json.loads(json.dumps(data))
        bad["holdout"][0][field] = bad["initial"][0][field]
        with pytest.raises(ValidationError):
            StudySplit.model_validate_json(json.dumps(bad))
    bad = json.loads(json.dumps(data))
    bad["holdout"][0]["label_ref"] = "holdout/labels.json"
    with pytest.raises(ValidationError):
        StudySplit.model_validate_json(json.dumps(bad))


def test_source_cannot_be_laundered_into_holdout(training):
    session, protocol, split, _, _ = training
    rewrite(
        session.workspace / "split.json",
        lambda row: row["holdout"][0].update(project_group=protocol.source_project_group),
    )
    updated = json.loads((session.workspace / "split.json").read_bytes())["artifact_digest"]
    rewrite(session.workspace / "protocol.json", lambda row: row.update(split_digest=updated))
    with pytest.raises(ArtifactIntegrityError, match="source_in_holdout"):
        issue_fit_review(
            session.source_repo,
            session.workspace,
            "protocol.json",
            output_ref="invalid-review.json",
            operator="operator",
            reason="must reject",
        )
    assert not (session.workspace / "invalid-review.json").exists()


def test_cli_fitted_and_refused_semantics_and_holdout_argument_rejected_early(training, capsys):
    session, _, _, review, _ = training
    shared = [
        "--workspace",
        str(session.workspace),
        "--source-repo",
        str(session.source_repo),
        "--review-digest",
        review.artifact_digest,
    ]
    for repo in session.repositories.values():
        shared += ["--repository", str(repo)]
    args = [
        "fit",
        *shared,
        "--protocol",
        "protocol.json",
        "--review",
        "review.json",
        "--phase",
        "initial",
        "--output",
        "cli.json",
    ]
    assert fit_command(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "fitted"
    assert fit_command(["verify", *shared, "--result", "cli.json"]) == 0
    capsys.readouterr()
    args[args.index("initial")] = "holdout"
    with pytest.raises(SystemExit) as error:
        fit_command(args)
    assert error.value.code == 2


def test_new_scope_and_fit_are_not_accepted_by_production_or_c1_replay(training):
    from counterguard.baselines import ScopePredicate

    session, _, _, _, _ = training
    result = session.fit("protocol.json", "review.json", phase="initial")
    with pytest.raises(ValidationError):
        ScopePredicate.model_validate_json(result.scope.model_dump_json())
    with pytest.raises(ValidationError):
        StudyReplayPlan.model_validate_json(result.model_dump_json())
    assert isinstance(result, FrozenModel) and type(result) is StudyFit


def test_protocol_cannot_enable_execution_or_change_learner_budget(training):
    _, protocol, _, _, _ = training
    for field, value in (
        ("execution_allowed", True),
        ("max_predicates", 33),
        ("learner", "lazy"),
        ("purpose", "external"),
    ):
        raw = protocol.model_dump(mode="json") | {field: value}
        with pytest.raises(ValidationError):
            StudyFitProtocol.model_validate_json(json.dumps(raw))


def test_fully_resigned_learning_chain_still_has_to_match_original_training(training):
    from counterguard.digests import digest_json_artifact

    session, _, _, _, _ = training
    result = session.fit("protocol.json", "review.json", phase="initial", output=Path("fit.json"))
    forged = result.model_dump(mode="json")
    forged["learning"]["training_dataset_digest"] = ZERO
    forged["learning"]["artifact_digest"] = digest_json_artifact(forged["learning"])
    forged["explanation"].update(
        training_dataset_digest=ZERO, learning_digest=forged["learning"]["artifact_digest"]
    )
    forged["explanation"]["artifact_digest"] = digest_json_artifact(forged["explanation"])
    forged["scope"].update(
        learning_digest=forged["learning"]["artifact_digest"],
        explanation_digest=forged["explanation"]["artifact_digest"],
    )
    forged["scope"]["artifact_digest"] = digest_json_artifact(forged["scope"])
    forged["artifact_digest"] = digest_json_artifact(forged)
    StudyFit.model_validate_json(json.dumps(forged))  # Structurally coherent, not true.
    (session.workspace / "fit.json").write_bytes(canonical_json_bytes(forged))
    with pytest.raises(ArtifactIntegrityError, match="does_not_rebuild"):
        session.verify(Path("fit.json"))


def test_predicate_budget_refuses_without_clipping_or_calling_learner(training, monkeypatch):
    from counterguard.study_features import study_training_example

    session, _, _, _, _ = training
    loaded = session._load("protocol.json", "review.json", "initial")
    features = loaded[-1][0].features
    examples = tuple(
        study_training_example(features.model_copy(update={"contract_family": f"family-{i}"}), True)
        for i in range(32)
    )
    monkeypatch.setattr(StudyFitSession, "_load", lambda *a: (*loaded[:-1], examples))

    def forbidden(*args):
        pytest.fail("Budget failure must precede search")

    monkeypatch.setattr(fit_module, "learn_scope", forbidden)
    with pytest.raises(StudyNotReady, match="predicate_budget"):
        session.fit("protocol.json", "review.json", phase="initial")


@pytest.mark.parametrize("decoy", [False, True])
def test_static_reexports_bind_actual_definition_not_another_same_named_helper(
    training, monkeypatch, decoy
):
    import counterguard.study_data as data

    session, _, _, _, _ = training
    workspace = session.workspace / "static"
    workspace.mkdir()
    source = source_fixture(session.source_repo)
    trees = {}

    def commit_files(name, files):
        repo = workspace / ("repo-" + name)
        repo.mkdir()
        revision = digest_bytes(name.encode()).split(":")[1][:40]
        trees[repo.resolve()] = (revision, files, pins(files))
        return repo, revision

    monkeypatch.setattr(data, "read_committed_files", lambda repo, rev: trees[repo.resolve()])
    _, _, repositories, _ = prepare_training(
        workspace, source, commit_files, reexport=True, decoy_context=decoy
    )
    review = issue_fit_review(
        session.source_repo,
        workspace,
        "protocol.json",
        output_ref="review.json",
        operator="reviewer",
        reason="Fixed root export and explicit actual definition",
    )
    static = StudyFitSession(session.source_repo, workspace, repositories, review.artifact_digest)
    if decoy:
        with pytest.raises(ArtifactIntegrityError, match="feature_subject"):
            static.fit("protocol.json", "review.json", phase="initial")
    else:
        result = static.fit("protocol.json", "review.json", phase="refined")
        assert result.status == "fitted" and len(result.scope.clauses) == 2


def approve_member_changes(training, name):
    session = training[0]
    root = session.workspace
    sample = json.loads((root / name / "sample.json").read_bytes())
    rewrite(
        root / name / "label.json", lambda row: row.update(sample_digest=sample["artifact_digest"])
    )
    label = json.loads((root / name / "label.json").read_bytes())

    def change(split):
        for row in split["initial"] + split["refinement_additions"]:
            if row["sample_id"] == name:
                row.update(
                    sample_digest=sample["artifact_digest"], label_digest=label["artifact_digest"]
                )

    return reapprove(training, mutate_split=change)


def test_manual_label_basis_is_rebuilt_from_git_even_after_new_trusted_review(training):
    root = training[0].workspace
    rewrite(root / "a/label.json", lambda row: row["basis_pins"][0].update(content_digest=ZERO))
    session, ref = approve_member_changes(training, "a")
    with pytest.raises(ArtifactIntegrityError, match="label_basis_changed"):
        session.fit("protocol.json", ref, phase="initial")


def test_annotation_mismatch_remains_unknown_and_keeps_both_sides(training):
    from counterguard.standalone_capture import _model
    from counterguard.study_features import StudyFeatureContext, audit_study_features
    from tests.unit.test_study_features import golden

    session, _, _, _, snapshots = training
    root = session.workspace
    context = _model(root, "a/context.json", StudyFeatureContext)
    expected = golden(("int:parse",)).model_copy(update={"contract_family": "price"})
    audit = audit_study_features(
        snapshots["a"][context.source_ref],
        context,
        expected,
        context_anchor=context.artifact_digest,
    )
    assert not audit.matched
    (root / "a/audit.json").write_bytes(canonical_json_bytes(audit))
    rewrite(root / "a/sample.json", lambda row: row.update(audit_digest=audit.artifact_digest))
    session, ref = approve_member_changes(training, "a")
    with pytest.raises(StudyNotReady, match="annotation_mismatch"):
        session.fit("protocol.json", ref, phase="initial")
    assert (root / "a/audit.json").read_bytes() == canonical_json_bytes(audit)


def test_refinement_cannot_introduce_a_positive_or_change_initial_learning(training):
    original = training[0].fit("protocol.json", "review.json", phase="initial")
    rewrite(
        training[0].workspace / "d/label.json",
        lambda row: row.update(guard_applicable=True, confirmed_legal_counterexample=False),
    )
    session, ref = approve_member_changes(training, "d")
    assert session.fit("protocol.json", ref, phase="initial").learning == original.learning
    with pytest.raises(ArtifactIntegrityError, match="refinement_must_be_legal_negative"):
        session.fit("protocol.json", ref, phase="refined")


def test_cli_retains_refusal_exit_four_and_verify_does_not_relabel_it_success(training, capsys):
    session, ref = reapprove(
        training, mutate_split=lambda row: row.update(initial=row["initial"][:2])
    )
    shared = [
        "--workspace",
        str(session.workspace),
        "--source-repo",
        str(session.source_repo),
        "--review-digest",
        session.review_anchor,
    ]
    for repo in session.repositories.values():
        shared += ["--repository", str(repo)]
    assert (
        fit_command(
            [
                "fit",
                *shared,
                "--protocol",
                "protocol.json",
                "--review",
                ref,
                "--phase",
                "initial",
                "--output",
                "refused-cli.json",
            ]
        )
        == 4
    )
    refusal = json.loads(capsys.readouterr().out)
    assert refusal["status"] == "refused" and refusal["scope"] is None
    assert fit_command(["verify", *shared, "--result", "refused-cli.json"]) == 0
    assert json.loads(capsys.readouterr().out) == refusal
