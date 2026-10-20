"""Explicitly synthetic query inputs; queries have no applicability label file."""

from dataclasses import replace
from pathlib import Path

from counterguard.standalone_capture import ZERO, _model, _seal
from counterguard.study_data import inspect_source, inspect_target, make_call_map, persist
from counterguard.study_features import audit_study_features
from counterguard.study_fit import issue_fit_review
from counterguard.study_fit_models import StudyFitProtocol, StudySplit
from counterguard.study_fitted import StudyFittedSession, issue_fitted_review
from counterguard.study_fitted_models import StudyFittedPlan
from counterguard.study_models import StudyCaseMap, StudySource
from tests.unit.test_study_features import context, golden


def prepare_query(
    fit_session,
    name,
    commit_files,
    *,
    stdout=True,
    initial_ref="initial.json",
    refined_ref="refined.json",
):
    workspace = fit_session.workspace
    body = (
        "print(x + 1)"
        if stdout
        else "if x == 1: raise ValueError('expected message')\n return x + 1"
    )
    interface = "stdout_write" if stdout else "value_return"
    raw = f"def target(x):\n {body}\n".encode()
    files = {
        "src/fixture_target/__init__.py": b"# Tool-owned independent query\n",
        "src/fixture_target/core.py": raw,
        "pyproject.toml": (
            b'[project]\nname="fixture-query"\ndependencies=[]\nrequires-python=">=3.12"\n'
        ),
        "LICENSE": b"CounterGuard tool-owned fixture\n",
        "README.md": f"Tool-owned query API: {interface}, {body}".encode(),
    }
    repo, revision = commit_files(name, files)
    target, _ = inspect_target(
        repo,
        revision,
        target_id=name,
        module="fixture_target.core",
        symbol="target",
        import_root="src",
        profile="direct",
        license_ref="LICENSE",
    )
    feature_context = context(
        raw,
        context_id=name,
        source_ref="src/fixture_target/core.py",
        contract_family="price",
        interface_kind=interface,
        metadata_basis="Tool-owned query API shape, no outcome or label",
    )
    expected = golden(()).model_copy(
        update={"contract_family": "price", "interface_kind": interface}
    )
    audit = audit_study_features(
        raw, feature_context, expected, context_anchor=feature_context.artifact_digest
    )
    assert audit.matched
    source = _model(workspace, "source.json", StudySource)
    _, _, facts = inspect_source(
        fit_session.source_repo, workspace, source.guard_ref, source_id=source.source_id
    )
    contract = facts[-1]
    mapping = make_call_map(
        source,
        target,
        contract,
        map_id=name,
        cases=[
            StudyCaseMap(
                case_id=c.case_id, source_assertion_digest=c.assertion_digest, keyword_renames={}
            )
            for c in contract.cases
            if c.case_id in source.case_ids
        ],
    )
    for kind, model in (
        ("target", target),
        ("context", feature_context),
        ("audit", audit),
        ("map", mapping),
    ):
        persist(workspace / name / (kind + ".json"), model)
    plan = _seal(
        StudyFittedPlan(
            source_ref="source.json",
            target_ref=f"{name}/target.json",
            map_ref=f"{name}/map.json",
            review_ref=f"{name}/review.json",
            method="b1_always",
            initial_fit_ref=initial_ref,
            refined_fit_ref=refined_ref,
            context_ref=f"{name}/context.json",
            audit_ref=f"{name}/audit.json",
            artifact_digest=ZERO,
        )
    )
    review = issue_fitted_review(
        fit_session.source_repo,
        repo,
        workspace,
        plan,
        fit_session,
        output_ref=plan.review_ref,
        review_id=name,
        operator="tool-owned fixture reviewer",
        reason="Fixed query snapshot, original minimal oracle and independent reviewed training",
        source_interface="value_return",
        target_interface=interface,
    )
    session = StudyFittedSession(
        fit_session.source_repo, repo, workspace, review.artifact_digest, fit_session
    )
    return session, plan


def prepare_refused_initial(fit_session):
    """A separately reviewed split with no initial negative; no invented empty Scope."""
    root = fit_session.workspace
    split = _model(root, "split.json", StudySplit)
    split = _seal(
        split.model_copy(
            update={
                "split_id": "positive-only-initial",
                "initial": split.initial[:2],
            }
        )
    )
    persist(root / "positive-split.json", split)
    protocol = _model(root, "protocol.json", StudyFitProtocol)
    protocol = _seal(
        protocol.model_copy(
            update={
                "protocol_id": "positive-only-initial",
                "split_ref": "positive-split.json",
                "split_digest": split.artifact_digest,
            }
        )
    )
    persist(root / "positive-protocol.json", protocol)
    review = issue_fit_review(
        fit_session.source_repo,
        root,
        "positive-protocol.json",
        output_ref="positive-review.json",
        operator="tool-owned fixture reviewer",
        reason="Separate fixture with no initial legal counterexample; refusal is required",
    )
    session = replace(fit_session, review_anchor=review.artifact_digest)
    for phase in ("initial", "refined"):
        result = session.fit(
            "positive-protocol.json",
            "positive-review.json",
            phase=phase,
            output=Path(f"positive-{phase}.json"),
        )
        if phase == "initial":
            assert result.status == "refused" and result.refusal_code == "no_counterexample"
            assert result.scope is None
    return session
