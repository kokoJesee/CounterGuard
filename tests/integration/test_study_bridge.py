"""Actual two-history research bridge. Every executed repository here is tool-owned."""

import importlib
import json
import os
from pathlib import Path

import pytest

from counterguard.models import RunOutcome
from counterguard.registry import Registry
from counterguard.runner_catalog import resolve_runner
from counterguard.runners.docker import _AdmittedDockerProcess
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.standalone_capture import ZERO, _seal, capture_standalone
from counterguard.standalone_guard import compile_standalone_guard
from counterguard.study_data import (
    inspect_source,
    inspect_target,
    issue_review,
    make_call_map,
    persist,
)
from counterguard.study_models import (
    StdoutWitnessCase,
    StudyCaseMap,
    StudyReplayPlan,
    StudyWitness,
)
from counterguard.study_replay import StudySession
from tests.repository_support import git
from tests.standalone_support import standalone_history

pytestmark = [pytest.mark.slow, pytest.mark.docker]


def test_real_research_bridge_preserves_source_oracle_and_independent_stdout(tmp_path, monkeypatch):
    review = resolve_runner(runner_id="root-pytest8", image_digest=None)
    if not os.environ.get("COUNTERGUARD_RUNNER_IMAGE_DIGEST"):
        pytest.skip("set COUNTERGUARD_RUNNER_IMAGE_DIGEST to run actual research Docker fixture")
    assert os.environ["COUNTERGUARD_RUNNER_IMAGE_DIGEST"] == review.image_digest
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("research fixture reached local executor")

    monkeypatch.setattr(LocalTrustedExecutor, "execute", forbidden)
    original = importlib.import_module

    def import_guard(name, *args, **kwargs):
        assert name.split(".")[0] not in {"sample", "other"}
        return original(name, *args, **kwargs)

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
        evidence_id="evd_bridge_source",
        review_reason="tool-owned independent source oracle",
        output=Path("c"),
    )
    assert evidence["reproduced"]
    guard = compile_standalone_guard(
        source_repo,
        Path("c/evidence.json"),
        guard_id="grd_bridge_source",
        review_reason="tool-owned minimal source check",
        output=Path("g"),
    )
    assert len(guard.case_ids) == 1
    source, _, facts = inspect_source(source_repo, tmp_path, "g/guard.json", source_id="source")
    contract = facts[-1]
    persist(tmp_path / "s.json", source)
    target_repo = tmp_path / "other-repo"
    target_repo.mkdir()
    git(target_repo, "init", "-b", "main")
    git(target_repo, "config", "user.name", "CounterGuard fixture")
    git(target_repo, "config", "user.email", "fixture@example.invalid")
    package = target_repo / "src/other"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("# Independent tool-owned target\n", encoding="utf-8")
    normal = (
        "import os\ndef clamp(x):\n"
        " if os.environ.get('COUNTERGUARD_CONTRACT') != 'cg_control/contract.json':\n"
        "  raise RuntimeError('Docker only')\n"
        " if 'FORCE_COLOR' in os.environ: raise RuntimeError('host environment leaked')\n"
        " print(max(0, min(2, x)))\n"
    )
    (package / "core.py").write_text(normal, encoding="utf-8")
    (target_repo / "pyproject.toml").write_text(
        '[project]\nname="other"\ndependencies=[]\nrequires-python=">=3.12"\n[tool.pytest.ini_options]\nrequired_plugins=["must-not-load"]\n',
        encoding="utf-8",
    )
    (target_repo / "conftest.py").write_text(
        "raise RuntimeError('must not load')\n", encoding="utf-8"
    )
    (target_repo / "LICENSE").write_text("Tool-owned research fixture\n", encoding="utf-8")
    (target_repo / "README.md").write_text(
        "clamp prints the integer clamped to [0,2] and a newline\n", encoding="utf-8"
    )
    git(target_repo, "add", ".")
    git(target_repo, "commit", "-m", "tool-owned independent target")
    revision = git(target_repo, "rev-parse", "HEAD")
    monkeypatch.setenv("FORCE_COLOR", "1")

    def prepare(revision, name, *, witness=False):
        target, _ = inspect_target(
            target_repo,
            revision,
            target_id=name,
            module="other.core",
            symbol="clamp",
            import_root="src",
            profile="direct",
            license_ref="LICENSE",
        )
        mapping = make_call_map(
            source,
            target,
            contract,
            map_id=name,
            cases=[
                StudyCaseMap(
                    case_id=c.case_id,
                    source_assertion_digest=c.assertion_digest,
                    keyword_renames={},
                )
                for c in contract.cases
                if c.case_id in source.case_ids
            ],
        )
        persist(tmp_path / (name + "-t.json"), target)
        persist(tmp_path / (name + "-m.json"), mapping)
        witness_ref = None
        if witness:
            own = _seal(
                StudyWitness(
                    target_digest=target.artifact_digest,
                    map_digest=mapping.artifact_digest,
                    basis_refs=("README.md",),
                    cases=tuple(
                        StdoutWitnessCase(case_id=c.case_id, stdout="1\n") for c in mapping.cases
                    ),
                    artifact_digest=ZERO,
                )
            )
            witness_ref = name + "-w.json"
            persist(tmp_path / witness_ref, own)
        plan = _seal(
            StudyReplayPlan(
                source_ref="s.json",
                target_ref=name + "-t.json",
                map_ref=name + "-m.json",
                review_ref=name + "-review.json",
                witness_ref=witness_ref,
                method="b1_always",
                artifact_digest=ZERO,
            )
        )
        approval = issue_review(
            source_repo,
            target_repo,
            tmp_path,
            plan,
            output_ref=plan.review_ref,
            review_id=name,
            operator="tool-owned fixture",
            reason="reviewed complete source and independent target, map, witness and runner",
            source_interface="value_return",
            target_interface="stdout_write",
        )
        return StudySession(source_repo, target_repo, tmp_path, approval.artifact_digest), plan

    session, plan = prepare(revision, "normal", witness=True)
    first = session.replay(plan, Path("r1"))
    second = session.replay(plan, Path("r2"))
    assert first.outcome == second.outcome == "test_failed"
    assert [c.outcome for c in first.run.case_results] == [
        c.outcome for c in second.run.case_results
    ]
    assert session.verify(Path("r1/result.json")) == first
    own_plan = _seal(plan.model_copy(update={"lane": "witness"}))
    own = session.replay(own_plan, Path("own"))
    assert own.outcome == "passed" and session.verify(Path("own/result.json")) == own
    launches_before = len(launches)
    for method, decision in [
        ("b2_interface", "inapplicable"),
        ("learned_initial", "unknown"),
        ("learned_refined", "unknown"),
    ]:
        skipped = session.replay(_seal(plan.model_copy(update={"method": method})), Path(method))
        assert skipped.admission.decision == decision and skipped.run is None
        session.verify(Path(method) / "result.json")
    assert len(launches) == launches_before
    entry = Registry(tmp_path / "registry").add(
        tmp_path / "g/guard.json", cwd=tmp_path, repo=source_repo
    )
    assert entry.guard.guard_id == guard.guard_id
    assert not Registry(tmp_path / "registry").show(guard.guard_id)["verification_schedulable"]

    (package / "core.py").write_text(
        "raise ValueError('fixture import failure')\ndef clamp(x): print(x)\n", encoding="utf-8"
    )
    git(target_repo, "add", "src/other/core.py")
    git(target_repo, "commit", "-m", "tool-owned import-time ValueError attack")
    importing, import_plan = prepare(git(target_repo, "rev-parse", "HEAD"), "importing")
    imported = importing.replay(import_plan, Path("imported"))
    assert imported.outcome == "infrastructure_error"
    assert imported.run.outcome not in {RunOutcome.PASSED, RunOutcome.TEST_FAILED}
    importing.verify(Path("imported/result.json"))

    (package / "core.py").write_text(
        "import sys\ndef clamp(x): sys.stdout.close()\n", encoding="utf-8"
    )
    git(target_repo, "add", "src/other/core.py")
    git(target_repo, "commit", "-m", "tool-owned observer failure attack")
    observer, observer_plan = prepare(
        git(target_repo, "rev-parse", "HEAD"), "observer", witness=True
    )
    broken = observer.replay(
        _seal(observer_plan.model_copy(update={"lane": "witness"})), Path("observer-failed")
    )
    assert broken.outcome == "infrastructure_error"
    observer.verify(Path("observer-failed/result.json"))
    assert len(launches) == 9  # Source capture+self-check 4; replay 3; attacks 2.
    assert len(git(target_repo, "rev-list", "--max-parents=0", "HEAD").splitlines()) == 1
    assert git(source_repo, "rev-list", "--max-parents=0", "HEAD") != git(
        target_repo, "rev-list", "--max-parents=0", "HEAD"
    )
    summary = {
        "source_buggy_exit": evidence["buggy"]["run"]["pytest_exit_code"],
        "source_fixed_exit": evidence["fixed"]["run"]["pytest_exit_code"],
        "minimal_case_count": len(guard.case_ids),
        "source_contract_case_count": len(contract.cases),
        "guard_repeat_outcomes": [first.outcome, second.outcome],
        "repeat_counts_equal": True,
        "own_stdout_witness": own.outcome,
        "import_valueerror": imported.outcome,
        "observer_failure": broken.outcome,
        "docker_launch_count": len(launches),
        "skip_launch_count": 0,
        "production_candidate_schedulable": False,
        "runner_image": review.image_digest,
        "external_execution_count": 0,
    }
    (tmp_path / "summary.json").write_text(
        json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8"
    )
