"""Full-snapshot research isolation and training determinism, with no real processes."""

import json
import random
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

import counterguard.snapshot_comparison_data as comparison_data
import counterguard.snapshot_study_fit as fit_module
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError, FeatureExtractionError
from counterguard.snapshot_admission import ZERO, seal
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_repository import SNAPSHOT_BUDGET, SnapshotManifest
from counterguard.snapshot_study_features import (
    audit_snapshot_study_features,
    verify_snapshot_study_feature_audit,
)
from counterguard.snapshot_study_fit import (
    SnapshotStudyFitSession,
    issue_snapshot_study_fit_review,
)
from counterguard.snapshot_study_models import (
    SnapshotStudyContext,
    SnapshotStudyFeatureAudit,
    SnapshotStudyFit,
    SnapshotStudySource,
)
from counterguard.study_data import StudyNotReady, repository_identity
from counterguard.study_features import StudyFeatureAudit, StudyFeatureContext
from counterguard.study_fit_models import StudyFit, StudyFitProtocol, StudySplit
from scripts.fit_snapshot_study import main as fit_command
from tests.snapshot_study_support import prepare_snapshot_training
from tests.unit.test_bootstrap_binding import pins


@pytest.fixture
def training(tmp_path, monkeypatch):
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    engine = SnapshotSession(
        source_repo, tmp_path, tmp_path / "binding.json", tmp_path / "execution.json", ZERO
    )
    source = seal(
        SnapshotStudySource(
            source_id="snapshot-source",
            repository_identity_digest=repository_identity(source_repo),
            evidence_ref="capture/evidence.json",
            guard_ref="guard/guard.json",
            binding_digest=digest_bytes(b"fixture binding"),
            evidence_digest=digest_bytes(b"fixture evidence"),
            guard_digest=digest_bytes(b"fixture guard"),
            source_review_digest=ZERO,
            buggy_commit="a" * 40,
            fixed_commit="b" * 40,
            head_commit="c" * 40,
            case_ids=("case_" + "a" * 24,),
            artifact_digest=ZERO,
        )
    )
    monkeypatch.setattr(fit_module, "inspect_snapshot_study_source", lambda *a, **k: source)
    trees = {}

    def commit_files(name, files):
        repo = tmp_path / ("repo-" + name)
        repo.mkdir()
        revision = digest_bytes(name.encode()).split(":")[1][:40]
        manifest = seal(
            SnapshotManifest(
                commit=revision,
                budget=SNAPSHOT_BUDGET,
                files=pins(files),
                total_bytes=sum(map(len, files.values())),
                sizes={p.object_id: len(files[p.path]) for p in pins(files)},
                artifact_digest=ZERO,
            )
        )
        trees[repo.resolve()] = manifest, files
        return repo, revision

    def read(repo, revision, **kw):
        manifest, files = trees[Path(repo).resolve()]
        assert manifest.commit == revision
        return manifest, files

    monkeypatch.setattr(comparison_data, "read_snapshot", read)
    protocol, split, repositories, snapshots = prepare_snapshot_training(
        tmp_path, source, commit_files
    )
    review = issue_snapshot_study_fit_review(
        engine,
        "protocol.json",
        output_ref="review.json",
        operator="fixture reviewer",
        reason="Freeze synthetic snapshot membership before fitting",
    )
    session = SnapshotStudyFitSession(engine, repositories, review.artifact_digest)
    return session, protocol, split, review, snapshots


def rewrite(path, updates):
    value = json.loads(path.read_bytes())
    updates(value)
    value["artifact_digest"] = digest_json_artifact(value)
    path.write_bytes(canonical_json_bytes(value))


def test_initial_refined_rebuild_and_original_learner(training):
    session, _, _, _, _ = training
    initial = session.fit("protocol.json", "review.json", phase="initial", output="initial.json")
    refined = session.fit("protocol.json", "review.json", phase="refined", output="refined.json")
    assert initial.status == refined.status == "fitted"
    assert [(c.field, c.value) for c in initial.scope.clauses] == [("contract_version", "v2")]
    assert [(c.field, c.value) for c in refined.scope.clauses] == [
        ("contract_version", "v2"),
        ("interface_kind", "value_return"),
    ]
    assert refined.learning.training_confusion.model_dump() == {"tp": 2, "fp": 0, "tn": 2, "fn": 0}
    assert len(refined.explanation.clause_witnesses) == 2
    assert session.verify("initial.json") == initial
    assert session.verify("refined.json") == refined
    assert not refined.execution_allowed and not refined.scope.execution_allowed
    assert "created_at" not in type(refined).model_fields


def test_initial_does_not_read_refinement_and_holdout_never_opens(training, monkeypatch):
    session, _, _, _, _ = training
    original = fit_module._model
    opened = []

    def read(workspace, ref, model):
        assert "held" not in ref and "holdout" not in ref
        opened.append(ref)
        return original(workspace, ref, model)

    monkeypatch.setattr(fit_module, "_model", read)
    session.fit("protocol.json", "review.json", phase="initial")
    assert not any(ref.startswith("d/") for ref in opened)
    opened.clear()
    session.fit("protocol.json", "review.json", phase="refined")
    assert "d/label.json" in opened
    opened.clear()
    with pytest.raises(ValidationError):
        session.fit("protocol.json", "review.json", phase="holdout")
    assert opened == []


