"""Known tool-authored snapshot queries, metadata and reviews; no external input."""

from datetime import UTC, datetime

from counterguard.digests import digest_bytes
from counterguard.snapshot_admission import FIXTURE_MARKER, FIXTURE_REF, ZERO, seal
from counterguard.snapshot_comparison_data import create_comparison_map, inspect_snapshot_target
from counterguard.snapshot_comparison_models import SnapshotTargetEntry
from counterguard.snapshot_study_features import audit_snapshot_study_features
from counterguard.snapshot_study_models import SnapshotStudyContext
from counterguard.snapshot_study_replay import (
    SnapshotStudyReplaySession,
    issue_snapshot_study_execution_review,
)
from counterguard.snapshot_study_replay_models import SnapshotStudyPlan
from counterguard.study_data import persist
from tests.unit.test_study_features import golden


def prepare_snapshot_query(
    fit_session,
    name,
    commit_files,
    guard,
    binding,
    *,
    stdout=True,
    initial_ref="initial.json",
    refined_ref="refined.json",
):
    workspace = fit_session.workspace
    body = (
        " print(min(max(value, 0), 255))\n"
        if stdout
        else " if not 0 <= value <= 255: raise ValueError('outside range')\n return value\n"
    )
    source = (
        "from __future__ import annotations\nimport os\n"
        "if os.environ.get('COUNTERGUARD_CONTRACT') != 'cg_control/contract.json':\n"
        " raise RuntimeError('only admitted Docker may import this query')\n"
        "def normalize(value):\n" + body
    ).encode()
    basis = (
        "Tool-owned normalize prints a clamped integer, returns None and does not raise."
        if stdout
        else "Tool-owned normalize returns a valid integer unchanged; values outside "
        "0..255 raise ValueError with message outside range."
    )
    files = {
        FIXTURE_REF: FIXTURE_MARKER,
        "src/snapshot_query/__init__.py": b"from .core import normalize\n",
        "src/snapshot_query/core.py": source,
        "src/snapshot_query/resource.txt": b"Complete package fixture resource\n",
        "pyproject.toml": b'[project]\nname="snapshot-query"\ndependencies=[]\n'
        b'requires-python=">=3.12"\n'
        b'[tool.pytest.ini_options]\nminversion="999"\nrequired_plugins=["unavailable"]\n',
        "conftest.py": b"raise RuntimeError('root bootstrap must never load')\n",
        "LICENSE": b"CounterGuard tool-owned fixture\n",
        "README.md": basis.encode(),
    }
    repo, revision = commit_files(name, files)
    interface = "stdout_write" if stdout else "value_return"
    target, _ = inspect_snapshot_target(
        repo,
        revision,
        target_id=name,
        entry=SnapshotTargetEntry(
            target_module="snapshot_query.core",
            target_symbol="normalize",
            source_ref="src/snapshot_query/core.py",
            import_root="src",
        ),
        license_ref="LICENSE",
        interface_kind=interface,
        interface_basis_ref="README.md",
    )
    context = seal(
        SnapshotStudyContext(
            context_id=name,
            created_at=datetime.now(UTC),
            operator="fixture reviewer",
            reason="Independent manual syntax annotation of a known synthetic query",
            metadata_basis=basis,
            target_digest=target.artifact_digest,
            source_ref="src/snapshot_query/core.py",
            source_digest=digest_bytes(source),
            symbol="normalize",
            contract_family="rgb",
            contract_version="v2",
            interface_kind=interface,
            module_group="validation",
            artifact_digest=ZERO,
        )
    )
    expected = golden(() if stdout else ("range:check",)).model_copy(
        update={"interface_kind": interface}
    )
    audit = audit_snapshot_study_features(
        target, files, context, expected, context_anchor=context.artifact_digest
    )
    assert audit.matched
    mapping = create_comparison_map(guard, binding.contract, target)
    for kind, value in (
        ("target", target),
        ("context", context),
        ("audit", audit),
        ("map", mapping),
    ):
        persist(workspace / name / (kind + ".json"), value)
    plan = seal(
        SnapshotStudyPlan(
            evidence_ref="c/evidence.json",
            guard_ref="g/guard.json",
            target_ref=name + "/target.json",
            map_ref=name + "/map.json",
            review_ref=name + "/execution-review.json",
            initial_fit_ref=initial_ref,
            refined_fit_ref=refined_ref,
            context_ref=name + "/context.json",
            audit_ref=name + "/audit.json",
            method="b1_always",
            artifact_digest=ZERO,
        )
    )
    review = issue_snapshot_study_execution_review(
        fit_session,
        repo,
        plan,
        output=name + "/execution-review.json",
        reason="Synthetic complete query, original Guard and both actual fits reviewed",
        source_interface="value_return",
        source_interface_basis_ref="src/snapshot_sample/core.py",
    )
    persist(workspace / name / "plan.json", plan)
    return (
        SnapshotStudyReplaySession(fit_session.source, repo, review.artifact_digest, fit_session),
        plan,
        target,
        files,
    )
