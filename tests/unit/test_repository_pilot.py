"""In-process adversarial checks; no candidate code, Git or Docker is executed."""

import base64
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import ValidationError

from counterguard.digests import canonical_json_bytes, digest_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.execution import PytestRunRequest
from counterguard.models import RunRole, TargetRef
from counterguard.pilot_inputs import ZERO
from counterguard.preflight import inspect_execution_requirements
from counterguard.project_config import ProjectConfig
from counterguard.repository_contracts import (
    CONTRACT_REF,
    SOURCE_REF,
    extract_mac_contract,
    read_contract,
    render_repository_test,
)
from counterguard.runners import repository as runner

UPSTREAM_TEST = b'''"""Upstream parameter/oracle shape, represented as inert test data."""
@pytest.mark.parametrize("validate,value", [
    (mac_address, "01:23:45:67:ab:CD"), (mac_address, "01-23-45-67-ab-CD"),
    (fi_business_id, "0112038-9"), (fi_ssn, "010101-0101"),
    (fr_ssn, "1 84 12 76 451 089 46"), (fr_ssn, "1 84 12 76 451 089"),
    (ind_aadhar, "3675 9834 6015")])
@pytest.mark.parametrize("suffix", ["", "\\n", "\\r\\n", " ", "\\nextra"])
def test_complete_identifier(validate, value, suffix):
    """Same assertions."""
    if suffix:
        assert isinstance(validate(value + suffix), ValidationError)
    else:
        assert validate(value) is True
'''


def test_projection_preserves_every_mac_value_suffix_and_oracle():
    contract = extract_mac_contract(UPSTREAM_TEST)
    assert len(contract.cases) == 10 and contract.upstream_case_count == 35
    assert sum(c.oracle == "is_true" for c in contract.cases) == 2
    assert sum(c.oracle == "validation_error_instance" for c in contract.cases) == 8
    assert {case.positional_args[0] for case in contract.cases} == {
        value + suffix
        for value in ("01:23:45:67:ab:CD", "01-23-45-67-ab-CD")
        for suffix in ("", "\n", "\r\n", " ", "\nextra")
    }
    assert read_contract(canonical_json_bytes(contract)) == contract


@pytest.mark.parametrize(
    "old,new",
    [
        (b" is True", b" == True"),
        (b"isinstance(validate(value + suffix), ValidationError)", b"not validate(value + suffix)"),
        (b'"\\nextra"', b'"extra"'),
        (b"pytest.mark.parametrize", b"unsafe.parametrize"),
        (b"(ind_aadhar,", b"(__import__('os'),"),
    ],
)
def test_projection_refuses_oracle_and_parameter_drift(old, new):
    with pytest.raises(ValueError):
        extract_mac_contract(UPSTREAM_TEST.replace(old, new))


def test_generator_deterministic_and_only_selects_failed_cases():
    contract = extract_mac_contract(UPSTREAM_TEST)
    ids = tuple(case.case_id for case in contract.cases if case.case_id.endswith("-lf"))
    test = render_repository_test(contract, ids)
    assert len(ids) == 2 and b"mac-colons-plain" not in test
    for _ in range(20):
        assert render_repository_test(read_contract(canonical_json_bytes(contract)), ids) == test
    with pytest.raises(ValueError):
        render_repository_test(contract, tuple(reversed(ids)))
    with pytest.raises(ValueError):
        render_repository_test(contract, ("invented",))


@pytest.mark.parametrize(
    "oracle,result,passes",
    [
        ("is_true", True, True),
        ("is_true", 1, False),
        ("is_true", False, False),
        ("validation_error_instance", False, False),
        ("validation_error_instance", None, False),
        ("validation_error_instance", True, False),
    ],
)
def test_generated_oracle_does_not_coerce_truthiness(monkeypatch, oracle, result, passes):
    class ErrorClass(Exception):
        pass

    _invoke_generated(monkeypatch, oracle, result, ErrorClass, passes)


