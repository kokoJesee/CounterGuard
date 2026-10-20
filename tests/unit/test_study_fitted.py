"""Full fit/replay provenance with synthetic transport; no real container execution."""

import ast
import base64
import json
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from counterguard.digests import canonical_json_bytes, digest_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.runners import docker
from counterguard.standalone_capture import _seal
from counterguard.study_fitted_models import StudyFittedAuthorization
from counterguard.study_models import StudyAuthorization
from counterguard.study_replay import StudySession
from tests.study_fitted_support import prepare_query, prepare_refused_initial
from tests.unit.test_bootstrap_binding import pins
from tests.unit.test_bootstrap_binding import repository as repository
from tests.unit.test_standalone_capture import capture_inputs as capture_inputs
from tests.unit.test_standalone_guard import guard_inputs as guard_inputs
from tests.unit.test_study_fit import rewrite
from tests.unit.test_study_fit_provenance import source_training as source_training

pytestmark = pytest.mark.slow


@pytest.fixture
def fitted(source_training, monkeypatch):
    import counterguard.bootstrap_binding as binding
    import counterguard.study_data as data
    import counterguard.study_replay as replay

    fit_session, _ = source_training
    root = fit_session.workspace
    for phase in ("initial", "refined"):
        fit_session.fit("protocol.json", "review.json", phase=phase, output=Path(phase + ".json"))
    original_reader = data.read_committed_files
    queries = {}

    def commit_files(name, files):
        repo = root / ("repo-" + name)
        repo.mkdir()
        revision = digest_bytes(name.encode()).split(":")[1][:40]
        queries[repo.resolve()] = (revision, files, pins(files))
        return repo, revision

    monkeypatch.setattr(
        data,
        "read_committed_files",
        lambda repo, rev: (
            queries[repo.resolve()] if repo.resolve() in queries else original_reader(repo, rev)
        ),
    )
    monkeypatch.setattr(replay, "read_committed_files", binding.read_committed_files)
    monkeypatch.setattr(replay, "_docker_executable", lambda: "docker")
    monkeypatch.setattr(replay, "_require_image_identity", lambda *a: None)
    session, plan = prepare_query(fit_session, "query", commit_files)
    calls = []

    def transport(argv, *, cwd, **kwargs):
        manifest = json.loads(base64.urlsafe_b64decode(argv[-1]))
        sandbox = Path(next(v for v in argv if v.startswith("type=bind")).split(",")[1][4:])
        tree = ast.parse((sandbox / manifest["test_ref"]).read_bytes())
        assignment = next(
            n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "CASES"
        )
        cases = json.loads(ast.literal_eval(assignment.value.args[0]))
        suite = ET.Element("testsuite")
        for case in cases:
            node = ET.SubElement(
                suite, "testcase", name="test_guard_case[case-" + case["case_id"][5:] + "]"
            )
            ET.SubElement(node, "failure", message="AssertionError")
        calls.append(manifest)
        return docker._BoundedProcessResult(
            0,
            canonical_json_bytes(
                {
                    "schema_version": "docker-runner-response.v1",
                    "pytest_exit_code": 1,
                    "timed_out": False,
                    "error_code": None,
                    "junit_produced": True,
                    "stdout_b64": "",
                    "stderr_b64": "",
                    "junit_b64": base64.b64encode(ET.tostring(suite)).decode(),
                    "python_version": "3.13.16",
                    "pytest_version": "8.4.2",
                }
            ),
            b"",
            False,
            False,
        )

    monkeypatch.setattr(docker, "_run_bounded", transport)
    return session, plan, calls, commit_files


def test_all_methods_share_runtime_and_old_parsers_cannot_consume_v7(fitted):
    session, plan, calls, _ = fitted
    for method, decision in (
        ("b1_always", "applicable"),
        ("b2_interface", "inapplicable"),
        ("learned_initial", "applicable"),
        ("learned_refined", "inapplicable"),
    ):
        selected = _seal(plan.model_copy(update={"method": method}))
        result = session.replay(selected, Path(method))
        assert result.admission.decision == result.admission.scope_decision.decision == decision
        assert (result.run is None) == (decision != "applicable")
        assert session.verify(Path(method) / "result.json") == result
        if result.run:
            raw = (session.workspace / result.authorization_ref).read_bytes()
            auth = StudyFittedAuthorization.model_validate_json(raw)
            assert auth.fit_review_digest == session.fit_session.review_anchor
            assert auth.scope_digest == result.admission.scope_digest
            with pytest.raises(ValidationError):
                StudyAuthorization.model_validate_json(raw)
    assert len(calls) == 2
    with pytest.raises(ValidationError):
        StudySession(
            session.source_repo, session.target_repo, session.workspace, session.review_anchor
        ).audit(plan)


