"""Fast literal/model guarantees; no Git process, Docker discovery or target import."""

import ast
import json
import random
from pathlib import Path

import pytest
from pydantic import ValidationError

from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.runners.docker import ExecutionInputPin
from counterguard.standalone_capture import ZERO, _seal
from counterguard.standalone_contracts import read_standalone_contract
from counterguard.study_data import check_mapping, make_call_map
from counterguard.study_models import (
    StdoutWitnessCase,
    StudyCallMap,
    StudyCaseMap,
    StudyReplayPlan,
    StudySource,
    StudyTarget,
    StudyWitness,
)
from counterguard.study_test import render_study_test


@pytest.fixture
def literals():
    path = (
        Path(__file__).resolve().parents[2]
        / "docs/results/static-reexport-v1/termcolor-contract.json"
    )
    contract = read_standalone_contract(path.read_bytes())
    source = _seal(
        StudySource(
            source_id="source",
            repository_identity_digest=ZERO,
            guard_ref="g/guard.json",
            guard_digest=ZERO,
            evidence_digest=ZERO,
            binding_digest=ZERO,
            buggy_commit=contract.buggy_commit,
            fixed_commit=contract.fixed_commit,
            assertion_head="c" * 40,
            contract_ref="contracts/source.json",
            contract_digest=ZERO,
            case_ids=tuple(c.case_id for c in contract.cases),
            artifact_digest=ZERO,
        )
    )
    pins = tuple(
        ExecutionInputPin(path=p, object_id="e" * 40, content_digest=ZERO)
        for p in ["LICENSE", "src/other/__init__.py"]
    )
    target = _seal(
        StudyTarget(
            target_id="target",
            repository_identity_digest=ZERO,
            revision="e" * 40,
            module="other",
            symbol="clamp",
            import_root="src",
            profile="static-reexport-v2",
            source_ref="src/other/__init__.py",
            license_ref="LICENSE",
            tree_pins=pins,
            closure_pins=pins[1:],
            assessment_digest=ZERO,
            artifact_digest=ZERO,
        )
    )
    names = {"color": "fore_rgb", "on_color": "back_rgb"}
    rows = [
        StudyCaseMap(
            case_id=c.case_id,
            source_assertion_digest=c.assertion_digest,
            keyword_renames={k.name: names[k.name] for k in c.keyword_args if k.name in names},
            source_only_keywords=("force_color",),
        )
        for c in contract.cases
    ]
    return contract, source, target, rows


def test_twenty_real_case_shuffles_preserve_literals_oracles_and_digests(literals):
    contract, source, target, rows = literals
    mapping = make_call_map(source, target, contract, map_id="map", cases=rows)
    for seed in range(20):
        random.Random(seed).shuffle(rows)
        assert make_call_map(source, target, contract, map_id="map", cases=rows) == mapping
    mapped = check_mapping(source, target, mapping, contract)
    for original, current in zip(contract.cases, mapped, strict=True):
        assert original.positional_args == current.positional_args
        assert original.exception_match == current.exception_match
        assert original.exception == current.exception and original.oracle == current.oracle
        assert current.keyword_args[0].literal == next(
            k.literal for k in original.keyword_args if k.name != "force_color"
        )
        assert current.keyword_args[0].name in {"fore_rgb", "back_rgb"}
    rendered = render_study_test(contract, target, mapped)
    tree = ast.parse(rendered)
    assert any(
        isinstance(n, ast.Assign)
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "TARGET"
        for n in tree.body
    )
    cases_node = next(
        n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "CASES"
    )
    payload = json.loads(ast.literal_eval(cases_node.value.args[0]))
    assert len(payload) == 8
    assert all(c["exception_match"] == "Expected a tuple of 3 ints in range 0-255" for c in payload)


@pytest.mark.parametrize(
    "attack",
    [
        "drop",
        "duplicate",
        "assertion",
        "missing_keyword",
        "false_control",
        "source_digest",
        "target_digest",
    ],
)
def test_resigned_literal_map_still_has_to_match_source(literals, attack):
    contract, source, target, rows = literals
    if attack == "drop":
        rows.pop()
    elif attack == "duplicate":
        rows[-1] = rows[0]
    elif attack == "assertion":
        rows[0] = rows[0].model_copy(update={"source_assertion_digest": ZERO})
    elif attack == "missing_keyword":
        rows[0] = rows[0].model_copy(update={"keyword_renames": {}})
    elif attack == "false_control":
        case = contract.cases[0]
        keywords = tuple(
            k.model_copy(update={"literal": k.literal.model_copy(update={"value": False})})
            if k.name == "force_color"
            else k
            for k in case.keyword_args
        )
        contract = contract.model_copy(
            update={
                "cases": (case.model_copy(update={"keyword_args": keywords}), *contract.cases[1:])
            }
        )
    mapping = None
    with pytest.raises((ArtifactIntegrityError, ValueError)):
        mapping = make_call_map(source, target, contract, map_id="map", cases=rows)
        if attack in {"source_digest", "target_digest"}:
            changed = _seal(mapping.model_copy(update={attack: ZERO}))
            check_mapping(source, target, changed, contract)