def _invoke_generated(monkeypatch, oracle, result, error_class, passes):
    module, utils = ModuleType("validators.mac_address"), ModuleType("validators.utils")

    def positional_only(value, /):
        assert value == "input"
        return result

    module.mac_address, utils.ValidationError = positional_only, error_class
    monkeypatch.setitem(sys.modules, "validators.mac_address", module)
    monkeypatch.setitem(sys.modules, "validators.utils", utils)
    monkeypatch.setenv("COUNTERGUARD_TARGET", "validators.mac_address")
    monkeypatch.setenv("COUNTERGUARD_SYMBOL", "mac_address")
    namespace = {}
    exec(
        compile(
            render_repository_test(extract_mac_contract(UPSTREAM_TEST)),
            "<trusted-generated-test>",
            "exec",
        ),
        namespace,
    )
    case = {"case_id": "synthetic", "positional_args": ["input"], "oracle": oracle}
    if passes:
        namespace["test_guard_case"](case)
    else:
        with pytest.raises(AssertionError):
            namespace["test_guard_case"](case)


def test_return_class_uses_actual_pinned_class_identity(monkeypatch):
    class Expected(Exception):
        pass

    class Child(Expected):
        pass

    class Other(Exception):
        pass

    _invoke_generated(monkeypatch, "validation_error_instance", Child(), Expected, True)
    _invoke_generated(monkeypatch, "validation_error_instance", Other(), Expected, False)


def _config(version="project-config.v2", root="src"):
    return {
        "schema_version": version,
        "project_id": "pilot",
        "targets": [
            {
                "target_id": "mac",
                "guard_id": "grd_mac",
                "source_ref": SOURCE_REF,
                "module": "validators.mac_address",
                "symbol": "mac_address",
                "contract_ref": CONTRACT_REF,
                "import_root": root,
            }
        ],
        "audit_refs": ["counterguard.yaml"],
    }


def test_import_root_is_explicit_versioned_and_not_an_alias_switch():
    config = ProjectConfig.model_validate_json(json.dumps(_config()))
    assert config.targets[0].import_root == "src"
    for raw in (_config("project-config.v1"), _config(root="../outside")):
        with pytest.raises(ValidationError):
            ProjectConfig.model_validate_json(json.dumps(raw))
    raw = _config()
    raw["targets"][0]["module"] = "unrelated.mac_address"
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate_json(json.dumps(raw))


def test_legacy_config_serialization_does_not_gain_fields():
    raw = _config("project-config.v1")
    del raw["audit_refs"]
    del raw["targets"][0]["import_root"]
    raw["targets"][0]["module"] = "src.validators.mac_address"
    config = ProjectConfig.model_validate_json(json.dumps(raw))
    payload = config.model_dump(mode="json")
    assert "audit_refs" not in payload
    assert "import_root" not in payload["targets"][0]


def test_new_static_profile_does_not_relax_plugin_and_conftest_rejection():
    files = {
        "pyproject.toml": b"""[project]
dependencies=[]
[tool.pytest]
minversion="9.0"
pythonpath=["src"]
[tool.setuptools.packages.find]
where=["src"]
"""
    }
    assert inspect_execution_requirements(files)["status"] == "blocked"
    assert (
        inspect_execution_requirements(files, pytest_version="9.0.3", import_root="src")["status"]
        == "eligible_candidate"
    )
    for ref, body in (
        ("tests/nested/conftest.py", b""),
        ("tests/plugins.py", b"pytest_plugins=['evil']"),
    ):
        result = inspect_execution_requirements(
            {**files, ref: body}, pytest_version="9.0.3", import_root="src"
        )
        assert result["status"] == "blocked"


