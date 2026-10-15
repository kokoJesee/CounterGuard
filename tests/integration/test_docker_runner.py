"""Real Docker attacks for the closed W3-B execution profile."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from evidenceguard.change_analysis import InspectionReport, TargetImpact, inspect_repository
from evidenceguard.digests import digest_file, digest_json_artifact
from evidenceguard.execution import PytestRunRequest
from evidenceguard.models import RunOutcome, RunRole, TargetRef
from evidenceguard.project_config import load_project_config
from evidenceguard.repository import FilePin
from evidenceguard.runners.docker import DockerExecutor, authorize_docker_execution
from tests.repository_support import git

pytestmark = [pytest.mark.slow, pytest.mark.docker]


def _image_digest() -> str:
    value = os.environ.get("EVIDENCEGUARD_RUNNER_IMAGE_DIGEST")
    if not value:
        pytest.skip("set EVIDENCEGUARD_RUNNER_IMAGE_DIGEST to run real Docker attacks")
    return value


def _workspace(tmp_path: Path, test_body: str, *, timeout: float = 5.0):
    source = tmp_path / "src/pricing.py"
    contract = tmp_path / "contracts/price.json"
    test = tmp_path / "guards/test_guard.py"
    config = tmp_path / "evidenceguard.yaml"
    for path in (source, contract, test):
        path.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def price(value):\n    return value\n", encoding="utf-8")
    contract.write_text('{"contract_id":"price-v1"}\n', encoding="utf-8")
    test.write_text(test_body, encoding="utf-8")
    config.write_text(
        json.dumps(
            {
                "schema_version": "project-config.v1",
                "project_id": "docker-fixture",
                "targets": [
                    {
                        "target_id": "pricing",
                        "guard_id": "grd_price",
                        "source_ref": "src/pricing.py",
                        "module": "src.pricing",
                        "symbol": "price",
                        "contract_ref": "contracts/price.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _, config_digest = load_project_config(config)
    report = InspectionReport(
        project_id="docker-fixture",
        status="ready",
        reason_codes=(),
        requested_base="HEAD~1",
        requested_head="HEAD",
        base_commit="a" * 40,
        head_commit="b" * 40,
        shallow=False,
        git_version="git version fixture",
        config_digest=config_digest,
        implementation_digests={},
        changes=(),
        files=(
            FilePin(
                revision="head",
                path="contracts/price.json",
                object_id="c" * 40,
                content_digest=digest_file(contract),
            ),
            FilePin(
                revision="head",
                path="src/pricing.py",
                object_id="d" * 40,
                content_digest=digest_file(source),
            ),
        ),
        unmapped_paths=(),
        targets=(
            TargetImpact(
                target_id="pricing",
                guard_id="grd_price",
                source_ref="src/pricing.py",
                symbol="price",
                impact="affected",
                changed_inputs=("src/pricing.py",),
            ),
        ),
        artifact_digest="sha256:" + "0" * 64,
    )
    report = report.model_copy(update={"artifact_digest": digest_json_artifact(report)})
    request = PytestRunRequest(
        role=RunRole.REPLAY,
        contract_id="price-v1",
        contract_digest=digest_file(contract),
        target=TargetRef(module="src.pricing", symbol="price", source_ref="src/pricing.py"),
        target_digest=digest_file(source),
        test_path=test,
        known_case_ids=("docker-case",),
        cwd=tmp_path,
        artifact_root=Path("artifacts/w3b"),
        timeout_seconds=timeout,
        contract_path=contract,
    )
    authorization = authorize_docker_execution(
        report,
        config_path=config,
        target_id="pricing",
        request=request,
        image_digest=_image_digest(),
        require_current_implementation=False,
    )
    executor = DockerExecutor(
        authorization=authorization,
        inspection_report=report,
        config_path=config,
        docker_executable=shutil.which("docker"),
        require_current_implementation=False,
    )
    return executor, request


def test_real_container_enforces_identity_filesystem_network_and_cgroups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVIDENCEGUARD_SHOULD_NOT_LEAK", "host-secret")
    body = r'''
import os
import socket
from pathlib import Path

import pytest


@pytest.mark.parametrize("case", [pytest.param(1, id="docker-case")])
def test_isolation(case):
    assert case == 1
    assert os.getuid() == 65532 and os.getgid() == 65532
    assert os.environ.get("EVIDENCEGUARD_SHOULD_NOT_LEAK") is None
    assert Path.cwd() == Path("/workspace")
    assert not Path("/workspace/evidenceguard.yaml").exists()
    assert not Path("/workspace/conftest.py").exists()
    assert not Path("/workspace/pytest.ini").exists()
    with pytest.raises(OSError):
        Path("/workspace/escape.txt").write_text("blocked")
    with pytest.raises(OSError):
        Path("/root-escape.txt").write_text("blocked")
    temporary = Path(os.environ["TMPDIR"]) / "allowed.txt"
    temporary.write_text("ok")
    assert temporary.read_text() == "ok"

    status = Path("/proc/self/status").read_text()
    assert "CapEff:\t0000000000000000" in status
    assert "NoNewPrivs:\t1" in status
    assert int(Path("/sys/fs/cgroup/pids.max").read_text()) <= 64
    assert int(Path("/sys/fs/cgroup/memory.max").read_text()) <= 268435456
    quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    assert quota != "max" and int(quota) / int(period) <= 1.0

    sock = socket.socket()
    sock.settimeout(0.2)
    with pytest.raises(OSError):
        sock.connect(("1.1.1.1", 9))
'''
    executor, request = _workspace(tmp_path, body)
    (tmp_path / "conftest.py").write_text("raise RuntimeError('must not load')\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts=-p missing_plugin\n")

    record = executor.execute(request)

    assert record.outcome is RunOutcome.PASSED
    assert record.pytest_exit_code == 0
    assert "--network=none" in record.argv
    assert "--read-only" in record.argv
    assert "--cap-drop=ALL" in record.argv
    assert not (tmp_path / "escape.txt").exists()


def test_real_inspection_requires_separate_authorization_before_docker_replay(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "EvidenceGuard fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / "src").mkdir()
    (repo / "contracts").mkdir()
    source = repo / "src/pricing.py"
    contract = repo / "contracts/price.json"
    source.write_text("def price(value):\n    return value\n", encoding="utf-8")
    contract.write_text('{"contract_id":"price-v1"}\n', encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    source.write_text("def price(value):\n    return value + 1\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "head")
    head = git(repo, "rev-parse", "HEAD")

    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "project-config.v1",
                "project_id": "real-bridge",
                "targets": [
                    {
                        "target_id": "pricing",
                        "guard_id": "grd_price",
                        "source_ref": "src/pricing.py",
                        "module": "src.pricing",
                        "symbol": "price",
                        "contract_ref": "contracts/price.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    test = repo / "guards/test_guard.py"
    test.parent.mkdir()
    test.write_text(
        """\
