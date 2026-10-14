"""Tests for the controlled pytest execution boundary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from evidenceguard.digests import digest_file
from evidenceguard.execution import PytestRunRequest, run_pytest
from evidenceguard.models import (
    CaseOutcome,
    RunOutcome,
    RunRole,
    TargetRef,
)

CONTRACT_DIGEST = "sha256:" + "1" * 64
TARGET_DIGEST = "sha256:" + "2" * 64


def _request(
    workspace: Path,
    *,
    known_case_ids: tuple[str, ...] = ("member-price", "non-member-price"),
    timeout_seconds: float = 30.0,
) -> PytestRunRequest:
    (workspace / "test_contract.py").write_text(
        "# supplied by a fake pytest run\n", encoding="utf-8"
    )
    return PytestRunRequest(
        role=RunRole.BUGGY,
        contract_id="membership-discount-final-price-v1",
        contract_digest=CONTRACT_DIGEST,
        target=TargetRef(
            module="examples.discount.implementations.final_price_v1_buggy",
            symbol="calculate_price",
            source_ref="target.py",
        ),
        target_digest=TARGET_DIGEST,
        test_path=Path("test_contract.py"),
        known_case_ids=known_case_ids,
        cwd=workspace,
        artifact_root=Path("artifacts"),
        timeout_seconds=timeout_seconds,
    )


def _junit(*cases: tuple[str, str | None]) -> str:
    testcases = []
    for name, child in cases:
        nested = "" if child is None else child
        testcases.append(
            f'<testcase classname="tests.test_contract" name="{name}" time="0.001">'
            f"{nested}</testcase>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuites><testsuite tests="{len(cases)}">'
        f"{''.join(testcases)}</testsuite></testsuites>"
    )


def _fake_completed_run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int,
    junit: str | None,
) -> dict[str, Any]:
    call: dict[str, Any] = {}

    def fake_run(argv: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        call["argv"] = argv
        call["kwargs"] = kwargs
        if junit is not None:
            junit_ref = argv[argv.index("--junitxml") + 1]
            junit_path = Path(kwargs["cwd"]) / junit_ref
            junit_path.write_text(junit, encoding="utf-8")
        return subprocess.CompletedProcess(
            argv,
            returncode,
            stdout=b"captured stdout\n",
            stderr=b"captured stderr\n",
        )

    monkeypatch.setattr("evidenceguard.execution.subprocess.run", fake_run)
    return call


def _artifact_path(workspace: Path, artifact_ref: str) -> Path:
    return workspace / Path(artifact_ref)


@pytest.mark.slow
def test_runs_real_pytest_with_fixed_cwd_and_sanitized_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_file = tmp_path / "test_contract.py"
    test_file.write_text(
        """\
import os
from pathlib import Path

import pytest


@pytest.mark.parametrize("value", [pytest.param(1, id="target-case")])
def test_controlled_environment(value: int) -> None:
    assert value == 1
    assert os.environ["EVIDENCEGUARD_TARGET"] == "package.implementation"
    assert os.environ["EVIDENCEGUARD_SYMBOL"] == "target"
    assert "EVIDENCEGUARD_SHOULD_NOT_LEAK" not in os.environ
    assert Path.cwd() == Path(__file__).parent
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("EVIDENCEGUARD_SHOULD_NOT_LEAK", "secret")
    (tmp_path / "conftest.py").write_text("raise RuntimeError('conftest must not load')\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -p missing_project_plugin\n")
    request = PytestRunRequest(
        role=RunRole.REPLAY,
        contract_id="controlled-environment-v1",
        contract_digest=CONTRACT_DIGEST,
        target=TargetRef(
            module="package.implementation",
            symbol="target",
            source_ref="package/implementation.py",
        ),
        target_digest=TARGET_DIGEST,
        test_path=Path("test_contract.py"),
        known_case_ids=("target-case",),
        cwd=tmp_path,
        artifact_root=Path("artifacts"),
    )

    record = run_pytest(request)

    assert record.outcome is RunOutcome.PASSED
    assert record.pytest_exit_code == 0
    assert record.cwd == "."
    assert record.argv[:3] == (sys.executable, "-m", "pytest")
    assert [result.case_id for result in record.case_results] == ["target-case"]
    assert record.case_results[0].outcome is CaseOutcome.PASSED
    assert _artifact_path(tmp_path, record.stdout_ref).is_file()
    assert _artifact_path(tmp_path, record.stderr_ref).is_file()
    assert _artifact_path(tmp_path, record.junit_ref).is_file()
    assert record.stdout_digest == digest_file(_artifact_path(tmp_path, record.stdout_ref))
    assert record.stderr_digest == digest_file(_artifact_path(tmp_path, record.stderr_ref))
    assert record.junit_digest == digest_file(_artifact_path(tmp_path, record.junit_ref))


