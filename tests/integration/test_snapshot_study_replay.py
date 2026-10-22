"""Real complete-snapshot four-method matrices; only known tool-owned fixtures."""

import importlib
import json
import os
from pathlib import Path

import pytest

from counterguard.digests import digest_bytes
from counterguard.protocol import SampleLabels
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import _AdmittedDockerProcess
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.snapshot_admission import ZERO, issue_snapshot_review, seal
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_study_evaluation import (
    SnapshotStudyEvaluationSession,
    issue_snapshot_study_evaluation_review,
)
from counterguard.snapshot_study_evaluation_models import (
    SnapshotStudyEvaluationMember,
    SnapshotStudyEvaluationPlan,
    SnapshotStudyQueryLabel,
)
from counterguard.snapshot_study_fit import (
    SnapshotStudyFitSession,
    inspect_snapshot_study_source,
    issue_snapshot_study_fit_review,
    snapshot_study_target_key,
)
from counterguard.study_data import persist
from counterguard.study_fit_models import StudyBasisPin
from tests.repository_support import git
from tests.snapshot_study_replay_support import prepare_snapshot_query
from tests.snapshot_study_support import prepare_snapshot_training
from tests.snapshot_support import snapshot_history

pytestmark = [pytest.mark.slow, pytest.mark.docker]


