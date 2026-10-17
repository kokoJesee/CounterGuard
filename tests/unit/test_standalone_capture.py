"""Real admission/materialization with a bounded in-process Docker transport double."""

import base64
import importlib
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from typer.testing import CliRunner

from counterguard.bootstrap_binding import bind_contract, prepare_contract
from counterguard.cli import app
from counterguard.contract_draft import project_test
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import RunRole
from counterguard.runners import docker
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.standalone_capture import (
    StandaloneDockerExecutor,
    authorize_standalone,
    capture_standalone,
    standalone_capture_exit_code,
    verify_standalone_evidence,
)
from counterguard.standalone_contracts import read_standalone_contract
from counterguard.standalone_models import StandaloneCapture
from counterguard.standalone_test import render_standalone_test, runtime_case_id
from tests.unit.test_bootstrap_binding import REF, B, F, H
from tests.unit.test_bootstrap_binding import repository as repository

capture_module = importlib.import_module("counterguard.standalone_capture")
binding_module = importlib.import_module("counterguard.bootstrap_binding")


@pytest.fixture
def capture_inputs(repository, monkeypatch, tmp_path):
    repo, trees, _ = repository
    trees[B]["sample/core.py"] = b"def price(x): return x+1 if x == 0 else x\n"
    trees[F]["tests/test_price.py"] = (
        b"from sample.core import price\n"
        b"def test_price():\n assert price(0) == 1\n assert price(1) == 2\n"
    )
    prepare_contract(
        repo,
        buggy=B,
        fixed=F,
        contract_id="price.v2",
        target="sample.core:price",
        import_root=".",
        test_ref="tests/test_price.py",
        test_function="test_price",
        output=Path("prepared-capture"),
    )
    trees[H] = {**trees[F], REF: Path("prepared-capture/contract.json").read_bytes()}
    bind_contract(repo, H, REF, output=Path("source"))
    monkeypatch.setattr(capture_module, "read_committed_files", binding_module.read_committed_files)
    monkeypatch.setattr(capture_module, "_docker_executable", lambda: "docker")
    monkeypatch.setattr(capture_module, "_require_image_identity", lambda *args: None)

    def forbidden_local(*args, **kwargs):
        pytest.fail("standalone capture reached a local executor")

    monkeypatch.setattr(LocalTrustedExecutor, "execute", forbidden_local)
    contract = read_standalone_contract(trees[H][REF])
    fail_id = next(case.case_id for case in contract.cases if case.positional_args[0].value == 1)
    calls = []

    def transport(argv, *, cwd, **kwargs):
        assert argv[1] == "run"
        manifest = json.loads(base64.urlsafe_b64decode(argv[-1]))
        assert manifest["import_root"] == "."
        mount = next(arg for arg in argv if arg.startswith("type=bind"))
        sandbox = Path(mount.split(",")[1].removeprefix("src="))
        files = sorted(
            path.relative_to(sandbox).as_posix() for path in sandbox.rglob("*") if path.is_file()
        )
        calls.append({"role": cwd.name, "files": files, "argv": argv})
        suite = ET.Element("testsuite")
        for case in contract.cases:
            node = ET.SubElement(
                suite,
                "testcase",
                name=f"test_guard_case[{runtime_case_id(case.case_id)}]",
                classname="cg_control.test_capture",
            )
            if cwd.name == "b" and case.case_id == fail_id:
                ET.SubElement(node, "failure", message="assert 1 == 2").text = "AssertionError"
        envelope = {
            "schema_version": "docker-runner-response.v1",
            "pytest_exit_code": 1 if cwd.name == "b" else 0,
            "timed_out": False,
            "error_code": None,
            "junit_produced": True,
            "stdout_b64": "",
            "stderr_b64": "",
            "junit_b64": base64.b64encode(ET.tostring(suite)).decode(),
            "python_version": "3.13.16",
            "pytest_version": "8.4.2",
        }
        return docker._BoundedProcessResult(0, canonical_json_bytes(envelope), b"", False, False)

    monkeypatch.setattr(docker, "_run_bounded", transport)
    return repo, trees, contract, fail_id, calls, tmp_path


def run_capture(repo, name="capture"):
    return capture_standalone(
        repo,
        Path("source/binding.json"),
        runner_id="root-pytest8",
        evidence_id="evd_" + name,
        review_reason="reviewed fixture sources and oracles",
        output=Path(name),
    )


def resign(path, mutate):
    value = json.loads(path.read_bytes())
    mutate(value)
    value["artifact_digest"] = digest_json_artifact(value)
    path.write_bytes(canonical_json_bytes(value))