@pytest.mark.parametrize(
    "extra", ["applicable", "oracle", "python_code", "execution_allowed", "target_args"]
)
def test_callers_cannot_supply_an_oracle_or_execution_decision(literals, extra):
    contract, source, target, rows = literals
    mapping = make_call_map(source, target, contract, map_id="map", cases=rows)
    value = mapping.model_dump(mode="json")
    value[extra] = True
    with pytest.raises(ValidationError):
        StudyCallMap.model_validate_json(json.dumps(value))
    plan = _seal(
        StudyReplayPlan(
            source_ref="s",
            target_ref="t",
            map_ref="m",
            review_ref="r",
            method="b1_always",
            artifact_digest=ZERO,
        )
    )
    value = plan.model_dump(mode="json")
    value[extra] = True
    with pytest.raises(ValidationError):
        StudyReplayPlan.model_validate_json(json.dumps(value))


@pytest.mark.parametrize("attack", ["duplicate", "closure_pin", "missing_license", "absolute_path"])
def test_target_pins_are_closed_and_paths_cannot_escape(literals, attack):
    _, _, target, _ = literals
    value = target.model_dump(mode="json")
    if attack == "duplicate":
        value["tree_pins"].append(value["tree_pins"][-1])
    elif attack == "closure_pin":
        value["closure_pins"][0]["content_digest"] = "sha256:" + "f" * 64
    elif attack == "missing_license":
        value["license_ref"] = "NOTFOUND"
    else:
        value["source_ref"] = "../escape.py"
    with pytest.raises(ValidationError):
        StudyTarget.model_validate_json(json.dumps(value))


def test_stdout_witness_renders_separately_and_bounds_observer(literals):
    contract, source, target, rows = literals
    before = canonical_json_bytes(contract)
    mapping = make_call_map(source, target, contract, map_id="map", cases=rows)
    mapped = check_mapping(source, target, mapping, contract)
    witness = _seal(
        StudyWitness(
            target_digest=target.artifact_digest,
            map_digest=mapping.artifact_digest,
            basis_refs=("LICENSE",),
            cases=(StdoutWitnessCase(case_id=rows[0].case_id, stdout="text\n"),),
            artifact_digest=ZERO,
        )
    )
    rendered = render_study_test(contract, target, mapped, witness)
    assert b"with pytest.raises" not in rendered
    assert b"BoundedObserver" in rendered and b"returncode=3" in rendered
    assert b"8192" in rendered
    tree = ast.parse(rendered)
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "CASES")
    assert len(json.loads(ast.literal_eval(node.value.args[0]))) == 1
    assert canonical_json_bytes(contract) == before
    with pytest.raises(ValidationError):
        StdoutWitnessCase(case_id=rows[0].case_id, stdout="x" * 4097)


def test_cli_missing_inputs_are_sanitized_and_do_not_launch_processes(
    tmp_path, monkeypatch, capsys
):
    import subprocess

    from scripts.run_scope_study import main

    def forbidden(*args, **kwargs):
        pytest.fail("invalid research input launched a process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    command = [
        "audit",
        "--workspace",
        str(tmp_path),
        "--source-repo",
        str(tmp_path),
        "--target-repo",
        str(tmp_path),
        "--review-digest",
        ZERO,
        "--plan",
        str(tmp_path / "private-missing-plan"),
    ]
    assert main(command) == 5
    value = capsys.readouterr().out
    assert "private-missing-plan" not in value and str(tmp_path) not in value
    assert json.loads(value)["reason_code"] == "study_input_invalid"
    with pytest.raises(SystemExit) as error:
        main([*command, "--approve"])
    assert error.value.code == 2


def test_deep_json_is_a_finite_failure_without_traceback_or_process(tmp_path, monkeypatch, capsys):
    import subprocess
    import sys

    from counterguard.study_replay import StudySession
    from scripts.run_scope_study import main

    def forbidden(*args, **kwargs):
        pytest.fail("malformed JSON launched a process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    depth = sys.getrecursionlimit() + 100
    (tmp_path / "deep.json").write_bytes(b'{"x":' + b"[" * depth + b"0" + b"]" * depth + b"}")
    assert (
        main(
            [
                "audit",
                "--workspace",
                str(tmp_path),
                "--source-repo",
                str(tmp_path),
                "--target-repo",
                str(tmp_path),
                "--review-digest",
                ZERO,
                "--plan",
                "deep.json",
            ]
        )
        == 5
    )
    output = capsys.readouterr().out
    assert "Traceback" not in output and str(tmp_path) not in output
    source_repo, target_repo = tmp_path / "source", tmp_path / "target"
    source_repo.mkdir()
    target_repo.mkdir()
    session = StudySession(source_repo, target_repo, tmp_path, ZERO)
    plan = _seal(
        StudyReplayPlan(
            source_ref="deep.json",
            target_ref="t.json",
            map_ref="m.json",
            review_ref="r.json",
            method="b1_always",
            artifact_digest=ZERO,
        )
    )
    result = session.replay(plan, Path("invalid-json"))
    assert result.integrity == "invalid" and result.run is None
