"""Exercise real provenance gates and Docker materialization without a child process."""

import ast
import base64
import importlib
import json
import random
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from counterguard.change_analysis import InspectionReport, TargetImpact
from counterguard.cli import app
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError, GuardSelfCheckError, InvalidEvidenceError
from counterguard.github_report import project_github_report
from counterguard.lifecycle import GuardState
from counterguard.models import RunRole
from counterguard.registry import Registry
from counterguard.runners import docker
from counterguard.standalone_guard import (
    authorize_self_check,
    compilation_sources,
    compile_standalone_guard,
    render_minimal_test,
    snapshot_scope,
    verify_standalone_guard,
)
from counterguard.standalone_test import runtime_case_id
from counterguard.verify import VerifyRequest, verify_repository
from tests.unit.test_bootstrap_binding import REF, B, H, pins
from tests.unit.test_bootstrap_binding import repository as repository
from tests.unit.test_standalone_capture import capture_inputs as capture_inputs
from tests.unit.test_standalone_capture import resign, run_capture

guard_module = importlib.import_module("counterguard.standalone_guard")
replay_module = importlib.import_module("counterguard.standalone_replay")
verify_module = importlib.import_module("counterguard.verify")
binding_module = importlib.import_module("counterguard.bootstrap_binding")
J = "d" * 40


@pytest.fixture
def guard_inputs(capture_inputs, monkeypatch):
    repo, trees, contract, fail_id, calls, workspace = capture_inputs
    assert run_capture(repo)["reproduced"]
    monkeypatch.setattr(guard_module, "_docker_executable", lambda: "docker")
    monkeypatch.setattr(guard_module, "_require_image_identity", lambda *args: None)
    monkeypatch.setattr(replay_module, "read_committed_files", binding_module.read_committed_files)
    outcome = ["normal"]

    def transport(argv, *, cwd, **kwargs):
        manifest = json.loads(base64.urlsafe_b64decode(argv[-1]))
        mount = next(value for value in argv if value.startswith("type=bind"))
        sandbox = Path(mount.split(",")[1][4:])
        parsed = ast.parse((sandbox / manifest["test_ref"]).read_bytes())
        assignment = next(
            node
            for node in parsed.body
            if isinstance(node, ast.Assign) and node.targets[0].id == "CASES"
        )
        cases = json.loads(ast.literal_eval(assignment.value.args[0]))
        source = (sandbox / contract.source_ref).read_bytes()
        buggy = b"else x" in source
        suite = ET.Element("testsuite")
        failed = False
        for case in cases:
            node = ET.SubElement(
                suite, "testcase", name="test_guard_case[" + runtime_case_id(case["case_id"]) + "]"
            )
            if (buggy and case["case_id"] == fail_id) or outcome[0] == "fixed_fail":
                ET.SubElement(node, "failure", message="assertion")
                failed = True
        payload = {
            "schema_version": "docker-runner-response.v1",
            "pytest_exit_code": int(failed),
            "timed_out": False,
            "error_code": None,
            "junit_produced": True,
            "stdout_b64": "",
            "stderr_b64": "",
            "junit_b64": base64.b64encode(ET.tostring(suite)).decode(),
            "python_version": "3.13.16",
            "pytest_version": "8.4.2",
        }
        calls.append({"cwd": cwd, "case_ids": tuple(case["case_id"] for case in cases)})
        return docker._BoundedProcessResult(0, canonical_json_bytes(payload), b"", False, False)

    monkeypatch.setattr(docker, "_run_bounded", transport)
    return repo, trees, contract, fail_id, calls, workspace, outcome


def compile_fixture(repo):
    return compile_standalone_guard(
        repo,
        Path("capture/evidence.json"),
        guard_id="grd_price_v1",
        review_reason="reviewed independent oracles and exact snapshots",
        output=Path("g"),
    )


def test_minimal_compile_independent_rebuild_and_registry_lifecycle(guard_inputs):
    repo, _, contract, fail_id, calls, workspace, _ = guard_inputs
    guard = compile_fixture(repo)
    assert guard.case_ids == (fail_id,) and len(contract.cases) == 2
    assert calls[-2]["case_ids"] == calls[-1]["case_ids"] == (fail_id,)
    assert verify_standalone_guard(repo, Path("g/guard.json")) == guard
    registry = Registry(workspace / "registry")
    with pytest.raises(ValueError, match="--repo"):
        registry.add(Path("g/guard.json"), cwd=workspace)
    entry = registry.add(Path("g/guard.json"), cwd=workspace, repo=repo)
    assert entry.schema_version == "registry-entry.v3"
    assert registry.add(Path("g/guard.json"), cwd=workspace, repo=repo) == entry
    assert not registry.show(guard.guard_id)["verification_schedulable"]
    registry.transition(guard.guard_id, to=GuardState.SHADOW, reason="scope review")
    assert registry.resolve_for_verification(guard.guard_id).lifecycle_state is GuardState.SHADOW
    registry.disable(guard.guard_id, reason="stop")
    with pytest.raises(ArtifactIntegrityError):
        registry.resolve_for_verification(guard.guard_id)