@pytest.fixture
def admitted_request(tmp_path, monkeypatch):
    contract = extract_mac_contract(UPSTREAM_TEST)
    contract_bytes = canonical_json_bytes(contract)
    source = b"# inert synthetic source; never executed\n"
    trees = {key: {SOURCE_REF: source, CONTRACT_REF: contract_bytes} for key in ("b", "f", "h")}
    for key, files in trees.items():
        for ref, body in files.items():
            path = tmp_path / "ws" / key / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        test = tmp_path / "ws" / key / "t/capture.py"
        test.parent.mkdir()
        test.write_bytes(render_repository_test(contract))
    manifest = {
        "workspace_root_ref": "ws",
        "head_sha": "a" * 40,
        "base_sha": "b" * 40,
        "fixed_sha": "c" * 40,
        "contract_digest": digest_bytes(contract_bytes),
        "artifact_digest": ZERO,
        "image_id": ZERO,
    }
    facts = {
        "manifest": manifest,
        "contract": contract,
        "trees": trees,
        "runtime_refs": (SOURCE_REF,),
        "inspection": SimpleNamespace(artifact_digest=ZERO),
        "implementation_digests": {},
        "pins": {
            key: [
                SimpleNamespace(path=ref, object_id="d" * 40, content_digest=digest_bytes(body))
                for ref, body in files.items()
            ]
            for key, files in trees.items()
        },
    }
    monkeypatch.setattr(runner, "load_inputs", lambda *args: facts)
    runtime = tmp_path / "ws/b"
    request = PytestRunRequest(
        role=RunRole.BUGGY,
        contract_id=contract.contract_id,
        contract_digest=manifest["contract_digest"],
        target=TargetRef(
            module=contract.target_module, symbol=contract.target_symbol, source_ref=SOURCE_REF
        ),
        target_digest=digest_bytes(source),
        test_path=runtime / "t/capture.py",
        known_case_ids=tuple(c.case_id for c in contract.cases),
        cwd=runtime,
        artifact_root=runtime / "a",
        contract_path=runtime / CONTRACT_REF,
        run_id="run_test",
    )
    return tmp_path, tmp_path / "manifest.json", request


def test_authorization_separates_assertion_head_and_historical_target(admitted_request):
    workspace, manifest, request = admitted_request
    auth = runner.authorize_repository_execution(manifest, workspace, request, phase="capture")
    assert auth.assertion_head == "a" * 40 and auth.target_revision == "b" * 40
    assert auth.import_root == "src" and auth.role is RunRole.BUGGY


@pytest.mark.parametrize("mutation", ["cases", "role", "target", "contract", "workspace", "test"])
def test_capture_refuses_misbound_requests_before_any_process(admitted_request, mutation):
    workspace, manifest, request = admitted_request
    if mutation == "cases":
        request = replace(request, known_case_ids=request.known_case_ids[:-1])
    elif mutation == "role":
        request = replace(request, role=RunRole.REPLAY)
    elif mutation == "target":
        request = replace(
            request, target=TargetRef(module="other", symbol="mac_address", source_ref=SOURCE_REF)
        )
    elif mutation == "contract":
        request.contract_path.write_bytes(b"{}")
    elif mutation == "workspace":
        request = replace(request, cwd=workspace / "ws/f")
    else:
        request.test_path.write_bytes(b"# forged passing test")
    with pytest.raises(ArtifactIntegrityError):
        runner.authorize_repository_execution(manifest, workspace, request, phase="capture")


def test_resigned_authorization_does_not_start_docker_or_local(admitted_request, monkeypatch):
    workspace, manifest, request = admitted_request
    auth = runner.authorize_repository_execution(manifest, workspace, request, phase="capture")
    forged = auth.model_copy(update={"image_digest": "sha256:" + "1" * 64})
    from counterguard.digests import digest_json_artifact

    forged = forged.model_copy(update={"artifact_digest": digest_json_artifact(forged)})
    monkeypatch.setattr(runner, "_docker_executable", lambda: pytest.fail("Docker must not start"))
    from counterguard.runners.local import LocalTrustedExecutor

    monkeypatch.setattr(
        LocalTrustedExecutor, "execute", lambda *args: pytest.fail("No local fallback")
    )
    with pytest.raises(ArtifactIntegrityError):
        runner.RepositoryDockerExecutor(forged, manifest, workspace).execute(request)


