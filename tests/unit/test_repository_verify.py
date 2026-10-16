"""New-runtime replay authorization preserves head contract, minimal cases and pinned inputs."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from counterguard.digests import digest_bytes
from counterguard.errors import ArtifactIntegrityError
from counterguard.execution import PytestRunRequest
from counterguard.models import RunRole, TargetRef
from counterguard.repository_contracts import (
    CONTRACT_REF,
    SOURCE_REF,
    extract_mac_contract,
    render_repository_test,
)
from counterguard.repository_verify import ReviewedRepositoryExecutor, authorize_reviewed_replay
from counterguard.runner_catalog import resolve_runner
from tests.unit.test_repository_pilot import UPSTREAM_TEST


@pytest.fixture
def admission(tmp_path, monkeypatch):
    contract = extract_mac_contract(UPSTREAM_TEST)
    cases = tuple(case for case in contract.cases if case.case_id.endswith("-lf"))
    runtime = tmp_path / "output/work/mac-address"
    test = runtime / "_cg/test_guard.py"
    files = {
        SOURCE_REF: b"def mac_address(value, /): return True\n",
        CONTRACT_REF: b"committed head contract bytes",
    }
    for ref, raw in files.items():
        path = runtime / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    test.parent.mkdir(parents=True)
    test.write_bytes(render_repository_test(contract, tuple(case.case_id for case in cases)))
    guard = SimpleNamespace(
        cases=cases,
        source_fixed_digest=digest_bytes(files[SOURCE_REF]),
        contract_id=contract.contract_id,
        contract_digest=digest_bytes(files[CONTRACT_REF]),
        artifact_digest="sha256:" + "1" * 64,
    )
    verified = SimpleNamespace(
        guard=guard,
        evidence=SimpleNamespace(artifact_digest="sha256:" + "2" * 64),
        entry=SimpleNamespace(artifact_digest="sha256:" + "3" * 64),
    )
    facts = {
        "config": SimpleNamespace(targets=[SimpleNamespace(target_id="mac-address")]),
        "contract": contract,
        "pins": {
            "h": [
                SimpleNamespace(path=ref, object_id="a" * 40, content_digest=digest_bytes(raw))
                for ref, raw in files.items()
            ]
        },
        "runtime_refs": (SOURCE_REF,),
        "manifest": {"artifact_digest": "sha256:" + "4" * 64},
    }
    scope = SimpleNamespace(artifact_digest="sha256:" + "5" * 64)
    inspection = SimpleNamespace(artifact_digest="sha256:" + "6" * 64, head_commit="b" * 40)
    review = resolve_runner(runner_id="validators-pytest9", image_digest=None)
    monkeypatch.setattr(
        "counterguard.repository_verify._admission",
        lambda *args: (
            verified,
            facts,
            scope,
            inspection,
            review,
            {"events": [{"artifact_digest": "sha256:" + "7" * 64}]},
        ),
    )
    host_request = SimpleNamespace(cwd=tmp_path, output=Path("output"))
    request = PytestRunRequest(
        role=RunRole.REPLAY,
        contract_id=guard.contract_id,
        contract_digest=guard.contract_digest,
        target=TargetRef(
            module=contract.target_module, symbol=contract.target_symbol, source_ref=SOURCE_REF
        ),
        target_digest=guard.source_fixed_digest,
        test_path=test,
        known_case_ids=tuple(case.case_id for case in cases),
        cwd=runtime,
        artifact_root=runtime / "a",
        contract_path=runtime / CONTRACT_REF,
    )
    return host_request, request


def test_replay_authorization_is_deterministic_and_pins_head_contract(admission):
    host, request = admission
    first = authorize_reviewed_replay(host, "grd_test", request)
    assert first.import_root == "src"
    assert CONTRACT_REF in {pin.path for pin in first.input_pins}
    assert first.runner_review_digest
    for _ in range(20):
        assert authorize_reviewed_replay(host, "grd_test", request) == first


@pytest.mark.parametrize(
    "field,value",
    [
        ("role", RunRole.BUGGY),
        ("known_case_ids", ("invented",)),
        ("contract_id", "invented"),
        ("timeout_seconds", 31.0),
    ],
)
def test_requests_cannot_expand_historical_replay(admission, field, value):
    host, request = admission
    with pytest.raises(ArtifactIntegrityError):
        authorize_reviewed_replay(host, "grd_test", replace(request, **{field: value}))


@pytest.mark.parametrize("ref", [SOURCE_REF, CONTRACT_REF, "_cg/test_guard.py"])
def test_materialized_source_contract_and_assertions_are_rechecked(admission, ref):
    host, request = admission
    (request.cwd / ref).write_bytes(b"changed")
    with pytest.raises(ArtifactIntegrityError):
        authorize_reviewed_replay(host, "grd_test", request)


def test_request_change_is_rejected_before_docker_start(admission, monkeypatch):
    host, request = admission
    authorization = authorize_reviewed_replay(host, "grd_test", request)
    executor = ReviewedRepositoryExecutor(authorization, host, "grd_test")
    monkeypatch.setattr(
        "counterguard.repository_verify._docker_executable",
        lambda: pytest.fail("Docker must not start for stale authorization"),
    )
    with pytest.raises(ArtifactIntegrityError, match="stale"):
        executor.execute(replace(request, run_id="run_changed"))