@pytest.mark.parametrize(
    "ref",
    ["initial.json", "refined.json", "query/context.json", "query/audit.json", "query/review.json"],
)
def test_resigned_upstream_inputs_never_reach_transport(fitted, ref):
    session, plan, calls, _ = fitted
    # Keep each strict schema valid and recompute its self-digest. Provenance,
    # not merely a malformed field or missing signature, must reject the change.
    mutation = {
        "initial.json": {"training_binding_digest": digest_bytes(b"other initial members")},
        "refined.json": {"training_binding_digest": digest_bytes(b"other refined members")},
        "query/context.json": {"metadata_basis": "A different independently claimed basis"},
        "query/audit.json": {"expected_digest": digest_bytes(b"another manual vector")},
        "query/review.json": {"reason": "Another apparently valid execution review"},
    }[ref]
    rewrite(
        session.workspace / ref,
        lambda row: row.update(mutation),
    )
    result = session.replay(
        _seal(plan.model_copy(update={"method": "learned_initial"})), Path("rejected")
    )
    assert result.integrity == "invalid" and result.run is None and not calls


def test_independent_fit_anchor_and_query_decisions_cannot_be_forged(fitted):
    session, plan, calls, _ = fitted
    wrong = replace(session.fit_session, review_anchor=digest_bytes(b"other trusted anchor"))
    result = replace(session, fit_session=wrong).replay(plan, Path("bad-anchor"))
    assert result.integrity == "invalid" and result.run is None and not calls
    result = session.replay(
        _seal(plan.model_copy(update={"method": "learned_refined"})), Path("skip")
    )
    rewrite(
        session.workspace / "skip/result.json",
        lambda row: row.update(
            admission=_seal(result.admission.model_copy(update={"scope_digest": None})).model_dump(
                mode="json"
            )
        ),
    )
    with pytest.raises(ArtifactIntegrityError):
        session.verify(Path("skip/result.json"))


def test_post_run_fit_mutation_keeps_actual_run_and_refuses_verify(fitted, monkeypatch):
    import counterguard.study_replay as replay

    session, plan, calls, _ = fitted
    original = replay._execute_with_adapter

    def changed(request, adapter):
        run = original(request, adapter)
        rewrite(
            session.workspace / "initial.json",
            lambda row: row.update(training_binding_digest=digest_bytes(b"changed")),
        )
        return run

    monkeypatch.setattr(replay, "_execute_with_adapter", changed)
    result = session.replay(
        _seal(plan.model_copy(update={"method": "learned_initial"})), Path("late")
    )
    assert result.run is not None and result.integrity == "stale" and len(calls) == 1
    with pytest.raises((ArtifactIntegrityError, ValidationError)):
        session.verify(Path("late/result.json"))


def test_refused_initial_remains_unknown_with_zero_docker_discovery(fitted, monkeypatch):
    import counterguard.study_replay as replay

    session, _, calls, commit_files = fitted
    fit_session = prepare_refused_initial(session.fit_session)
    current, plan = prepare_query(
        fit_session,
        "refused-query",
        commit_files,
        initial_ref="positive-initial.json",
        refined_ref="positive-refined.json",
    )

    def forbidden():
        pytest.fail("unknown tried Docker discovery")

    monkeypatch.setattr(replay, "_docker_executable", forbidden)
    result = current.replay(
        _seal(plan.model_copy(update={"method": "learned_initial"})), Path("unknown")
    )
    assert result.integrity == "current" and result.outcome == "skipped_unknown"
    assert result.admission.decision == "unknown" and result.run is None and not calls
    assert result.admission.scope_digest is None
    assert result.admission.scope_decision.reason == "no_counterexample"
    assert current.verify(Path("unknown/result.json")) == result
    assert not list((current.workspace / "refused-query").glob("*label*"))


def test_swapped_fit_phases_and_output_in_training_repository_are_rejected(fitted):
    session, plan, calls, _ = fitted
    swapped = _seal(
        plan.model_copy(
            update={
                "initial_fit_ref": plan.refined_fit_ref,
                "refined_fit_ref": plan.initial_fit_ref,
            }
        )
    )
    result = session.replay(swapped, Path("swapped"))
    assert result.integrity == "invalid" and result.run is None and not calls
    training_repo = next(iter(session.fit_session.repositories.values()))
    with pytest.raises(ArtifactIntegrityError, match="output_in_repo"):
        session.replay(plan, training_repo / "must-not-write")
    assert not (training_repo / "must-not-write").exists()
