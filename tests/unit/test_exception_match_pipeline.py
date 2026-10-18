"""Exercise the new chain with an in-process transport double, never a real target."""

import ast
import base64
import importlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from counterguard.bootstrap_binding import bind_contract
from counterguard.digests import canonical_json_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.lifecycle import GuardState
from counterguard.registry import Registry, RegistryEntry, StandaloneRegistryEntry
from counterguard.runners import docker
from counterguard.runners.local import LocalTrustedExecutor
from counterguard.standalone_capture import capture_standalone, verify_standalone_evidence
from counterguard.standalone_guard import compile_standalone_guard, verify_standalone_guard
from tests.unit.test_bootstrap_binding import REF, B, H
from tests.unit.test_bootstrap_binding import repository as repository
from tests.unit.test_exception_match import matched_contract as matched_contract


def test_versioned_match_chain_independent_rebuild_minimal_guard_and_registry(
    matched_contract, monkeypatch, tmp_path
):
    repo, trees, _, _, contract = matched_contract
    binding_module = importlib.import_module("counterguard.bootstrap_binding")
    capture_module = importlib.import_module("counterguard.standalone_capture")
    guard_module = importlib.import_module("counterguard.standalone_guard")
    monkeypatch.setattr(capture_module, "read_committed_files", binding_module.read_committed_files)
    for module in [capture_module, guard_module]:
        monkeypatch.setattr(module, "_docker_executable", lambda: "docker")
        monkeypatch.setattr(module, "_require_image_identity", lambda *args: None)

    def forbidden(*args, **kwargs):
        pytest.fail("candidate reached local executor")

    monkeypatch.setattr(LocalTrustedExecutor, "execute", forbidden)
    calls = []

    def transport(argv, *, cwd, **kwargs):
        manifest = json.loads(base64.urlsafe_b64decode(argv[-1]))
        mount = next(value for value in argv if value.startswith("type=bind"))
        sandbox = Path(mount.split(",")[1][4:])
        generated = (sandbox / manifest["test_ref"]).read_bytes()
        parsed = ast.parse(generated)
        assignment = next(
            node
            for node in parsed.body
            if isinstance(node, ast.Assign) and node.targets[0].id == "CASES"
        )
        cases = json.loads(ast.literal_eval(assignment.value.args[0]))
        assert cases[0]["exception_match"] == "invalid value"
        buggy = (sandbox / contract.source_ref).read_bytes() == trees[B][contract.source_ref]
        suite = ET.Element("testsuite")
        for case in cases:
            item = ET.SubElement(
                suite, "testcase", name="test_guard_case[case-" + case["case_id"][5:] + "]"
            )
            if buggy:
                ET.SubElement(item, "failure", message="message mismatch")
        calls.append((generated, tuple(x["case_id"] for x in cases)))
        return docker._BoundedProcessResult(
            0,
            canonical_json_bytes(
                {
                    "schema_version": "docker-runner-response.v1",
                    "pytest_exit_code": int(buggy),
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
    bind_contract(repo, H, REF, output=Path("pipeline-binding"))
    evidence = capture_standalone(
        repo,
        Path("pipeline-binding/binding.json"),
        runner_id="root-pytest8",
        evidence_id="evd_match_unit",
        review_reason="reviewed test double",
        output=Path("c"),
    )
    assert evidence["reproduced"]
    assert verify_standalone_evidence(repo, Path("c/evidence.json")).reproduced
    guard = compile_standalone_guard(
        repo,
        Path("c/evidence.json"),
        guard_id="grd_match_unit",
        review_reason="reviewed test double",
        output=Path("g"),
    )
    assert guard.schema_version == "guard.v4" and guard.generator_version.endswith("v2")
    assert verify_standalone_guard(repo, Path("g/guard.json")) == guard
    assert len(calls) == 4 and all(b"exception_match" in data for data, _ in calls)
    registry = Registry(tmp_path / "registry")
    entry = registry.add(Path("g/guard.json"), cwd=tmp_path, repo=repo)
    assert entry.schema_version == "registry-entry.v4"
    for old in [RegistryEntry, StandaloneRegistryEntry]:
        with pytest.raises(ValueError):
            old.model_validate_json(canonical_json_bytes(entry))
    assert registry.add(Path("g/guard.json"), cwd=tmp_path, repo=repo) == entry
    registry.transition(guard.guard_id, to=GuardState.SHADOW, reason="reviewed fixture")
    assert registry.resolve_for_verification(guard.guard_id).guard == guard
    # A re-signed textual oracle change still cannot replace the head-committed projection.
    changed = json.loads(trees[H][REF])
    changed["cases"][0]["exception_match"] = "weakened"
    trees[H][REF] = canonical_json_bytes(changed)
    with pytest.raises((ArtifactIntegrityError, ValueError)):
        registry.resolve_for_verification(guard.guard_id)
