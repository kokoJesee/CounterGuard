"""Actual reviewed learning/replay chain, limited to independent tool-owned histories."""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from counterguard.digests import canonical_json_bytes
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import _AdmittedDockerProcess
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.standalone_capture import _seal, capture_standalone
from counterguard.standalone_guard import compile_standalone_guard
from counterguard.study_data import inspect_source
from counterguard.study_fit import StudyFitSession, issue_fit_review
from counterguard.study_fitted_models import StudyFittedAuthorization
from tests.repository_support import git
from tests.standalone_support import standalone_history
from tests.study_fit_support import prepare_training
from tests.study_fitted_support import prepare_query, prepare_refused_initial

pytestmark = [pytest.mark.slow, pytest.mark.docker]


def test_real_fitted_replay_keeps_three_way_decisions_and_original_oracle(tmp_path, monkeypatch):
    runner = resolve_runner(runner_id="root-pytest8", image_digest=None)
    if not os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST"):
        pytest.skip("set COUNTERGUARD_RUNNER_IMAGE_DIGEST for the actual fitted research fixture")
    assert os.environ["COUNTERGUARD_RUNNER_IMAGE_DIGEST"] == runner.image_digest
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("research reached the local target executor")

    monkeypatch.setattr(LocalTrustedExecutor, "execute", forbidden)
    original_import = importlib.import_module

    def import_guard(name, *args, **kwargs):
        assert name.split(".")[0] not in {"sample", "fixture_target"}
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", import_guard)
    launches = []
    original_process = _AdmittedDockerProcess.execute_process

    def counted(self, request, prepared):
        launches.append(request.target.module)
        return original_process(self, request, prepared)

    monkeypatch.setattr(_AdmittedDockerProcess, "execute_process", counted)
    source_repo = standalone_history(tmp_path, message_match=True)
    evidence = capture_standalone(
        source_repo,
        Path("bind/binding.json"),
        runner_id="root-pytest8",
        evidence_id="evd_fitted_source",
        review_reason="tool-owned fitted replay source",
        output=Path("c"),
    )
    assert evidence["reproduced"]
    guard = compile_standalone_guard(
        source_repo,
        Path("c/evidence.json"),
        guard_id="grd_fitted_source",
        review_reason="minimal original source oracle",
        output=Path("g"),
    )
    source, _, facts = inspect_source(source_repo, tmp_path, "g/guard.json", source_id="source")
    contract = facts[-1]
    assert len(source.case_ids) == len(guard.case_ids) == 1 and len(contract.cases) == 2
    assert len(launches) == 4

    def commit_files(name, files):
        repo = tmp_path / ("repo-" + name)
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "CounterGuard fixture")
        git(repo, "config", "user.email", "fixture@example.invalid")
        for ref, raw in files.items():
            path = repo / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        git(repo, "add", ".")
        git(repo, "commit", "-m", "tool-owned independent research fixture")
        return repo, git(repo, "rev-parse", "HEAD")

    _, _, repositories, _ = prepare_training(tmp_path, source, commit_files)
    review = issue_fit_review(
        source_repo,
        tmp_path,
        "protocol.json",
        output_ref="review.json",
        operator="tool-owned fixture reviewer",
        reason="fixed source, separate training repositories and reviewed fixture labels",
    )
    fit_session = StudyFitSession(source_repo, tmp_path, repositories, review.artifact_digest)
    fits = {}
    for phase in ("initial", "refined"):
        fits[phase] = fit_session.fit(
            "protocol.json", "review.json", phase=phase, output=Path(phase + ".json")
        )
    assert len(fits["initial"].scope.clauses) == 1
    assert len(fits["refined"].scope.clauses) == 2
    assert len(launches) == 4  # Training never executes a target.

    session, plan = prepare_query(fit_session, "query-stdout", commit_files)
    results = {}
    expected = {
        "b1_always": ("applicable", "test_failed"),
        "b2_interface": ("inapplicable", "skipped_inapplicable"),
        "learned_initial": ("applicable", "test_failed"),
        "learned_refined": ("inapplicable", "skipped_inapplicable"),
    }
    for method, (decision, outcome) in expected.items():
        before = len(launches)
        result = session.replay(_seal(plan.model_copy(update={"method": method})), Path(method))
        assert result.integrity == "current" and result.admission.decision == decision
        assert result.outcome == outcome
        assert len(launches) - before == (1 if decision == "applicable" else 0)
        assert session.verify(Path(method) / "result.json") == result
        results[method] = result
        if result.run:
            auth = StudyFittedAuthorization.model_validate_json(
                (tmp_path / result.authorization_ref).read_bytes()
            )
            assert auth.source_head == source.assertion_head
            assert auth.fit_review_digest == review.artifact_digest
            assert auth.known_case_ids == tuple(c.case_id for c in result.run.case_results)
            assert len(result.run.case_results) == 1
            assert (tmp_path / method / "w/cg_control/contract.json").read_bytes() == (
                source_repo / source.contract_ref
            ).read_bytes()

    repeated = session.replay(
        _seal(plan.model_copy(update={"method": "learned_initial"})), Path("repeated")
    )
    first = results["learned_initial"]
    assert repeated.outcome == first.outcome and repeated.run.run_id != first.run.run_id
    assert [(c.case_id, c.outcome) for c in repeated.run.case_results] == [
        (c.case_id, c.outcome) for c in first.run.case_results
    ]
    assert session.verify(Path("repeated/result.json")) == repeated

    normal, normal_plan = prepare_query(fit_session, "query-value", commit_files, stdout=False)
    passing = normal.replay(
        _seal(normal_plan.model_copy(update={"method": "learned_refined"})), Path("normal")
    )
    assert passing.outcome == "passed" and passing.admission.decision == "applicable"
    assert normal.verify(Path("normal/result.json")) == passing

    refused_fit = prepare_refused_initial(fit_session)
    unknown_session, unknown_plan = prepare_query(
        refused_fit,
        "query-refused",
        commit_files,
        initial_ref="positive-initial.json",
        refined_ref="positive-refined.json",
    )
    before = len(launches)
    unknown = unknown_session.replay(
        _seal(unknown_plan.model_copy(update={"method": "learned_initial"})), Path("unknown")
    )
    assert unknown.outcome == "skipped_unknown" and unknown.admission.decision == "unknown"
    assert unknown.run is None and unknown.admission.scope_decision.reason == "no_counterexample"
    assert unknown_session.verify(Path("unknown/result.json")) == unknown
    assert len(launches) == before == 8
    assert not list((tmp_path / "query-stdout").glob("*label*"))
    script = Path(__file__).resolve().parents[2] / "scripts/run_scope_study.py"
    cli_plan = _seal(unknown_plan.model_copy(update={"method": "learned_initial"}))
    (tmp_path / "unknown-plan.json").write_bytes(canonical_json_bytes(cli_plan))
    command = [
        sys.executable,
        str(script),
        "audit",
        "--workspace",
        str(tmp_path),
        "--source-repo",
        str(source_repo),
        "--target-repo",
        str(unknown_session.target_repo),
        "--review-digest",
        unknown_session.review_anchor,
        "--fit-review-digest",
        refused_fit.review_anchor,
        "--plan",
        "unknown-plan.json",
    ]
    for repo in repositories.values():
        command.extend(["--training-repository", str(repo)])
    process = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    assert process.returncode == 4, process.stdout + process.stderr
    assert json.loads(process.stdout)["decision"] == "unknown"
    summary = {
        "purpose": "tool_owned_fixture_only_not_formal_evaluation",
        "source_buggy_exit": evidence["buggy"]["run"]["pytest_exit_code"],
        "source_fixed_exit": evidence["fixed"]["run"]["pytest_exit_code"],
        "minimal_case_count": 1,
        "source_contract_case_count": 2,
        "initial_clause_count": len(fits["initial"].scope.clauses),
        "refined_clause_count": len(fits["refined"].scope.clauses),
        "query_methods": {
            method: {
                "decision": result.admission.decision,
                "outcome": result.outcome,
                "has_run": result.run is not None,
            }
            for method, result in results.items()
        },
        "repeat_counts_equal": True,
        "refined_value_outcome": passing.outcome,
        "refused_initial_outcome": unknown.outcome,
        "cli_unknown_audit_exit": process.returncode,
        "skip_launch_count": 0,
        "docker_launch_count": len(launches),
        "external_execution_count": 0,
        "runner_image": runner.image_digest,
    }
    (tmp_path / "summary.json").write_text(json.dumps(summary, sort_keys=True) + "\n")