@pytest.mark.parametrize("field", ["cases", "scope", "test", "run", "authorization"])
def test_resigned_guard_and_upstream_corruption_cannot_claim_verified(guard_inputs, field):
    repo, _, _, _, _, _, _ = guard_inputs
    compile_fixture(repo)
    if field == "cases":
        resign(Path("g/guard.json"), lambda value: value.update(case_ids=[]))
    elif field == "scope":
        resign(Path("g/scope.json"), lambda value: value["snapshots"].update(buggy={}))
    elif field == "test":
        Path("g/test_guard.py").write_bytes(
            Path("g/test_guard.py").read_bytes() + b"\nassert True\n"
        )
    elif field == "run":
        resign(
            Path("g/guard.json"), lambda value: value["buggy_check"]["run"].update(case_results=[])
        )
    else:
        resign(
            Path("g/b/authorization.json"),
            lambda value: value.update(purpose="standalone_registry_replay"),
        )
    with pytest.raises((ArtifactIntegrityError, ValueError)):
        verify_standalone_guard(repo, Path("g/guard.json"))


def test_fixed_self_check_failure_keeps_records_and_does_not_publish_guard(guard_inputs):
    repo, _, _, _, _, _, mode = guard_inputs
    mode[0] = "fixed_fail"
    with pytest.raises(GuardSelfCheckError):
        compile_fixture(repo)
    assert Path("g/f/r/record.json").exists() and Path("g/compilation-failure.json").exists()
    assert not Path("g/guard.json").exists()


def test_nonreproduced_evidence_is_not_compile_authority(guard_inputs, monkeypatch):
    repo, _, _, _, _, _, _ = guard_inputs
    original = guard_module.verify_standalone_evidence
    monkeypatch.setattr(
        guard_module,
        "verify_standalone_evidence",
        lambda *args, **kwargs: original(*args, **kwargs).model_copy(update={"reproduced": False}),
    )
    with pytest.raises(InvalidEvidenceError):
        compile_fixture(repo)
    assert not Path("g").exists()


def test_case_order_scope_and_test_are_deterministic_for_twenty_shuffles(guard_inputs):
    repo, _, contract, _, _, workspace, _ = guard_inputs
    compile_fixture(repo)
    plan, evidence, _, binding, _ = compilation_sources(repo, workspace, "g/compilation.json")
    expected = snapshot_scope(plan, evidence, binding, contract)
    expected_test = render_minimal_test(contract, evidence.failing_case_ids)
    for seed in range(20):
        shuffled = list(binding["runtime_assessments"]["buggy"]["files"])
        random.Random(seed).shuffle(shuffled)
        binding["runtime_assessments"]["buggy"]["files"] = shuffled
        assert snapshot_scope(plan, evidence, binding, contract) == expected
        assert (
            render_minimal_test(contract, tuple(sorted(evidence.failing_case_ids))) == expected_test
        )


@pytest.fixture
def verified_project(guard_inputs, monkeypatch):
    repo, trees, contract, _, calls, workspace, mode = guard_inputs
    guard = compile_fixture(repo)
    registry = Registry(workspace / "registry")
    registry.add(Path("g/guard.json"), cwd=workspace, repo=repo)
    registry.transition(guard.guard_id, to=GuardState.SHADOW, reason="exact snapshot review")
    trees[J] = {**trees[H], contract.source_ref: trees[B][contract.source_ref]}
    config = workspace / "config.json"
    config.write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "project-config.v2",
                "project_id": "standalone",
                "targets": [
                    {
                        "target_id": "price",
                        "guard_id": guard.guard_id,
                        "module": contract.target_module,
                        "symbol": contract.target_symbol,
                        "source_ref": contract.source_ref,
                        "contract_ref": REF,
                        "dependency_refs": [
                            ref for ref in contract.runtime_refs if ref != contract.source_ref
                        ],
                    }
                ],
            }
        )
    )

    def inspect(repo_arg, base, head, config_path):
        value = InspectionReport(
            project_id="standalone",
            status="ready",
            reason_codes=(),
            requested_base=base,
            requested_head=head,
            base_commit=base,
            head_commit=head,
            shallow=False,
            git_version="git fixture",
            config_digest=digest_bytes(config_path.read_bytes()),
            implementation_digests=verify_module.inspection_implementation_digests(),
            changes=(),
            files=pins(trees[head]),
            unmapped_paths=(),
            targets=(
                TargetImpact(
                    target_id="price",
                    guard_id=guard.guard_id,
                    source_ref=contract.source_ref,
                    symbol=contract.target_symbol,
                    impact="affected",
                    changed_inputs=(contract.source_ref,),
                ),
            ),
            artifact_digest="sha256:" + "0" * 64,
        )
        return value.model_copy(update={"artifact_digest": digest_json_artifact(value)})

    monkeypatch.setattr(verify_module, "inspect_repository", inspect)
    monkeypatch.setattr(replay_module, "inspect_repository", inspect)
    request = VerifyRequest(
        repo, H, J, config, registry.root, Path("v"), cwd=workspace, runner_id="root-pytest8"
    )
    return request, registry, trees, calls, mode