def test_canonical_test_preserves_all_oracles_literal_types_and_never_evaluates_strings(
    capture_inputs, monkeypatch
):
    _, _, contract, _, _, _ = capture_inputs
    source = b"""import pytest
from sample.core import price
def test_price():
 assert price(1) == 1
 assert price(1) != 2
 assert price(None) is None
 assert price(False) is not True
 assert price([1])
 assert not price([])
 assert price((b'x', {'a': [1, None]})) == (b'x', {'a': [1, None]})
 assert price("__import__('os').abort()") == "__import__('os').abort()"
 with pytest.raises(ValueError): price('bad')
"""
    cases = project_test(
        source, test_function="test_price", target_module="sample.core", target_symbol="price"
    )["cases"]
    value = contract.model_copy(update={"cases": cases})
    module = ModuleType("sample.core")

    def identity(value):
        if value == "bad":
            raise ValueError("expected")
        return value

    module.price = identity
    monkeypatch.setitem(sys.modules, "sample.core", module)
    monkeypatch.setenv("COUNTERGUARD_TARGET", "sample.core")
    monkeypatch.setenv("COUNTERGUARD_SYMBOL", "price")
    namespace = {}
    exec(compile(render_standalone_test(value), "<trusted generated fixture>", "exec"), namespace)
    for case in namespace["CASES"]:
        namespace["test_guard_case"](case)
    assert render_standalone_test(value) == render_standalone_test(value)


def test_capture_is_minimal_docker_only_and_independently_verifiable(capture_inputs):
    repo, _, contract, fail_id, calls, root = capture_inputs
    value = run_capture(repo)
    assert value["schema_version"] == "evidence.v4" and value["reproduced"]
    assert value["failing_case_ids"] == [fail_id] and len(contract.cases) == 2
    assert [item["role"] for item in calls] == ["b", "f"]
    assert all(
        item["files"]
        == [
            "cg_control/contract.json",
            "cg_control/test_capture.py",
            "sample/__init__.py",
            "sample/core.py",
        ]
        for item in calls
    )
    assert verify_standalone_evidence(repo, Path("capture/evidence.json")).reproduced
    assert standalone_capture_exit_code(value) == 0
    assert len(calls) == 2  # Verification has not launched Docker.
    for role in ("buggy", "fixed"):
        auth = json.loads((root / value[role]["authorization_ref"]).read_bytes())
        assert set(auth["case_id_map"]) == {case.case_id for case in contract.cases}
    with pytest.raises(ArtifactIntegrityError, match="Output exists"):
        run_capture(repo)


@pytest.mark.parametrize(
    "field,changed",
    [
        ("reproduced", False),
        ("failing_case_ids", []),
        ("contract_digest", "sha256:" + "0" * 64),
        ("rejection_reasons", ["invented"]),
    ],
)
def test_re_signed_evidence_cannot_change_derived_claims(capture_inputs, field, changed):
    repo, _, _, _, _, _ = capture_inputs
    run_capture(repo)
    path = Path("capture/evidence.json")
    resign(path, lambda value: value.__setitem__(field, changed))
    with pytest.raises(ArtifactIntegrityError):
        verify_standalone_evidence(repo, path)


@pytest.mark.parametrize(
    "attack", ["authorization", "test", "source", "junit", "argv", "run_identity"]
)
def test_independent_verifier_rejects_re_signed_or_mutated_inputs(capture_inputs, attack):
    repo, _, _, _, _, root = capture_inputs
    value = run_capture(repo)
    if attack == "authorization":
        resign(
            root / value["buggy"]["authorization_ref"],
            lambda item: item.__setitem__("image_digest", "sha256:" + "0" * 64),
        )
    elif attack in {"test", "source"}:
        path = (
            root
            / "capture/b"
            / ("cg_control/test_capture.py" if attack == "test" else "sample/core.py")
        )
        path.write_bytes(path.read_bytes() + b"\n# modified\n")
    elif attack == "junit":
        path = root / "capture/b" / value["buggy"]["run"]["junit_ref"]
        path.write_bytes(b"<testsuite/>")
    else:
        evidence = Path("capture/evidence.json")
        record = root / value["buggy"]["record_ref"]
        changed = json.loads(record.read_bytes())
        if attack == "argv":
            changed["argv"].insert(2, "--privileged")
        else:
            changed["target"]["symbol"] = "unreviewed"
        record.write_bytes(canonical_json_bytes(changed))
        resign(evidence, lambda item: item["buggy"].__setitem__("run", changed))
    with pytest.raises(ArtifactIntegrityError):
        verify_standalone_evidence(repo, Path("capture/evidence.json"))


def test_unknown_is_not_integrity_failure_and_does_not_inspect_or_run_docker(
    capture_inputs, monkeypatch
):
    repo, trees, _, _, calls, _ = capture_inputs
    monkeypatch.setattr(
        capture_module, "_docker_executable", lambda: pytest.fail("unknown inspected Docker")
    )
    for revision in (B, F, H):
        trees[revision]["sample/__init__.py"] = b"import importlib\n"
    bind_contract(repo, H, REF, output=Path("unknown"))
    value = capture_standalone(
        repo,
        Path("unknown/binding.json"),
        runner_id="root-pytest8",
        evidence_id="evd_unknown",
        review_reason="cannot override unknown",
        output=Path("refused"),
    )
    assert value["exit_code"] == 4 and value["reason_code"] == "capture_inputs_require_resolution"
    assert not calls and value["completed_record_refs"] == []
    assert not Path("refused/b").exists()