def test_container_protocol_rejects_arbitrary_import_roots(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "trusted_entrypoint", Path("containers/python-runner/entrypoint.py")
    )
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    monkeypatch.setattr(entry, "WORKSPACE", tmp_path)
    (tmp_path / "test.py").write_bytes(b"")
    (tmp_path / "contract.json").write_bytes(b"{}")
    payload = {
        "schema_version": "docker-runner-request.v2",
        "test_ref": "test.py",
        "contract_ref": "contract.json",
        "target_module": "validators.mac_address",
        "target_symbol": "mac_address",
        "timeout_seconds": 2,
        "stdout_limit_bytes": 100,
        "stderr_limit_bytes": 100,
        "junit_limit_bytes": 100,
        "import_root": "src",
    }

    def encode(value):
        return base64.urlsafe_b64encode(canonical_json_bytes(value)).decode()

    assert entry._request(encode(payload))["import_root"] == "src"
    for root in ("../src", "/usr/lib", "src:evil", "src;evil", None):
        with pytest.raises(ValueError):
            entry._request(encode({**payload, "import_root": root}))
    with pytest.raises(ValueError):
        entry._request(encode({**payload, "schema_version": "docker-runner-request.v1"}))


@pytest.mark.parametrize(
    "field",
    [
        "manifest_digest",
        "guard_digest",
        "contract_digest",
        "source_digest",
        "runtime_closure_digest",
        "head_commit",
    ],
)
def test_explicit_scope_rejects_resigned_bindings(admitted_request, field):
    from counterguard.pilot_inputs import closure_digest, signed
    from counterguard.repository_contracts import ExplicitPilotScope
    from counterguard.repository_guard import verify_pilot_scope

    workspace, manifest_path, request = admitted_request
    facts = runner.load_inputs(manifest_path, workspace)
    scope = ExplicitPilotScope(
        manifest_digest=ZERO,
        guard_digest=ZERO,
        contract_digest=request.contract_digest,
        source_digest=request.target_digest,
        runtime_closure_digest=closure_digest(facts["trees"]["h"], facts["runtime_refs"]),
        head_commit=facts["manifest"]["head_sha"],
        artifact_digest=ZERO,
    ).model_dump(mode="json")
    path = workspace / "scope.json"
    path.write_bytes(canonical_json_bytes(signed(scope)))
    verify_pilot_scope(path, facts, SimpleNamespace(artifact_digest=ZERO))
    scope[field] = "different-head" if field == "head_commit" else "sha256:" + "1" * 64
    path.write_bytes(canonical_json_bytes(signed(scope)))
    with pytest.raises(ArtifactIntegrityError):
        verify_pilot_scope(path, facts, SimpleNamespace(artifact_digest=ZERO))


def test_static_refusal_cannot_be_used_as_execution_proof(tmp_path):
    from counterguard.pilot import verify_pilot_report
    from counterguard.pilot_inputs import signed

    path = tmp_path / "report.json"
    path.write_bytes(
        canonical_json_bytes(
            signed(
                {
                    "schema_version": "pilot-admission-report.v1",
                    "accepted": True,
                    "repository_execution_count": 0,
                }
            )
        )
    )
    with pytest.raises(ArtifactIntegrityError, match="real execution"):
        verify_pilot_report(path, tmp_path)


def test_repeatability_rejects_reusing_one_run(monkeypatch, tmp_path):
    from counterguard import pilot

    report = {
        "schema_version": "pilot-execution-report.v2",
        "accepted": True,
        "guards": [{"run": {"run_id": "run_one"}}],
        "projection": {},
        "artifact_digest": ZERO,
        "projection_digest": ZERO,
    }
    monkeypatch.setattr(pilot, "verify_pilot_report", lambda *args: report)
    with pytest.raises(ArtifactIntegrityError, match="independent run"):
        pilot.compare_replays(tmp_path / "a.json", tmp_path / "a.json")


def test_repeatability_does_not_turn_unknown_into_pass(monkeypatch, tmp_path):
    from counterguard import pilot

    first = {
        "schema_version": "pilot-execution-report.v2",
        "accepted": True,
        "guards": [{"run": {"run_id": "run_one"}}],
        "projection": {"counts": {"skipped_unknown": 1}},
        "artifact_digest": ZERO,
        "projection_digest": ZERO,
    }
    second = {
        **first,
        "guards": [{"run": {"run_id": "run_two"}}],
        "projection": {"counts": {"skipped_unknown": 0, "pass": 1}},
    }
    monkeypatch.setattr(
        pilot, "verify_pilot_report", lambda path, _: first if path.name == "a" else second
    )
    result = pilot.compare_replays(tmp_path / "a", tmp_path / "b")
    assert result["accepted"] is False and result["counts_equal"] is False


