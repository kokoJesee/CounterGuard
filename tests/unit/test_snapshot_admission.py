"""Static package boundaries are distinct from a claim of lexical safety."""

import random
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import CaseOutcome, RunOutcome
from counterguard.snapshot_admission import _package
from counterguard.snapshot_execution import SnapshotSession, _reproduction
from counterguard.snapshot_models import SnapshotReview


def package_files():
    return {
        "pyproject.toml": b'[project]\nname="sample"\ndependencies=[]\nrequires-python=">=3.12"\n',
        "src/sample/__init__.py": b"import re\nPATTERN = re.compile('x')\n",
        "src/sample/core.py": b"class Hook(type):\n def __getattr__(cls, key): return key\n",
        "src/sample/data.txt": b"full package input",
        "media.gif": b"not a runtime input",
        "conftest.py": b"raise RuntimeError('must not load')",
    }


def test_full_package_refs_are_stable_for_twenty_input_shuffles():
    contract = SimpleNamespace(
        import_root="src", target_module="sample.core", source_ref="src/sample/core.py"
    )
    files = package_files()
    expected = _package(files, contract)
    assert expected == ("src/sample/__init__.py", "src/sample/core.py", "src/sample/data.txt")
    for seed in range(20):
        items = list(files.items())
        random.Random(seed).shuffle(items)
        assert _package(dict(items), contract) == expected


@pytest.mark.parametrize(
    "ref,body",
    [
        ("src/sample/conftest.py", b""),
        ("src/sample/hidden.pyd", b"native"),
        ("src/sample/hidden.pyc", b"bytecode"),
        ("src/sample/dependency.py", b"import requests\n"),
        ("setup.py", b"raise RuntimeError('never run')"),
        (
            "pyproject.toml",
            b'[project]\nname="x"\ndependencies=["requests"]\nrequires-python=">=3.8"',
        ),
        (
            "pyproject.toml",
            b'[project]\nname="x"\ndynamic=["dependencies"]\nrequires-python=">=3.8"',
        ),
    ],
)
def test_uninstalled_dependency_bootstrap_and_native_inputs_remain_refused(ref, body):
    files = package_files() | {ref: body}
    with pytest.raises(ArtifactIntegrityError):
        _package(
            files,
            SimpleNamespace(
                import_root="src", target_module="sample.core", source_ref="src/sample/core.py"
            ),
        )


def test_source_case_order_is_separate_from_canonical_run_result_order():
    contract = SimpleNamespace(
        cases=(SimpleNamespace(case_id="case_z"), SimpleNamespace(case_id="case_a"))
    )
    cases = (
        SimpleNamespace(case_id="case-a", outcome=CaseOutcome.PASSED),
        SimpleNamespace(case_id="case-z", outcome=CaseOutcome.FAILED),
    )
    buggy = SimpleNamespace(outcome=RunOutcome.TEST_FAILED, pytest_exit_code=1, case_results=cases)
    fixed = SimpleNamespace(outcome=RunOutcome.PASSED, pytest_exit_code=0, case_results=cases)
    assert _reproduction(buggy, fixed, contract) == (("case_z",), ())
    fixed.case_results = cases[:1]
    assert _reproduction(buggy, fixed, contract)[1] == ("fixed_case_set_mismatch",)


def test_missing_review_rejects_before_docker_or_output_creation(tmp_path, monkeypatch):
    from counterguard import snapshot_execution

    def denied(self):
        raise ArtifactIntegrityError("snapshot_trusted_anchor_mismatch")

    monkeypatch.setattr(SnapshotSession, "context", denied)
    monkeypatch.setattr(
        snapshot_execution,
        "_docker_executable",
        lambda: pytest.fail("Docker discovery must not run"),
    )
    engine = SnapshotSession(
        tmp_path / "repo", tmp_path, tmp_path / "binding", tmp_path / "review", "sha256:" + "0" * 64
    )
    with pytest.raises(ArtifactIntegrityError, match="trusted_anchor"):
        engine.capture(evidence_id="evd_denied", output=Path("denied"))
    assert not (tmp_path / "denied").exists()


def test_cli_namespace_and_review_purpose_are_explicit():
    result = CliRunner().invoke(app, ["research-snapshot", "--help"])
    assert result.exit_code == 0 and "fixture" in result.output.lower()
    assert "audit-binding" in result.output and "capture" in result.output
    assert SnapshotReview.model_fields["purpose"].annotation.__args__ == ("tool_owned_fixture",)
