"""Qualify external-purpose mechanics only on tool-owned Git and Docker fixtures."""

import importlib
import json
import os
from pathlib import Path

import pytest

from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import _AdmittedDockerProcess
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.standalone_capture import _seal, capture_standalone
from counterguard.standalone_guard import compile_standalone_guard
from counterguard.study_models import StudyAuthorization
from counterguard.study_observation_models import StudyObservationAuthorization
from tests.observation_support import prepare_observation, rgb_history

pytestmark = [pytest.mark.slow, pytest.mark.docker]


def test_real_observation_preserves_eight_cases_and_four_stdout_witnesses(tmp_path, monkeypatch):
    runner = resolve_runner(runner_id="root-pytest8", image_digest=None)
    if not os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST"):
        pytest.skip("set exact reviewed runner image for tool-owned observation qualification")
    assert os.environ["COUNTERGUARD_RUNNER_IMAGE_DIGEST"] == runner.image_digest
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("observation reached a local target executor")

    monkeypatch.setattr(LocalTrustedExecutor, "execute", forbidden)
    original_import = importlib.import_module

    def guarded(name, *args, **kwargs):
        assert name.split(".")[0] not in {"fixture_source", "fixture_target"}
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", guarded)
    launches = []
    original_process = _AdmittedDockerProcess.execute_process

    def counted(self, request, prepared):
        launches.append(request.target.module)
        return original_process(self, request, prepared)

    monkeypatch.setattr(_AdmittedDockerProcess, "execute_process", counted)
    source = rgb_history(tmp_path)
    evidence = capture_standalone(
        source,
        Path("bind/binding.json"),
        runner_id="root-pytest8",
        evidence_id="evd_observation_fixture",
        review_reason="Tool-owned original eight-case RGB contract",
        output=Path("c"),
    )
    assert evidence["reproduced"] and len(evidence["failing_case_ids"]) == 8
    guard = compile_standalone_guard(
        source,
        Path("c/evidence.json"),
        guard_id="grd_observation_fixture",
        review_reason="Tool-owned minimal failure set is all original eight cases",
        output=Path("g"),
    )
    assert len(guard.case_ids) == 8 and len(launches) == 4
    session, plan = prepare_observation(source, tmp_path)
    monkeypatch.setenv("FORCE_COLOR", "1")
    results = {}
    for lane, count, outcome in (("guard", 8, "test_failed"), ("witness", 4, "passed")):
        for trial in (1, 2):
            folder = f"{lane}{trial}"
            result = session.replay(_seal(plan.model_copy(update={"lane": lane})), Path(folder))
            assert result.integrity == "current" and result.outcome == outcome
            assert len(result.run.case_results) == count
            assert session.verify(Path(folder) / "result.json") == result
            auth = StudyObservationAuthorization.model_validate_json(
                (tmp_path / result.authorization_ref).read_bytes()
            )
            assert auth.purpose == result.purpose == "external_snapshot_observation_only"
            with pytest.raises(ValueError):
                StudyAuthorization.model_validate_json(auth.model_dump_json())
            results[lane, trial] = result
        first, second = results[lane, 1], results[lane, 2]
        assert first.admission == second.admission
        assert first.run.run_id != second.run.run_id
        assert [(c.case_id, c.outcome) for c in first.run.case_results] == [
            (c.case_id, c.outcome) for c in second.run.case_results
        ]
    assert len(launches) == 8
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "assurance": "tool_owned_fixture_not_external_target_observation",
                "docker_launch_count": 8,
                "external_execution_count": 0,
                "original_guard_case_count": 8,
                "stdout_subset_case_count": 4,
                "source_buggy_exit": evidence["buggy"]["run"]["pytest_exit_code"],
                "source_fixed_exit": evidence["fixed"]["run"]["pytest_exit_code"],
                "guard_outcome": results["guard", 1].outcome,
                "stdout_outcome": results["witness", 1].outcome,
                "repeat_counts_equal": True,
                "source_cases_removed": 0,
                "host_color_environment_forwarded": False,
                "runner_image": runner.image_digest,
                "labels_assigned": False,
                "formal_scope_v2_frozen": False,
            },
            sort_keys=True,
        )
        + "\n"
    )
