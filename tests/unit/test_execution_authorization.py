"""Docker execution requires a separate, digest-bound authorization artifact."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from counterguard.change_analysis import (
    InspectionReport,
    TargetImpact,
    inspection_implementation_digests,
)
from counterguard.digests import digest_file, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError, GuardReplayIntegrityError
from counterguard.execution import PytestRunRequest
from counterguard.models import RunRole, TargetRef
from counterguard.project_config import load_project_config
from counterguard.repository import FilePin
from counterguard.runners.docker import (
    DockerExecutionAuthorization,
    DockerExecutor,
    DockerPolicyV1,
    authorize_docker_execution,
    verify_docker_authorization,
)
from tests.unit.test_project_config import mapping, project

IMAGE_DIGEST = "sha256:" + "d" * 64


def _inputs(workspace: Path) -> tuple[Path, Path, Path, Path]:
    source = workspace / "src/pricing.py"
    contract = workspace / "contracts/price.json"
    test = workspace / "guards/test_price.py"
    config = workspace / "counterguard.yaml"
    for path in (source, contract, test):
        path.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def price(value):\n    return value\n", encoding="utf-8")
    contract.write_text('{"contract_id":"price-v1"}\n', encoding="utf-8")
    test.write_text("def test_price():\n    assert True\n", encoding="utf-8")
    config.write_text(
        json.dumps(project(targets=[mapping(module="src.pricing")])),
        encoding="utf-8",
    )
    return source, contract, test, config


def _request(workspace: Path, source: Path, contract: Path, test: Path) -> PytestRunRequest:
    return PytestRunRequest(
        role=RunRole.REPLAY,
        contract_id="price-v1",
        contract_digest=digest_file(contract),
        target=TargetRef(module="src.pricing", symbol="price", source_ref="src/pricing.py"),
        target_digest=digest_file(source),
        test_path=test,
        known_case_ids=("price-case",),
        cwd=workspace,
        artifact_root=Path("artifacts/w3b"),
        timeout_seconds=2.0,
        contract_path=contract,
    )


def _report(workspace: Path, config: Path, *, status: str = "ready") -> InspectionReport:
    _, config_digest = load_project_config(config)
    source = workspace / "src/pricing.py"
    contract = workspace / "contracts/price.json"
    reasons = () if status == "ready" else ("unmapped_changed_paths",)
    impact = "affected" if status == "ready" else "unknown"
    report = InspectionReport(
        project_id="fixture",
        status=status,
        reason_codes=reasons,
        requested_base="HEAD~1",
        requested_head="HEAD",
        base_commit="a" * 40,
        head_commit="b" * 40,
        shallow=False,
        git_version="git version test",
        config_digest=config_digest,
        implementation_digests={},
        changes=(),
        files=(
            FilePin(
                revision="head",
                path="src/pricing.py",
                object_id="c" * 40,
                content_digest=digest_file(source),
            ),
            FilePin(
                revision="head",
                path="contracts/price.json",
                object_id="d" * 40,
                content_digest=digest_file(contract),
            ),
        ),
        unmapped_paths=(),
        targets=(
            TargetImpact(
                target_id="pricing",
                guard_id="grd_price",
                source_ref="src/pricing.py",
                symbol="price",
                impact=impact,
                changed_inputs=("src/pricing.py",) if status == "ready" else (),
                reason_codes=reasons,
            ),
        ),
        artifact_digest="sha256:" + "0" * 64,
    )
    return report.model_copy(update={"artifact_digest": digest_json_artifact(report)})


def test_ready_report_is_still_not_an_execution_switch(tmp_path: Path) -> None:
    source, contract, test, config = _inputs(tmp_path)
    report = _report(tmp_path, config)
    request = _request(tmp_path, source, contract, test)

    authorization = authorize_docker_execution(
        report,
        config_path=config,
        target_id="pricing",
        request=request,
        image_digest=IMAGE_DIGEST,
        require_current_implementation=False,
    )

    assert report.execution_allowed is False
    assert authorization.backend == "docker"
    assert authorization.inspection_digest == report.artifact_digest
    assert authorization.test_digest == digest_file(test)
    assert authorization.policy_digest == digest_json_artifact(DockerPolicyV1())
    assert (
        verify_docker_authorization(
            authorization,
            report=report,
            config_path=config,
            request=request,
            require_current_implementation=False,
        )
        is authorization
    )


def test_docker_authorization_requires_an_explicit_module_mapping(tmp_path: Path) -> None:
    source, contract, test, config = _inputs(tmp_path)
    config.write_text(json.dumps(project()), encoding="utf-8")

    with pytest.raises(ValueError, match="explicit matching module"):
        authorize_docker_execution(
            _report(tmp_path, config),
            config_path=config,
            target_id="pricing",
            request=_request(tmp_path, source, contract, test),
            image_digest=IMAGE_DIGEST,
            require_current_implementation=False,
        )


@pytest.mark.parametrize("status", ["unknown", "rejected"])
def test_uncertain_or_rejected_inspection_cannot_authorize_execution(
    tmp_path: Path, status: str
) -> None:
    source, contract, test, config = _inputs(tmp_path)
    with pytest.raises(ValueError, match="ready inspection"):
        authorize_docker_execution(
            _report(tmp_path, config, status=status),
            config_path=config,
            target_id="pricing",
            request=_request(tmp_path, source, contract, test),
            image_digest=IMAGE_DIGEST,
            require_current_implementation=False,
        )


def test_authorization_rejects_changed_inputs_and_resigned_claims(tmp_path: Path) -> None:
    source, contract, test, config = _inputs(tmp_path)
    request = _request(tmp_path, source, contract, test)
    authorization = authorize_docker_execution(
        _report(tmp_path, config),
        config_path=config,
        target_id="pricing",
        request=request,
        image_digest=IMAGE_DIGEST,
        require_current_implementation=False,
    )

    source.write_text("def price(value):\n    return value + 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="request or workspace"):
        verify_docker_authorization(
            authorization,
            report=_report(tmp_path, config),
            config_path=config,
            request=request,
            require_current_implementation=False,
        )

    source.write_text("def price(value):\n    return value\n", encoding="utf-8")
    payload = authorization.model_dump(mode="json")
    payload["target_id"] = "other"
    payload["artifact_digest"] = digest_json_artifact(payload)
    forged = DockerExecutionAuthorization.model_validate_json(json.dumps(payload))
    with pytest.raises(ValueError, match="request or workspace"):
        verify_docker_authorization(
            forged,
            report=_report(tmp_path, config),
            config_path=config,
            request=request,
            require_current_implementation=False,
        )


def test_policy_is_a_closed_profile_not_a_user_tunable_switch() -> None:
    schema = DockerPolicyV1.model_json_schema()["properties"]
    assert schema["network_mode"]["const"] == "none"
    assert schema["workspace_mode"]["const"] == "read_only"
    assert schema["run_as"]["const"] == "65532:65532"
    assert schema["cap_drop"]["const"] == "ALL"
    assert schema["no_new_privileges"]["const"] is True
    with pytest.raises(ValueError):
        DockerPolicyV1(network_mode="bridge")


def test_execution_admission_requires_the_current_inspector_implementation(
    tmp_path: Path,
) -> None:
    source, contract, test, config = _inputs(tmp_path)
    report = _report(tmp_path, config).model_copy(
        update={"implementation_digests": inspection_implementation_digests()}
    )
    report = report.model_copy(update={"artifact_digest": digest_json_artifact(report)})

    authorization = authorize_docker_execution(
        report,
        config_path=config,
        target_id="pricing",
        request=_request(tmp_path, source, contract, test),
        image_digest=IMAGE_DIGEST,
    )
    assert authorization.inspection_digest == report.artifact_digest

    stale = report.model_copy(
        update={"implementation_digests": {"change_analysis.py": "sha256:" + "0" * 64}}
    )
    stale = stale.model_copy(update={"artifact_digest": digest_json_artifact(stale)})
    with pytest.raises(ArtifactIntegrityError, match="different CounterGuard implementation"):
        authorize_docker_execution(
            stale,
            config_path=config,
            target_id="pricing",
            request=_request(tmp_path, source, contract, test),
            image_digest=IMAGE_DIGEST,
        )


def test_missing_pinned_image_fails_before_outputs_without_local_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, contract, test, config = _inputs(tmp_path)
    report = _report(tmp_path, config)
    request = _request(tmp_path, source, contract, test)
    authorization = authorize_docker_execution(
        report,
        config_path=config,
        target_id="pricing",
        request=request,
        image_digest=IMAGE_DIGEST,
        require_current_implementation=False,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Docker failure must never fall back to local pytest")

    def missing_image(*_args, **_kwargs):
        raise OSError("Pinned Docker runner image is unavailable")

    monkeypatch.setattr("counterguard.runners.local.LocalTrustedExecutor.execute", forbidden)
    monkeypatch.setattr(
        "counterguard.runners.docker._require_image_identity",
        missing_image,
    )
    executor = DockerExecutor(
        authorization=authorization,
        inspection_report=report,
        config_path=config,
        docker_executable=str(tmp_path / "missing-docker"),
        require_current_implementation=False,
    )
    with pytest.raises(OSError, match="Pinned Docker runner image"):
        executor.execute(request)
    assert not (tmp_path / "artifacts").exists()


def test_post_execution_revalidation_preserves_run_and_rejects_changed_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, contract, test, config = _inputs(tmp_path)
    report = _report(tmp_path, config)
    request = _request(tmp_path, source, contract, test)
    authorization = authorize_docker_execution(
        report,
        config_path=config,
        target_id="pricing",
        request=request,
        image_digest=IMAGE_DIGEST,
        require_current_implementation=False,
    )
    preserved_run = object()

    def execute_then_change(*_args, **_kwargs):
        source.write_text("def price(value):\n    return value + 1\n", encoding="utf-8")
        return preserved_run

    monkeypatch.setattr("counterguard.runners.docker._require_image_identity", lambda *_: None)
    monkeypatch.setattr("counterguard.execution._execute_with_adapter", execute_then_change)
    executor = DockerExecutor(
        authorization=authorization,
        inspection_report=report,
        config_path=config,
        docker_executable="docker",
        require_current_implementation=False,
    )

    with pytest.raises(GuardReplayIntegrityError) as raised:
        executor.execute(request)
    assert raised.value.run is preserved_run