def test_unavailable_docker_is_retained_without_a_local_fallback(capture_inputs, monkeypatch):
    repo, _, _, _, calls, _ = capture_inputs

    def unavailable(*args):
        raise OSError("unavailable")

    monkeypatch.setattr(capture_module, "_require_image_identity", unavailable)
    value = run_capture(repo)
    assert value["exit_code"] == 3 and not value["reproduced"] and not calls
    assert Path("capture/capture-failure.json").is_file()


def test_role_request_policy_and_post_run_mutation_are_checked(capture_inputs):
    repo, _, _, _, _, root = capture_inputs
    run_capture(repo)
    plan = capture_module._model(root, "capture/capture.json", StandaloneCapture)
    source, contract = capture_module._binding(repo, root / "source/binding.json")
    original = json.loads(Path("capture/evidence.json").read_bytes())
    request = capture_module._request(
        plan, source, contract, root, RunRole.BUGGY, run_id=original["buggy"]["run"]["run_id"]
    )
    auth = authorize_standalone(repo, root, "capture/capture.json", request)
    for altered in (
        replace(request, role=RunRole.REPLAY),
        replace(request, timeout_seconds=31),
        replace(request, known_case_ids=request.known_case_ids[:1]),
    ):
        with pytest.raises(ArtifactIntegrityError):
            authorize_standalone(repo, root, "capture/capture.json", altered)
    weak = docker.DockerPolicyV1().model_copy(update={"network_mode": "bridge"})
    with pytest.raises(ArtifactIntegrityError, match="policy_mismatch"):
        StandaloneDockerExecutor(auth, repo, root, "capture/capture.json", weak).verify(request)


def test_cli_capture_and_verify_preserve_success_status(capture_inputs):
    repo, _, _, _, _, _ = capture_inputs
    result = CliRunner().invoke(
        app,
        [
            "bootstrap",
            "capture",
            "--repo",
            str(repo),
            "--binding",
            "source/binding.json",
            "--runner-id",
            "root-pytest8",
            "--evidence-id",
            "evd_cli",
            "--review-reason",
            "reviewed fixture",
            "--output",
            "cli",
        ],
    )
    assert result.exit_code == 0, result.output
    verify = CliRunner().invoke(
        app, ["bootstrap", "verify-evidence", "cli/evidence.json", "--repo", str(repo)]
    )
    assert verify.exit_code == 0 and json.loads(verify.stdout)["reproduced"]


@pytest.mark.parametrize("late", [False, True])
def test_post_run_mutation_keeps_actual_records_and_never_publishes_success(
    capture_inputs,
    monkeypatch,
    late,
):
    repo, _, _, _, calls, root = capture_inputs
    original = docker._run_bounded

    def mutate(argv, *, cwd, **kwargs):
        response = original(argv, cwd=cwd, **kwargs)
        if cwd.name == ("f" if late else "b"):
            target = root / "capture/b/sample/core.py"
            target.write_bytes(target.read_bytes() + b"\n# changed after actual transport\n")
        return response

    monkeypatch.setattr(docker, "_run_bounded", mutate)
    value = run_capture(repo)
    assert value["exit_code"] == 5 and not value["reproduced"]
    assert len(calls) == (2 if late else 1)
    assert len(value["completed_record_refs"]) == (2 if late else 1)
    assert Path("capture/b/r/record.json").exists()
    assert not Path("capture/evidence.json").exists()


@pytest.mark.parametrize("mode", ["buggy_pass", "fixed_fail"])
def test_real_domain_nonreproduction_is_distinct_from_infrastructure_failure(
    capture_inputs,
    monkeypatch,
    mode,
):
    repo, _, _, _, _, _ = capture_inputs
    original = docker._run_bounded

    def changed(argv, *, cwd, **kwargs):
        response = original(argv, cwd=cwd, **kwargs)
        if (mode == "buggy_pass" and cwd.name == "b") or (mode == "fixed_fail" and cwd.name == "f"):
            payload = json.loads(response.stdout)
            suite = ET.fromstring(base64.b64decode(payload["junit_b64"]))
            for failure in list(suite.iter("failure")):
                for testcase in suite:
                    if failure in list(testcase):
                        testcase.remove(failure)
            if mode == "fixed_fail":
                ET.SubElement(suite[0], "failure", message="assertion failed")
            payload["pytest_exit_code"] = 1 if mode == "fixed_fail" else 0
            payload["junit_b64"] = base64.b64encode(ET.tostring(suite)).decode()
            response = replace(response, stdout=canonical_json_bytes(payload))
        return response

    monkeypatch.setattr(docker, "_run_bounded", changed)
    value = run_capture(repo)
    assert value["schema_version"] == "evidence.v4" and not value["reproduced"]
    assert standalone_capture_exit_code(value) == 1
    assert not verify_standalone_evidence(repo, Path("capture/evidence.json")).reproduced