def test_full_replay(tmp_path, monkeypatch):
    runner = resolve_runner(runner_id="root-pytest8", image_digest=None)
    image = os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST")
    if not image:
        pytest.skip("set COUNTERGUARD_RUNNER_IMAGE_DIGEST to the reviewed exact image ID")
    assert image == runner.image_digest
    monkeypatch.chdir(tmp_path)
    original_import = importlib.import_module

    def import_guard(name, *args, **kwargs):
        assert name.split(".")[0] not in {"snapshot_sample", "snapshot_target", "snapshot_query"}
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", import_guard)
    monkeypatch.setattr(
        LocalTrustedExecutor, "execute", lambda *a, **k: pytest.fail("local target fallback")
    )
    starts = []
    original_process = _AdmittedDockerProcess.execute_process

    def counted(self, request, prepared):
        starts.append(request.target.module)
        with (tmp_path / "process-ledger.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps({"index": len(starts), "module": request.target.module}) + "\n")
        return original_process(self, request, prepared)

    monkeypatch.setattr(_AdmittedDockerProcess, "execute_process", counted)
    source_repo, binding = snapshot_history(tmp_path)
    execution = issue_snapshot_review(
        source_repo,
        tmp_path / "binding.json",
        kind="execution",
        reason="Tool-owned full snapshot, contract and Docker inputs reviewed",
        output=tmp_path / "execution.json",
    )
    source = SnapshotSession(
        source_repo,
        tmp_path,
        tmp_path / "binding.json",
        tmp_path / "execution.json",
        execution.artifact_digest,
    )
    evidence = source.capture(evidence_id="evd_snapshot_replay", output=Path("c"))
    assert evidence.reproduced
    guard = source.compile(
        tmp_path / "c/evidence.json", guard_id="grd_snapshot_replay", output=Path("g")
    )
    assert len(starts) == 4
    declaration = inspect_snapshot_study_source(
        source, evidence_ref="c/evidence.json", guard_ref="g/guard.json", source_id="source"
    )

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
        git(repo, "add", "--", *files)
        git(repo, "commit", "-m", "tool-owned complete snapshot study fixture")
        return repo, git(repo, "rev-parse", "HEAD")

    protocol, split, repositories, _ = prepare_snapshot_training(
        tmp_path, declaration, commit_files
    )
    fit_review = issue_snapshot_study_fit_review(
        source,
        "protocol.json",
        output_ref="fit-review.json",
        operator="fixture reviewer",
        reason="Review explicit synthetic training labels before fitting",
    )
    fit = SnapshotStudyFitSession(source, repositories, fit_review.artifact_digest)
    initial = fit.fit("protocol.json", "fit-review.json", phase="initial", output="initial.json")
    refined = fit.fit("protocol.json", "fit-review.json", phase="refined", output="refined.json")
    assert len(initial.scope.clauses) == 1 and len(refined.scope.clauses) == 2
    stdout, _, target, files = prepare_snapshot_query(fit, "stdout", commit_files, guard, binding)

    def evaluation(name, session, target, files):
        from datetime import UTC, datetime

        label = seal(
            SnapshotStudyQueryLabel(
                created_at=datetime.now(UTC),
                operator="fixture reviewer",
                reason="Synthetic query prints instead of returning; source rule inapplicable",
                sample_id=name,
                project_group="query-" + name,
                guard_digest=guard.artifact_digest,
                target_digest=target.artifact_digest,
                labels=SampleLabels(
                    guard_id=guard.guard_id,
                    guard_applicable=False,
                    guard_violation=None,
                    contract_compliant=True,
                    basis="Known tool-owned README policy",
                ),
                basis_pins=(
                    StudyBasisPin(ref="README.md", content_digest=digest_bytes(files["README.md"])),
                ),
                artifact_digest=ZERO,
            )
        )
        persist(tmp_path / name / "query-label.json", label)
        plan = seal(
            SnapshotStudyEvaluationPlan(
                evaluation_id=name,
                members=(
                    SnapshotStudyEvaluationMember(
                        row_id=name,
                        sample_id=name,
                        project_group=label.project_group,
                        guard_digest=guard.artifact_digest,
                        target_key=snapshot_study_target_key(target),
                        plan_ref=name + "/plan.json",
                        label_ref=name + "/query-label.json",
                        label_digest=label.artifact_digest,
                    ),
                ),
                artifact_digest=ZERO,
            )
        )
        plan_ref, review_ref = name + "/evaluation-plan.json", name + "/evaluation-review.json"
        persist(tmp_path / plan_ref, plan)
        review = issue_snapshot_study_evaluation_review(
            tmp_path,
            {name: session},
            plan_ref,
            output=review_ref,
            operator="fixture reviewer",
            reason="Review full four-method known fixture matrix",
        )
        return (
            SnapshotStudyEvaluationSession(tmp_path, {name: session}, review.artifact_digest),
            plan_ref,
            review_ref,
        )

    engine, plan_ref, review_ref = evaluation("stdout", stdout, target, files)
    first = engine.evaluate(plan_ref, review_ref, output="m1")
    assert [s.prediction.verdict for s in first.slots] == [
        "violation",
        "skipped_inapplicable",
        "violation",
        "skipped_inapplicable",
    ]
    assert len(starts) == 6
    assert all(
        s.role == "unscoped_guard_self_check_not_learned_scope_replay" for s in first.source_bugs
    )
    assert first.source_bugs[0].detected and first.source_bugs[0].fixed_passed
    assert first.metrics.paired.totals.corrected_false_applications == 1
    assert first.execution_failures == 0
    assert engine.verify("m1/evaluation.json") == first
    engine.report("m1/evaluation.json", output="report.md")
    engine.export("m1/evaluation.json", output="export")
    engine.compare("m1/evaluation.json", output="paired.json")
    assert len(starts) == 6
    second = engine.evaluate(plan_ref, review_ref, output="m2")
    assert [s.prediction for s in first.slots] == [s.prediction for s in second.slots]
    assert first.metrics == second.metrics and len(starts) == 8
    for a, b in zip(first.slots, second.slots, strict=True):
        run_a, run_b = stdout.verify(a.replay_ref).run, stdout.verify(b.replay_ref).run
        if run_a is None:
            assert run_b is None
        else:
            assert [(c.case_id, c.outcome) for c in run_a.case_results] == [
                (c.case_id, c.outcome) for c in run_b.case_results
            ]
    value, base, _, _ = prepare_snapshot_query(
        fit, "value", commit_files, guard, binding, stdout=False
    )
    passed = value.run(
        seal(base.model_copy(update={"method": "learned_refined"})), output="value-run"
    )
    assert passed.outcome == "passed" and len(starts) == 9
    assert value.verify("value-run/replay.json") == passed

    # A separate experiment has no initial negative; preserve refusal as unknown.
    positive_split = seal(
        split.model_copy(update={"split_id": "positive-only", "initial": split.initial[:2]})
    )
    persist(tmp_path / "positive-split.json", positive_split)
    positive_protocol = seal(
        protocol.model_copy(
            update={
                "protocol_id": "positive-only",
                "split_ref": "positive-split.json",
                "split_digest": positive_split.artifact_digest,
            }
        )
    )
    persist(tmp_path / "positive-protocol.json", positive_protocol)
    positive_review = issue_snapshot_study_fit_review(
        source,
        "positive-protocol.json",
        output_ref="positive-review.json",
        operator="fixture reviewer",
        reason="Separate experiment with no initial counterexample",
    )
    positive_fit = SnapshotStudyFitSession(source, repositories, positive_review.artifact_digest)
    refused = positive_fit.fit(
        "positive-protocol.json",
        "positive-review.json",
        phase="initial",
        output="positive-initial.json",
    )
    assert refused.status == "refused" and refused.scope is None
    positive_fit.fit(
        "positive-protocol.json",
        "positive-review.json",
        phase="refined",
        output="positive-refined.json",
    )
    unknown, _, unknown_target, unknown_files = prepare_snapshot_query(
        positive_fit,
        "unknown",
        commit_files,
        guard,
        binding,
        initial_ref="positive-initial.json",
        refined_ref="positive-refined.json",
    )
    unknown_engine, unknown_plan, unknown_review = evaluation(
        "unknown", unknown, unknown_target, unknown_files
    )
    unknown_result = unknown_engine.evaluate(unknown_plan, unknown_review, output="u1")
    assert [s.prediction.verdict for s in unknown_result.slots] == [
        "violation",
        "skipped_inapplicable",
        "skipped_unknown",
        "skipped_inapplicable",
    ]
    assert unknown.verify(unknown_result.slots[2].replay_ref).run is None
    unknown_engine.report("u1/evaluation.json", output="unknown-report.md")
    assert "| learned_initial | 0 | 0 | 0 | 1 | 0 |" in (tmp_path / "unknown-report.md").read_text()
    assert len(starts) == 10
    persist(
        tmp_path / "qualification.json",
        {
            "purpose": "tool_owned_snapshot_study_only",
            "external_containers": 0,
            "actual_container_calls": len(starts),
            "repeated_matrix_predictions_equal": True,
            "refusal_unknown_run_null": True,
            "refined_passing_execution": True,
            "evaluation_digest": first.artifact_digest,
            "repeat_digest": second.artifact_digest,
            "unknown_evaluation_digest": unknown_result.artifact_digest,
            "source_retention": "unscoped_guard_self_check_only",
            "initial_clause_count": len(initial.scope.clauses),
            "refined_clause_count": len(refined.scope.clauses),
            "source_buggy_cases": len(guard.buggy_check.run.case_results),
            "implementation_digests": first.implementation_digests,
        },
    )