def test_run_cwd_dot_is_relative_to_authorized_snapshot(admitted_request, monkeypatch):
    from datetime import UTC, datetime

    from counterguard import repository_guard
    from counterguard.models import CaseOutcome, CaseResult, RunOutcome, RunRecord

    workspace, manifest_path, request = admitted_request
    auth = runner.authorize_repository_execution(manifest_path, workspace, request, phase="capture")
    auth_path = workspace / "authorization.json"
    auth_path.write_bytes(canonical_json_bytes(auth))
    cases = tuple(
        CaseResult(
            case_id=case_id,
            node_id=f"test[{case_id}]",
            outcome=CaseOutcome.FAILED if index == 0 else CaseOutcome.PASSED,
        )
        for index, case_id in enumerate(request.known_case_ids)
    )
    record = RunRecord(
        run_id=request.run_id,
        role=request.role,
        contract_id=request.contract_id,
        contract_digest=request.contract_digest,
        target=request.target,
        target_digest=request.target_digest,
        argv=("docker",),
        cwd=".",
        started_at=datetime.now(UTC),
        duration_ms=0,
        timeout_seconds=request.timeout_seconds,
        pytest_exit_code=1,
        outcome=RunOutcome.TEST_FAILED,
        case_results=cases,
        stdout_ref="a/stdout.txt",
        stdout_digest=ZERO,
        stderr_ref="a/stderr.txt",
        stderr_digest=ZERO,
        junit_ref="a/junit.xml",
        junit_digest=ZERO,
        python_version="synthetic",
        pytest_version="9.0.3",
    )
    monkeypatch.setattr(repository_guard, "authorize_repository_execution", lambda *a, **k: auth)
    checked = []
    monkeypatch.setattr(
        repository_guard, "verify_run_record", lambda *a, **k: checked.append(k["cwd"])
    )
    repository_guard._verify_record(
        record, "authorization.json", manifest_path, workspace, "capture"
    )
    assert checked == [workspace / auth.workspace_ref]
    with pytest.raises(ArtifactIntegrityError):
        repository_guard._verify_record(
            record.model_copy(update={"cwd": "another-snapshot"}),
            "authorization.json",
            manifest_path,
            workspace,
            "capture",
        )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("output_root_ref", "src/counterguard/overwrite"),
        ("output_root_ref", "../outside"),
        ("workspace_root_ref", "artifacts/pilot/other/ws"),
        ("registry_root_ref", ".counterguard"),
        ("scope_ref", "benchmarks/scope.json"),
        ("config_ref", "external-config.json"),
        ("contract_ref", "external-contract.json"),
    ],
)
def test_manifest_cannot_redirect_sources_or_outputs_before_git(tmp_path, field, bad):
    from counterguard.pilot_inputs import TOOL_FILES, load_inputs, signed
    from counterguard.repository_contracts import BASE, FIXED, FORK_URL, UPSTREAM_URL

    value = {
        "schema_version": "pilot-manifest.v2",
        "repository_url": FORK_URL,
        "upstream_url": UPSTREAM_URL,
        "base_sha": BASE,
        "fixed_sha": FIXED,
        "head_sha": "a" * 40,
        "tool_files": list(TOOL_FILES),
        "unknown_is_execution_success": False,
        "repository_ref": "artifacts/pilot/first/repo",
        "output_root_ref": "artifacts/pilot/second",
        "workspace_root_ref": "artifacts/pilot/second/ws",
        "registry_root_ref": "artifacts/pilot/second/registry",
        "scope_ref": "artifacts/pilot/second/scope.json",
        "config_ref": "artifacts/pilot/first/repo/counterguard.yaml",
        "contract_ref": "artifacts/pilot/first/repo/contracts/mac-complete-v2.json",
    }
    value[field] = bad
    path = tmp_path / "manifest.json"
    path.write_bytes(canonical_json_bytes(signed(value)))
    with pytest.raises((ArtifactIntegrityError, ValueError)):
        load_inputs(path, tmp_path)
