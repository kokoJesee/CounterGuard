"""Real research admission and transport-shaped doubles, without starting a process."""

import ast
import base64
import copy
import importlib
import json
import random
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.runners import docker
from counterguard.standalone_capture import ZERO, _seal
from counterguard.standalone_models import StandaloneAuthorization, StandaloneGuardAuthorization
from counterguard.study_data import (
    inspect_source,
    inspect_target,
    issue_review,
    make_call_map,
    persist,
)
from counterguard.study_models import (
    StdoutWitnessCase,
    StudyAuthorization,
    StudyCallMap,
    StudyCaseMap,
    StudyReplayPlan,
    StudyWitness,
)
from counterguard.study_replay import StudySession, replay_exit_code
from tests.unit.test_bootstrap_binding import H, pins
from tests.unit.test_bootstrap_binding import repository as repository
from tests.unit.test_standalone_capture import capture_inputs as capture_inputs
from tests.unit.test_standalone_capture import resign
from tests.unit.test_standalone_guard import compile_fixture
from tests.unit.test_standalone_guard import guard_inputs as guard_inputs

data = importlib.import_module("counterguard.study_data")
replay_module = importlib.import_module("counterguard.study_replay")
binding = importlib.import_module("counterguard.bootstrap_binding")
T = "e" * 40
pytestmark = pytest.mark.slow  # Full provenance/persistence pipeline, even with a transport double.