def test_exit_one_requires_exact_known_case_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    junit = _junit(
        ("test_price[member-price]", None),
        (
            "test_price[non-member-price]",
            '<failure message="assertion failed">expected 100, got 80</failure>',
        ),
    )
    call = _fake_completed_run(monkeypatch, returncode=1, junit=junit)

    record = run_pytest(_request(tmp_path))

    assert record.outcome is RunOutcome.TEST_FAILED
    assert [
        result.case_id for result in record.case_results if result.outcome is CaseOutcome.FAILED
    ] == ["non-member-price"]
    assert call["kwargs"]["shell"] is False
    assert call["kwargs"]["check"] is False
    assert call["kwargs"]["timeout"] == 30.0
    assert call["kwargs"]["cwd"] == tmp_path.resolve()
    assert call["kwargs"]["env"]["EVIDENCEGUARD_TARGET"].endswith("final_price_v1_buggy")
    assert call["kwargs"]["env"]["EVIDENCEGUARD_SYMBOL"] == "calculate_price"


def test_unknown_junit_node_cannot_become_test_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    junit = _junit(
        (
            "test_price[member-price-extra]",
            '<failure message="assertion failed">wrong test node</failure>',
        ),
    )
    _fake_completed_run(monkeypatch, returncode=1, junit=junit)

    record = run_pytest(_request(tmp_path, known_case_ids=("member-price", "non-member-price")))

    assert record.outcome is RunOutcome.PROCESS_ERROR
    assert record.pytest_exit_code == 1
    assert not record.case_results
    assert "unknown test nodes" in (record.error_detail or "")
    assert "missing case IDs" in (record.error_detail or "")


def test_setup_error_cannot_become_test_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    junit = _junit(
        (
            "test_price[member-price]",
            '<error message="fixture failed">setup traceback</error>',
        ),
    )
    _fake_completed_run(monkeypatch, returncode=1, junit=junit)

    record = run_pytest(_request(tmp_path, known_case_ids=("member-price",)))

    assert record.outcome is RunOutcome.PROCESS_ERROR
    assert record.case_results[0].outcome is CaseOutcome.ERROR
    assert "skipped or errored" in (record.error_detail or "")


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [
        (2, RunOutcome.INTERRUPTED),
        (3, RunOutcome.PYTEST_INTERNAL_ERROR),
        (4, RunOutcome.PYTEST_USAGE_ERROR),
        (5, RunOutcome.NO_TESTS_COLLECTED),
        (17, RunOutcome.PROCESS_ERROR),
    ],
)
def test_preserves_non_domain_pytest_exit_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    expected: RunOutcome,
) -> None:
    _fake_completed_run(monkeypatch, returncode=exit_code, junit=None)

    record = run_pytest(_request(tmp_path))

    assert record.pytest_exit_code == exit_code
    assert record.outcome is expected
    assert record.error_detail
    assert _artifact_path(tmp_path, record.junit_ref).read_bytes() == b""


def test_missing_junit_report_is_a_process_error_even_after_exit_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_completed_run(monkeypatch, returncode=0, junit=None)

    record = run_pytest(_request(tmp_path))

    assert record.outcome is RunOutcome.PROCESS_ERROR
    assert record.pytest_exit_code == 0
    assert record.error_detail == "pytest did not produce a JUnit report"


def test_timeout_is_not_reported_as_a_test_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(argv: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(
            argv,
            kwargs["timeout"],
            output=b"partial stdout",
            stderr=b"partial stderr",
        )

    monkeypatch.setattr("evidenceguard.execution.subprocess.run", time_out)

    record = run_pytest(_request(tmp_path, timeout_seconds=0.01))

    assert record.outcome is RunOutcome.TIMEOUT
    assert record.pytest_exit_code is None
    assert _artifact_path(tmp_path, record.stdout_ref).read_bytes() == b"partial stdout"
    assert _artifact_path(tmp_path, record.stderr_ref).read_bytes() == b"partial stderr"


def test_launch_error_is_not_reported_as_a_test_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_launch(
        argv: tuple[str, ...],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[bytes]:
        raise FileNotFoundError("python executable disappeared")

    monkeypatch.setattr("evidenceguard.execution.subprocess.run", fail_to_launch)

    record = run_pytest(_request(tmp_path))

    assert record.outcome is RunOutcome.LAUNCH_ERROR
    assert record.pytest_exit_code is None
    assert "FileNotFoundError" in (record.error_detail or "")
    assert b"FileNotFoundError" in _artifact_path(tmp_path, record.stderr_ref).read_bytes()


def test_rejects_duplicate_case_ids_before_starting_pytest(tmp_path: Path) -> None:
    request = _request(tmp_path, known_case_ids=("member-price", "member-price"))

    with pytest.raises(ValueError, match="must be unique"):
        run_pytest(request)


def test_rejects_artifact_root_outside_workspace(tmp_path: Path) -> None:
    from dataclasses import replace

    request = replace(_request(tmp_path), artifact_root=Path("../outside-workspace"))
    with pytest.raises(ValueError, match="must resolve below cwd"):
        run_pytest(request)
