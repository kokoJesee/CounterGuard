"""Verify the no-execution boundary and distinct integrity/unknown/execution outcomes."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.compiler import run_guard as direct_run
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import RunOutcome
from counterguard.replay import (
    ReplayRequest,
    ReplayResult,
    render_replay_report,
    replay_exit_code,
    replay_guard,
    verify_replay,
)

GUARD = "grd_discount_member_rate_regression_v2"
CONTRACT = Path("examples/discount/contracts/membership_discount_final_price_v1.json")


def request(workspace, *, implementation="final_price_v1_fixed", contract=CONTRACT):
    return ReplayRequest(
        Path(f"artifacts/guards/{GUARD}/guard.json"),
        Path(f"artifacts/fitted/refined/{GUARD}.json"),
        f"examples.discount.implementations.{implementation}:calculate_price",
        contract,
        workspace,
    )


def forbid_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Skipped/unknown replay must never start pytest or a subprocess")

    monkeypatch.setattr("counterguard.replay.run_guard", forbidden)
    monkeypatch.setattr("counterguard.execution.subprocess.run", forbidden)


def test_inapplicable_does_not_start_any_process_and_is_never_rendered_pass(
    replay_workspace, monkeypatch
):
    forbid_execution(monkeypatch)
    result = replay_guard(
        request(
            replay_workspace,
            implementation="final_price_v2_correct",
            contract=Path("examples/discount/contracts/membership_discount_final_price_v2.json"),
        )
    )
    assert result.scope_decision == "inapplicable" and result.verdict == "skipped_inapplicable"
    assert result.run is None and result.violated_case_ids == ()
    directory = replay_workspace / "artifacts/replays" / result.replay_id
    assert not (directory / "runs").exists()
    assert verify_replay(directory / "result.json", cwd=replay_workspace) == result
    text = render_replay_report(
        {"results": [{"sample_id": "legal-v2", "result": result.model_dump(mode="json")}]}
    )
    assert "不适用，未运行" in text and "通过" not in text


def test_missing_contract_is_unknown_not_inapplicable_and_never_executes(
    replay_workspace, monkeypatch
):
    forbid_execution(monkeypatch)
    result = replay_guard(request(replay_workspace, contract=None))
    assert result.scope_decision == "unknown" and result.verdict == "skipped_unknown"
    assert result.feature_vector is None and result.run is None
    assert result.error_detail and all(trace.matched is None for trace in result.decision_trace)
    assert replay_exit_code(result) == 4
    path = replay_workspace / "artifacts/replays" / result.replay_id / "result.json"
    assert verify_replay(path, cwd=replay_workspace) == result
    text = render_replay_report(
        {"results": [{"sample_id": "missing-contract", "result": result.model_dump(mode="json")}]}
    )
    assert "信息不足，未运行" in text and "不适用" not in text and "通过" not in text
    result_cli = CliRunner().invoke(
        app,
        [
            "replay",
            "run",
            "--guard",
            str(request(replay_workspace).guard_path),
            "--scope",
            str(request(replay_workspace).scope_path),
            "--target",
            request(replay_workspace).target,
            "--cwd",
            str(replay_workspace),
        ],
    )
    assert result_cli.exit_code == 4
    assert json.loads(result_cli.stdout)["run"] is None


@pytest.mark.parametrize(
    "code",
    ["def calculate_price(:", "def calculate_price(amount, is_member):\n return lambda: amount"],
)
def test_bad_new_target_is_unknown_with_no_pytest(mutable_replay_workspace, monkeypatch, code):
    source = mutable_replay_workspace / "examples/discount/implementations/new_unknown.py"
    source.write_text(code, encoding="utf-8")
    forbid_execution(monkeypatch)
    result = replay_guard(request(mutable_replay_workspace, implementation="new_unknown"))
    assert result.scope_decision == "unknown" and result.run is None
    assert result.verdict == "skipped_unknown"


@pytest.mark.parametrize("kind", ["guard", "scope", "context", "fit", "learning", "feature"])
def test_input_dependency_tampering_fails_before_execution(
    mutable_replay_workspace, monkeypatch, kind
):
    root = mutable_replay_workspace
    fit = json.loads((root / "artifacts/fitted/refined/fit-manifest.json").read_bytes())
    audit = json.loads((root / fit["feature_audit_ref"]).read_bytes())
    paths = {
        "guard": request(root).guard_path,
        "scope": request(root).scope_path,
        "context": Path("benchmarks/context/scope_v1.json"),
        "fit": Path("artifacts/fitted/refined/fit-manifest.json"),
        "learning": Path(fit["groups"][0]["learning_ref"]),
        "feature": Path(
            next(
                row["feature_ref"]
                for row in audit["entries"]
                if row["sample_id"].startswith("train-")
            )
        ),
    }
    path = root / paths[kind]
    payload = json.loads(path.read_bytes())
    payload["artifact_digest"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    forbid_execution(monkeypatch)
    with pytest.raises(ArtifactIntegrityError):
        replay_guard(request(root))


def test_rehashed_scope_change_cannot_escape_its_fit_binding(mutable_replay_workspace, monkeypatch):
    path = mutable_replay_workspace / request(mutable_replay_workspace).scope_path
    payload = json.loads(path.read_bytes())
    payload["clauses"][0]["value"] = "v2"
    payload["artifact_digest"] = digest_json_artifact(payload)
    path.write_bytes(canonical_json_bytes(payload))
    forbid_execution(monkeypatch)
    with pytest.raises(ArtifactIntegrityError, match="binding mismatch"):
        replay_guard(request(mutable_replay_workspace))


@pytest.mark.parametrize(
    "outcome, verdict, code",
    [
        (RunOutcome.TIMEOUT, "timeout", 3),
        (RunOutcome.LAUNCH_ERROR, "execution_error", 3),
        (RunOutcome.NO_TESTS_COLLECTED, "collection_error", 3),
        (RunOutcome.INTERRUPTED, "execution_error", 3),
        (RunOutcome.PYTEST_INTERNAL_ERROR, "execution_error", 3),
        (RunOutcome.PROCESS_ERROR, "execution_error", 3),
    ],
)
def test_execution_failures_are_neither_pass_nor_violation(
    replay_workspace, monkeypatch, outcome, verdict, code
):
    spec = request(replay_workspace)
    base = direct_run(spec.guard_path, spec.target, cwd=replay_workspace)
    exits = {
        RunOutcome.TIMEOUT: None,
        RunOutcome.LAUNCH_ERROR: None,
        RunOutcome.NO_TESTS_COLLECTED: 5,
        RunOutcome.INTERRUPTED: 2,
        RunOutcome.PYTEST_INTERNAL_ERROR: 3,
        RunOutcome.PROCESS_ERROR: 1,
    }
    fake = base.model_copy(
        update={
            "outcome": outcome,
            "pytest_exit_code": exits[outcome],
            "case_results": (),
            "error_detail": "controlled runner failure",
        }
    )
    monkeypatch.setattr("counterguard.replay.run_guard", lambda *args, **kwargs: fake)
    result = replay_guard(spec)
    assert result.verdict == verdict and result.violated_case_ids == ()
    assert replay_exit_code(result) == code


def test_target_change_after_real_execution_is_stale_and_preserves_run(
    mutable_replay_workspace, monkeypatch
):
    root = mutable_replay_workspace
    source = root / "examples/discount/implementations/new_mutable.py"
    source.write_bytes(
        (root / "examples/discount/implementations/final_price_v1_fixed.py").read_bytes()
    )
    import counterguard.compiler as compiler

    real_runner = compiler.run_pytest

    def changed_after_run(*args, **kwargs):
        run = real_runner(*args, **kwargs)
        source.write_bytes(source.read_bytes() + b"\n# changed during execution\n")
        return run

    monkeypatch.setattr(compiler, "run_pytest", changed_after_run)
    result = replay_guard(request(root, implementation="new_mutable"))
    assert result.verdict == "stale" and result.run is not None
    assert replay_exit_code(result) == 5 and result.error_detail


def test_result_model_rejects_skipped_as_pass_or_unknown_as_inapplicable(replay_workspace):
    result = replay_guard(request(replay_workspace, contract=None))
    for change in (
        {"verdict": "pass"},
        {"verdict": "skipped_inapplicable"},
        {"scope_decision": "inapplicable"},
    ):
        with pytest.raises(ValidationError):
            ReplayResult.model_validate_json(
                json.dumps({**result.model_dump(mode="json"), **change})
            )


def test_cross_guard_scope_binding_is_rejected(replay_workspace, monkeypatch):
    forbid_execution(monkeypatch)
    spec = replace(
        request(replay_workspace),
        scope_path=Path("artifacts/fitted/refined/grd_query_limit_zero_regression_v2.json"),
    )
    with pytest.raises(ArtifactIntegrityError, match="binding"):
        replay_guard(spec)