def test_verify_shadow_active_repeat_and_unknown_without_execution(verified_project):
    request, registry, trees, calls, _ = verified_project
    shadow = verify_repository(request)
    assert shadow.schema_version == "verify-report.v3" and shadow.exit_code == 0
    assert shadow.counts["shadow_violations"] == 1, shadow.model_dump_json()
    registry.transition("grd_price_v1", to=GuardState.ACTIVE, reason="accepted replay")
    active = verify_repository(replace(request, output=Path("active")))
    repeated = verify_repository(replace(request, output=Path("repeat")))
    assert active.exit_code == 1 and active.decision_digest == repeated.decision_digest
    assert active.rows[0].run.run_id != repeated.rows[0].run.run_id
    assert active.rows[0].scope_basis == "standalone-snapshot-scope.v1"
    assert project_github_report(active.model_dump(mode="json"))["counts"] == active.counts
    old = len(calls)
    trees[J]["sample/core.py"] += b"\n# unreviewed\n"
    unknown = verify_repository(replace(request, output=Path("unknown")))
    assert unknown.exit_code == 4 and unknown.rows[0].run is None and len(calls) == old


@pytest.mark.parametrize("mode", ["contract", "mapping", "metadata", "mixed_closure"])
def test_scope_refuses_unknown_inputs_and_does_not_launch_docker(verified_project, mode):
    request, _, trees, calls, _ = verified_project
    if mode == "contract":
        trees[J][REF] += b" "
    elif mode == "mapping":
        value = json.loads(request.config.read_bytes())
        value["targets"][0]["dependency_refs"] = []
        request.config.write_bytes(canonical_json_bytes(value))
    elif mode == "metadata":
        trees[J]["pyproject.toml"] = b'[project]\nname="sample"\ndependencies=["external"]\n'
    else:
        trees[J]["sample/__init__.py"] += b"\n# unreviewed dependency\n"
    before = len(calls)
    report = verify_repository(request)
    assert report.exit_code == 4 and report.rows[0].run is None and len(calls) == before


def test_candidate_retired_and_integrity_failures_remain_distinct(verified_project):
    request, registry, _, calls, _ = verified_project
    registry.transition("grd_price_v1", to=GuardState.RETIRED, reason="stop")
    before = len(calls)
    report = verify_repository(request)
    assert report.counts["skipped"] == 1 and len(calls) == before
    Path("g/test_guard.py").write_bytes(b"assert True\n")
    invalid = verify_repository(replace(request, output=Path("invalid")))
    assert invalid.exit_code == 5 and invalid.counts["integrity_error"] == 1


def test_compile_cli_and_self_check_role_rejection(guard_inputs):
    repo, _, _, _, _, workspace, _ = guard_inputs
    response = CliRunner().invoke(
        app,
        [
            "bootstrap",
            "compile",
            "--repo",
            str(repo),
            "--evidence",
            "capture/evidence.json",
            "--guard-id",
            "grd_price_v1",
            "--review-reason",
            "snapshot and oracle review",
            "--output",
            "g",
        ],
    )
    assert response.exit_code == 0, response.output
    result = CliRunner().invoke(
        app, ["bootstrap", "verify-guard", "g/guard.json", "--repo", str(repo)]
    )
    assert result.exit_code == 0, result.output
    guard = verify_standalone_guard(repo, Path("g/guard.json"))
    sources = compilation_sources(repo, workspace, guard.compilation_ref)
    from counterguard.standalone_guard import guard_request

    plan, evidence, capture, binding, contract = sources
    pin = next(
        pin for pin in binding["trees"]["buggy"]["files"] if pin["path"] == contract.source_ref
    )
    request = guard_request(
        workspace / plan.output_ref / "b",
        contract,
        evidence,
        capture,
        pin,
        RunRole.REPLAY,
        "run_" + "f" * 32,
    )
    with pytest.raises(ArtifactIntegrityError, match="role_mismatch"):
        authorize_self_check(repo, workspace, guard.compilation_ref, request)


def test_registry_missing_git_source_is_invalid_instead_of_an_unhandled_error(guard_inputs):
    repo, trees, _, _, _, workspace, _ = guard_inputs
    compile_fixture(repo)
    registry = Registry(workspace / "registry")
    registry.add(Path("g/guard.json"), cwd=workspace, repo=repo)
    del trees[B]
    assert registry.show("grd_price_v1")["integrity"] == "invalid"
    with pytest.raises(ArtifactIntegrityError):
        registry.resolve_for_execution("grd_price_v1")


def test_oversized_guard_is_rejected_before_publication(guard_inputs, monkeypatch):
    repo, _, _, _, _, _, _ = guard_inputs
    original = guard_module.canonical_json_bytes

    def huge(value):
        return (
            b" " * (4 * 1024 * 1024 + 1)
            if getattr(value, "schema_version", None) == "guard.v3"
            else original(value)
        )

    monkeypatch.setattr(guard_module, "canonical_json_bytes", huge)
    with pytest.raises(ArtifactIntegrityError, match="publication_byte_budget"):
        compile_fixture(repo)
    assert not Path("g/guard.json").exists() and Path("g/compilation-failure.json").exists()