@pytest.fixture
def study(guard_inputs, monkeypatch):
    source_repo, _, contract, _, _, workspace, _ = guard_inputs
    guard = compile_fixture(source_repo)
    source, _, _ = inspect_source(source_repo, workspace, "g/guard.json", source_id="source")
    target_repo = workspace / "target"
    target_repo.mkdir()
    target_files = {
        "src/other/__init__.py": b"# Tool-owned fixture\n",
        "src/other/core.py": b"def clamp(x): print(x)\n",
        "pyproject.toml": b'[project]\nname="other"\ndependencies=[]\nrequires-python=">=3.12"\n',
        "LICENSE": b"Tool-owned fixture\n",
        "README.md": b"clamp prints the input integer followed by a newline\n",
    }
    monkeypatch.setattr(
        data, "read_committed_files", lambda repo, revision: (T, target_files, pins(target_files))
    )
    monkeypatch.setattr(replay_module, "read_committed_files", binding.read_committed_files)
    target, _ = inspect_target(
        target_repo,
        T,
        target_id="target",
        module="other.core",
        symbol="clamp",
        import_root="src",
        profile="direct",
        license_ref="LICENSE",
    )
    rows = [
        StudyCaseMap(
            case_id=c.case_id, source_assertion_digest=c.assertion_digest, keyword_renames={}
        )
        for c in contract.cases
        if c.case_id in guard.case_ids
    ]
    mapping = make_call_map(source, target, contract, map_id="map", cases=rows)
    witness = _seal(
        StudyWitness(
            target_digest=target.artifact_digest,
            map_digest=mapping.artifact_digest,
            basis_refs=("README.md",),
            cases=tuple(StdoutWitnessCase(case_id=r.case_id, stdout="1\n") for r in rows),
            artifact_digest=ZERO,
        )
    )
    for name, value in [
        ("s.json", source),
        ("t.json", target),
        ("m.json", mapping),
        ("w.json", witness),
    ]:
        persist(workspace / name, value)
    plan = _seal(
        StudyReplayPlan(
            source_ref="s.json",
            target_ref="t.json",
            map_ref="m.json",
            witness_ref="w.json",
            review_ref="review.json",
            method="b1_always",
            artifact_digest=ZERO,
        )
    )
    review = issue_review(
        source_repo,
        target_repo,
        workspace,
        plan,
        output_ref="review.json",
        review_id="review",
        operator="tool-owned fixture",
        reason="reviewed sources and mapping",
        source_interface="value_return",
        target_interface="stdout_write",
    )
    session = StudySession(source_repo, target_repo, workspace, review.artifact_digest)
    calls = []

    def transport(argv, *, cwd, **kwargs):
        manifest = json.loads(base64.urlsafe_b64decode(argv[-1]))
        sandbox = Path(next(v for v in argv if v.startswith("type=bind")).split(",")[1][4:])
        raw = (sandbox / manifest["test_ref"]).read_bytes()
        parsed = ast.parse(raw)
        node = next(
            n for n in parsed.body if isinstance(n, ast.Assign) and n.targets[0].id == "CASES"
        )
        cases = json.loads(ast.literal_eval(node.value.args[0]))
        own_witness = b"BoundedObserver" in raw
        suite = ET.Element("testsuite")
        for case in cases:
            n = ET.SubElement(
                suite, "testcase", name="test_guard_case[case-" + case["case_id"][5:] + "]"
            )
            if not own_witness:
                ET.SubElement(n, "failure", message="AssertionError")
        calls.append(
            {
                "argv": argv,
                "manifest": manifest,
                "files": sorted(
                    p.relative_to(sandbox).as_posix() for p in sandbox.rglob("*") if p.is_file()
                ),
            }
        )
        return docker._BoundedProcessResult(
            0,
            canonical_json_bytes(
                {
                    "schema_version": "docker-runner-response.v1",
                    "pytest_exit_code": 0 if own_witness else 1,
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
    monkeypatch.setattr(replay_module, "_docker_executable", lambda: "docker")
    monkeypatch.setattr(replay_module, "_require_image_identity", lambda *a: None)
    return session, plan, calls, target_files, contract, mapping, source, target


def test_source_and_target_keep_distinct_authority_and_minimal_cases(study):
    session, plan, calls, _, contract, mapping, source, _ = study
    result = session.replay(plan, Path("r1"))
    assert result.outcome == "test_failed" and len(result.run.case_results) == 1
    assert len(contract.cases) == 2 and len(mapping.cases) == 1
    assert session.verify(Path("r1/result.json")) == result
    assert len(calls) == 1
    assert calls[0]["manifest"]["import_root"] == "src"
    assert calls[0]["files"] == [
        "cg_control/contract.json",
        "cg_control/test_capture.py",
        "src/other/__init__.py",
        "src/other/core.py",
    ]
    original = json.loads((session.workspace / "r1/w/cg_control/contract.json").read_bytes())
    assert original["target_module"] == contract.target_module != "other.core"
    auth = json.loads((session.workspace / "r1/w/authorization.json").read_bytes())
    assert auth["schema_version"] == "docker-execution-authorization.v6"
    assert auth["source_head"] == H and auth["target_revision"] == T
    assert len({p["origin"] for p in auth["input_origins"]}) == 2
    for old in [StandaloneAuthorization, StandaloneGuardAuthorization]:
        with pytest.raises(ValidationError) as error:
            old.model_validate_json(json.dumps(auth))
        assert any(item["loc"] == ("schema_version",) for item in error.value.errors())
    assert source.case_ids == tuple(c.case_id for c in mapping.cases)
    with pytest.raises(ArtifactIntegrityError):
        session.replay(plan, Path("r1"))


def test_stdout_witness_is_independent_and_not_a_compliance_label(study):
    session, plan, calls, *_ = study
    plan = _seal(plan.model_copy(update={"lane": "witness"}))
    result = session.replay(plan, Path("own"))
    assert result.outcome == "passed" and session.verify(Path("own/result.json")) == result
    assert len(calls) == 1
    assert "contract_compliant" not in result.model_dump()


@pytest.mark.parametrize(
    "method,decision",
    [
        ("b2_interface", "inapplicable"),
        ("learned_initial", "unknown"),
        ("learned_refined", "unknown"),
    ],
)
def test_nonapplicable_and_unknown_never_discover_or_start_docker(
    study, monkeypatch, method, decision
):
    session, plan, calls, *_ = study
    monkeypatch.setattr(
        replay_module, "_docker_executable", lambda: pytest.fail("skip discovered Docker")
    )
    plan = _seal(plan.model_copy(update={"method": method}))
    result = session.replay(plan, Path("skip"))
    assert result.admission.decision == decision
    assert result.outcome == "skipped_" + decision and result.run is None and not calls
    assert session.verify(Path("skip/result.json")) == result
    assert replay_exit_code(result) == (4 if decision == "unknown" else 0)


@pytest.mark.parametrize(
    "file,field,value",
    [
        ("s.json", "assertion_head", "f" * 40),
        ("s.json", "guard_digest", ZERO),
        ("t.json", "assessment_digest", ZERO),
        ("t.json", "revision", "f" * 40),
        ("m.json", "source_digest", ZERO),
        ("m.json", "target_digest", ZERO),
        ("review.json", "policy_digest", ZERO),
        ("review.json", "implementation_digests", {}),
        ("review.json", "target_interface", "value_return"),
        ("w.json", "map_digest", ZERO),
    ],
)
def test_resigned_input_cannot_authorize_an_unreviewed_subject(study, file, field, value):
    session, plan, calls, *_ = study
    resign(session.workspace / file, lambda x: x.__setitem__(field, value))
    result = session.replay(plan, Path("bad"))
    assert result.integrity == "invalid" and result.run is None and not calls
    assert replay_exit_code(result) == 5
    with pytest.raises((ArtifactIntegrityError, ValueError)):
        session.verify(Path("bad/result.json"))


@pytest.mark.parametrize("attack", ["source", "test", "authorization", "record", "result", "junit"])
def test_replay_independently_rebuilds_execution_and_original_logs(study, attack):
    session, plan, calls, *_ = study
    value = session.replay(plan, Path("r"))
    if attack == "source":
        (session.workspace / "r/w/src/other/core.py").write_bytes(b"def clamp(x): return x\n")
    elif attack == "test":
        p = session.workspace / "r/w/cg_control/test_capture.py"
        p.write_bytes(p.read_bytes() + b"\n# changed\n")
    elif attack == "junit":
        (session.workspace / "r/w" / value.run.junit_ref).write_bytes(b"<testsuite/>")
    else:
        p = {
            "authorization": "r/w/authorization.json",
            "record": "r/w/r/record.json",
            "result": "r/result.json",
        }[attack]
        resign(
            session.workspace / p,
            lambda x: x.__setitem__(
                "outcome" if attack != "authorization" else "image_digest",
                "passed" if attack != "authorization" else ZERO,
            ),
        )
    with pytest.raises((ArtifactIntegrityError, ValueError)):
        session.verify(Path("r/result.json"))
    assert len(calls) == 1


def test_late_target_change_preserves_actual_run_and_marks_stale(study, monkeypatch):
    session, plan, calls, files, *_ = study
    transport = docker._run_bounded

    def mutate(*a, **kw):
        result = transport(*a, **kw)
        files["src/other/core.py"] += b"\n# changed during execution\n"
        return result

    monkeypatch.setattr(docker, "_run_bounded", mutate)
    result = session.replay(plan, Path("late"))
    assert result.integrity == "stale" and result.run is not None and len(calls) == 1
    assert (session.workspace / result.record_ref).is_file()
    assert replay_exit_code(result) == 5


def test_twenty_map_orderings_are_deterministic_and_cannot_add_passed_case(study):
    _, _, _, _, contract, mapping, source, target = study
    rows = list(mapping.cases)
    for seed in range(20):
        random.Random(seed).shuffle(rows)
        assert make_call_map(source, target, contract, map_id="map", cases=rows) == mapping
    extra = next(c for c in contract.cases if c.case_id not in source.case_ids)
    rows.append(
        StudyCaseMap(
            case_id=extra.case_id,
            source_assertion_digest=extra.assertion_digest,
            keyword_renames={},
        )
    )
    with pytest.raises(ArtifactIntegrityError):
        make_call_map(source, target, contract, map_id="map", cases=rows)


def test_review_withdrawal_requires_new_anchor_and_remains_append_only(study):
    session, plan, calls, *_ = study
    original = (session.workspace / "review.json").read_bytes()
    withdrawn = issue_review(
        session.source_repo,
        session.target_repo,
        session.workspace,
        plan,
        output_ref="withdraw.json",
        review_id="withdraw",
        operator="fixture",
        reason="withdraw fixture approval",
        source_interface="value_return",
        target_interface="stdout_write",
        previous_ref=plan.review_ref,
        previous_anchor=session.review_anchor,
        action="withdraw",
    )
    new_plan = _seal(plan.model_copy(update={"review_ref": "withdraw.json"}))
    assert session.replay(new_plan, Path("old-anchor")).integrity == "invalid"
    newer = replace(session, review_anchor=withdrawn.artifact_digest)
    result = newer.replay(new_plan, Path("withdrawn"))
    assert result.outcome == "skipped_unknown" and result.run is None and not calls
    assert newer.verify(Path("withdrawn/result.json")) == result
    assert (session.workspace / "review.json").read_bytes() == original


def test_unknown_extra_execution_or_oracle_fields_are_rejected(study):
    _, plan, _, _, _, mapping, *_ = study
    for model, value in [
        (StudyReplayPlan, plan.model_dump(mode="json")),
        (StudyCallMap, mapping.model_dump(mode="json")),
    ]:
        for field in ["applicable", "oracle", "python_code", "execution_allowed"]:
            changed = copy.deepcopy(value)
            changed[field] = True
            with pytest.raises(ValidationError):
                model.model_validate_json(json.dumps(changed))
    with pytest.raises(ValidationError):
        StudyAuthorization.model_validate({"schema_version": "docker-execution-authorization.v5"})


@pytest.mark.parametrize("field,value", [("policy_digest", ZERO), ("implementation_digests", {})])
def test_even_trusted_review_cannot_override_current_policy_or_code(study, field, value):
    session, plan, calls, *_ = study
    path = session.workspace / "review.json"
    resign(path, lambda x: x.__setitem__(field, value))
    anchor = json.loads(path.read_bytes())["artifact_digest"]
    session = replace(session, review_anchor=anchor)
    result = session.replay(plan, Path("invalid-trusted-review"))
    assert result.integrity == "invalid" and result.run is None and not calls


def test_unresolved_target_has_no_execution_override(study, monkeypatch):
    session, plan, calls, files, *_ = study
    files["src/other/__init__.py"] = b"def __getattr__(name): return 1\n"
    monkeypatch.setattr(
        replay_module, "_docker_executable", lambda: pytest.fail("unknown discovered Docker")
    )
    result = session.replay(plan, Path("unknown-target"))
    assert result.outcome == "skipped_unknown" and result.run is None and not calls
