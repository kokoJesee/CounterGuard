"""Opt-in independent audit of two actual unified repository replays; no re-execution."""

import os
from pathlib import Path

import pytest

from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.execution import PytestRunRequest, verify_run_record
from counterguard.pilot_inputs import read_fact
from counterguard.repository_verify import ReviewedReplayAuthorization, authorize_reviewed_replay
from counterguard.verify import VerifyReportV2, VerifyRequest

pytestmark = pytest.mark.slow


def test_fixed_owner_head_repeats_bind_actual_runs_and_reviewed_authorization():
    manifest_ref = os.environ.get("COUNTERGUARD_PILOT_MANIFEST")
    report_refs = os.environ.get("COUNTERGUARD_VERIFY_REPORTS")
    if not manifest_ref or not report_refs:
        pytest.skip("set COUNTERGUARD_PILOT_MANIFEST and two COUNTERGUARD_VERIFY_REPORTS paths")
    root = Path(__file__).resolve().parents[2]
    manifest = read_fact(root / manifest_ref)
    reports = []
    run_ids = []
    for ref in report_refs.split(","):
        directory = (root / ref).resolve(strict=True)
        directory.relative_to(root)
        report = VerifyReportV2.model_validate_json((directory / "report.json").read_bytes())
        assert digest_json_artifact(report) == report.artifact_digest
        assert report.exit_code == 0 and report.counts["executions"] == report.counts["pass"] == 1
        row = report.rows[0]
        assert row.scope_basis == "pilot-scope.v1" and row.run is not None
        runtime = directory / row.run_workspace_ref
        authorization = ReviewedReplayAuthorization.model_validate_json(
            (runtime / "authorization.json").read_bytes()
        )
        assert digest_json_artifact(authorization) == authorization.artifact_digest
        request = VerifyRequest(
            root / manifest["repository_ref"],
            manifest["base_sha"],
            manifest["head_sha"],
            root / manifest["config_ref"],
            root / manifest["registry_root_ref"],
            directory,
            report.runner_image_digest,
            root,
        )
        run_request = PytestRunRequest(
            role=row.run.role,
            contract_id=row.run.contract_id,
            contract_digest=row.run.contract_digest,
            target=row.run.target,
            target_digest=row.run.target_digest,
            test_path=runtime / authorization.test_ref,
            known_case_ids=tuple(case.case_id for case in row.run.case_results),
            cwd=runtime,
            artifact_root=runtime / "a",
            contract_path=runtime / "contracts/mac-complete-v2.json",
        )
        rebuilt = authorize_reviewed_replay(request, row.guard_id, run_request)
        assert rebuilt == authorization
        assert (
            row.runner_review_digest
            == authorization.runner_review_digest
            == report.runner_review_digest
        )
        assert row.scope_digest == authorization.scope_digest
        verify_run_record(row.run, cwd=runtime, known_case_ids=run_request.known_case_ids)
        assert canonical_json_bytes(row.run) == (runtime / "run.json").read_bytes()
        reports.append(report)
        run_ids.append(row.run.run_id)
    assert len(reports) == 2 and len(set(run_ids)) == 2
    assert reports[0].head_commit == reports[1].head_commit == manifest["head_sha"]
    assert reports[0].counts == reports[1].counts
    assert reports[0].decision_digest == reports[1].decision_digest