def test_input_shuffle_twenty_times_preserves_rule_and_learning_digest(training, monkeypatch):
    session, _, _, _, _ = training
    original = SnapshotStudyFitSession._load
    expected = session.fit("protocol.json", "review.json", phase="refined")
    for seed in range(20):

        def load(self, *args, _seed=seed, **kwargs):
            protocol, split, source, review, inputs, examples = original(self, *args, **kwargs)
            paired = list(zip(inputs, examples, strict=True))
            random.Random(_seed).shuffle(paired)
            return (
                protocol,
                split,
                source,
                review,
                tuple(x[0] for x in paired),
                tuple(x[1] for x in paired),
            )

        # Only the training input order changes; publications remain canonical.
        monkeypatch.setattr(SnapshotStudyFitSession, "_load", load)
        rows = load(session, "protocol.json", "review.json", "refined")[-1]
        actual = fit_module.learn_scope(rows)
        assert actual == expected.learning


@pytest.mark.parametrize("ref", ["source.json", "a/target.json", "a/label.json", "a/audit.json"])
def test_resigned_input_cannot_replace_source_reconstruction_or_pins(training, ref):
    session, _, _, _, _ = training
    path = session.workspace / ref
    field = {
        "source.json": "guard_digest",
        "a/target.json": "license_digest",
        "a/label.json": "guard_digest",
        "a/audit.json": "expected_digest",
    }[ref]
    rewrite(path, lambda row: row.update({field: ZERO}))
    with pytest.raises(ArtifactIntegrityError):
        session.fit("protocol.json", "review.json", phase="initial")


def test_independent_namespaces_reject_each_others_records(training):
    session, protocol, split, _, _ = training
    for old, new in ((StudyFitProtocol, protocol), (StudySplit, split)):
        with pytest.raises(ValidationError):
            old.model_validate_json(new.model_dump_json())
        legacy = new.model_dump() | {
            "schema_version": old.model_fields["schema_version"].default,
            "purpose": "tool_owned_research_fixture_only",
        }
        if old is StudyFitProtocol:
            legacy["extractor"] = "ast-features.study.v1"
        old_record = old(**legacy)
        with pytest.raises(ValidationError):
            type(new).model_validate_json(old_record.model_dump_json())
    result = session.fit("protocol.json", "review.json", phase="initial")
    with pytest.raises(ValidationError):
        StudyFit.model_validate_json(result.model_dump_json())
    assert type(result) is SnapshotStudyFit


def test_context_and_audit_do_not_become_old_fixture_features(training):
    session, _, _, _, _ = training
    context = fit_module._model(session.workspace, "a/context.json", SnapshotStudyContext)
    audit = fit_module._model(session.workspace, "a/audit.json", SnapshotStudyFeatureAudit)
    for old, value in ((StudyFeatureContext, context), (StudyFeatureAudit, audit)):
        with pytest.raises(ValidationError):
            old.model_validate_json(value.model_dump_json())


def test_wrong_anchor_and_withdrawal_cannot_fit(training):
    session, _, _, review, _ = training
    with pytest.raises(ArtifactIntegrityError, match="anchor"):
        replace(session, review_anchor=ZERO).fit("protocol.json", "review.json", phase="initial")
    withdrawn = issue_snapshot_study_fit_review(
        session.source,
        "protocol.json",
        output_ref="withdrawn.json",
        operator="fixture reviewer",
        reason="Withdraw before any new training",
        action="withdraw",
        previous_ref="review.json",
        previous_anchor=review.artifact_digest,
    )
    with pytest.raises(StudyNotReady, match="withdrawn"):
        replace(session, review_anchor=withdrawn.artifact_digest).fit(
            "protocol.json", "withdrawn.json", phase="initial"
        )


def test_unsupported_syntax_does_not_create_empty_features(training):
    session, _, _, _, snapshots = training
    target = fit_module._model(
        session.workspace, "a/target.json", comparison_data.SnapshotComparisonTarget
    )
    context = fit_module._model(session.workspace, "a/context.json", SnapshotStudyContext)
    files = dict(snapshots["a"])
    raw = b"def target(x):\n try: return int(x)\n except ValueError: return 0\n"
    files[context.source_ref] = raw
    manifest = seal(target.manifest.model_copy(update={"files": pins(files)}))
    target = seal(target.model_copy(update={"manifest": manifest}))
    context = seal(
        context.model_copy(
            update={"target_digest": target.artifact_digest, "source_digest": digest_bytes(raw)}
        )
    )
    expected = fit_module._model(
        session.workspace, "a/audit.json", SnapshotStudyFeatureAudit
    ).expected
    with pytest.raises(FeatureExtractionError, match="unsupported"):
        audit_snapshot_study_features(
            target,
            files,
            context,
            expected,
            context_anchor=context.artifact_digest,
        )