import pytest
from src.pricing import price

@pytest.mark.parametrize("case", [pytest.param(1, id="docker-case")])
def test_price(case):
    assert price(case) == 2
""",
        encoding="utf-8",
    )
    report = inspect_repository(repo, base, head, config)
    assert report.status == "ready" and report.execution_allowed is False
    request = PytestRunRequest(
        role=RunRole.REPLAY,
        contract_id="price-v1",
        contract_digest=digest_file(contract),
        target=TargetRef(module="src.pricing", symbol="price", source_ref="src/pricing.py"),
        target_digest=digest_file(source),
        test_path=test,
        known_case_ids=("docker-case",),
        cwd=repo,
        artifact_root=Path("artifacts/w3b"),
        timeout_seconds=5.0,
        contract_path=contract,
    )
    authorization = authorize_docker_execution(
        report,
        config_path=config,
        target_id="pricing",
        request=request,
        image_digest=_image_digest(),
    )

    record = DockerExecutor(
        authorization=authorization,
        inspection_report=report,
        config_path=config,
        docker_executable=shutil.which("docker"),
    ).execute(request)

    assert record.outcome is RunOutcome.PASSED
    assert authorization.inspection_digest == report.artifact_digest


def test_timeout_kills_detached_descendants_and_removes_container(tmp_path: Path) -> None:
    body = r'''
import subprocess
import sys
import time

import pytest


@pytest.mark.parametrize("case", [pytest.param(1, id="docker-case")])
def test_timeout(case):
    subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    time.sleep(60)
'''
    executor, request = _workspace(tmp_path, body, timeout=1.0)

    record = executor.execute(request)

    assert record.outcome is RunOutcome.TIMEOUT
    docker = shutil.which("docker")
    remaining = subprocess.run(
        [docker, "ps", "-a", "--filter", "name=evidenceguard-w3b-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    assert not remaining.stdout.strip()


def test_log_flood_is_bounded_and_cannot_be_reported_as_pass(tmp_path: Path) -> None:
    body = r'''
import os

import pytest


@pytest.mark.parametrize("case", [pytest.param(1, id="docker-case")])
def test_flood(case):
    os.write(1, b"x" * (2 * 1024 * 1024))
    assert case == 1
'''
    executor, request = _workspace(tmp_path, body)

    record = executor.execute(request)

    assert record.outcome is RunOutcome.PROCESS_ERROR
    assert record.error_detail == "stdout_limit_exceeded"
    assert (tmp_path / record.stdout_ref).stat().st_size <= 1024 * 1024