def test_feature_audit_rebuilds_witness_and_annotation_not_only_self_digest(training):
    session, _, _, _, snapshots = training
    target = fit_module._model(
        session.workspace, "a/target.json", comparison_data.SnapshotComparisonTarget
    )
    context = fit_module._model(session.workspace, "a/context.json", SnapshotStudyContext)
    audit = fit_module._model(session.workspace, "a/audit.json", SnapshotStudyFeatureAudit)
    changed = seal(audit.model_copy(update={"matched": False}))
    with pytest.raises(ArtifactIntegrityError, match="not_rebuilt"):
        verify_snapshot_study_feature_audit(target, snapshots["a"], context, changed)


def reapprove(training, change):
    session, _, _, _, _ = training
    rewrite(session.workspace / "split.json", change)
    split = json.loads((session.workspace / "split.json").read_bytes())
    rewrite(
        session.workspace / "protocol.json",
        lambda row: row.update(split_digest=split["artifact_digest"]),
    )
    review = issue_snapshot_study_fit_review(
        session.source,
        "protocol.json",
        output_ref="new-review.json",
        operator="fixture reviewer",
        reason="Explicit new synthetic membership review before fitting",
    )
    return replace(session, review_anchor=review.artifact_digest), "new-review.json"


def test_no_negative_retains_verifiable_refusal(training):
    session, ref = reapprove(training, lambda row: row.update(initial=row["initial"][:2]))
    result = session.fit("protocol.json", ref, phase="initial", output="refused.json")
    assert result.status == "refused" and result.refusal_code == "no_counterexample"
    assert result.scope is result.learning is result.explanation is None
    assert session.verify("refused.json") == result


def test_source_and_train_cannot_be_laundered_into_holdout(training):
    _, protocol, split, _, _ = training
    from counterguard.snapshot_study_models import SnapshotStudySplit

    for field in ("sample_id", "target_key", "project_group", "repository_identity_digest"):
        raw = json.loads(split.model_dump_json())
        raw["holdout"][0][field] = raw["initial"][0][field]
        with pytest.raises(ValidationError):
            SnapshotStudySplit.model_validate_json(json.dumps(raw))
    with pytest.raises(ArtifactIntegrityError, match="source_in_holdout"):
        reapprove(
            training,
            lambda row: row["holdout"][0].update(project_group=protocol.source_project_group),
        )


def test_exact_fixture_session_type_required(training):
    session, _, _, _, _ = training

    class ExtendedSession(SnapshotSession):
        pass

    original = session.source
    extended = ExtendedSession(
        original.repo,
        original.workspace,
        original.binding_path,
        original.review_path,
        original.trusted_digest,
    )
    with pytest.raises(ArtifactIntegrityError, match="fixture_source_type"):
        SnapshotStudyFitSession(extended, session.repositories, session.review_anchor)


def test_only_feature_vectors_and_bools_reach_learner(training, monkeypatch):
    from counterguard.predicates import FeatureVector
    from counterguard.scope import TrainingExample

    session, _, _, _, _ = training
    original = fit_module.learn_scope
    seen = []

    def guarded(rows):
        assert all(type(r) is TrainingExample and type(r.features) is FeatureVector for r in rows)
        assert all(type(r.guard_applicable) is bool for r in rows)
        seen.extend(rows)
        return original(rows)

    monkeypatch.setattr(fit_module, "learn_scope", guarded)
    session.fit("protocol.json", "review.json", phase="refined")
    assert len(seen) == 4


def test_fit_output_and_verify_cannot_escape_workspace_or_enter_repository(training):
    session, _, _, _, _ = training
    for path in (Path("../escape.json"), session.source.repo / "fit.json"):
        with pytest.raises(ArtifactIntegrityError):
            session.fit("protocol.json", "review.json", phase="initial", output=path)
    with pytest.raises(ArtifactIntegrityError, match="path_escape"):
        session.verify("../escape.json")


def test_cli_success_refusal_and_no_holdout_argument(training, capsys):
    session, _, _, review, _ = training
    common = [
        "--workspace",
        str(session.workspace),
        "--source-repo",
        str(session.source.repo),
        "--source-binding",
        "binding.json",
        "--source-review",
        "execution.json",
        "--source-review-digest",
        ZERO,
        "--fit-review-digest",
        review.artifact_digest,
    ]
    for repo in session.repositories.values():
        common += ["--repository", str(repo)]
    args = [
        "fit",
        *common,
        "--protocol",
        "protocol.json",
        "--review",
        "review.json",
        "--phase",
        "initial",
        "--output",
        "cli-fit.json",
    ]
    assert fit_command(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "fitted" and result["execution_allowed"] is False
    assert fit_command(["verify", *common, "--result", "cli-fit.json"]) == 0
    capsys.readouterr()
    invalid = list(args)
    invalid[invalid.index("initial")] = "holdout"
    with pytest.raises(SystemExit) as error:
        fit_command(invalid)
    assert error.value.code == 2
