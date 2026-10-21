"""Explicitly synthetic snapshot training data for unit doubles and real Git fixtures."""

from datetime import UTC, datetime

from counterguard.digests import digest_bytes
from counterguard.snapshot_admission import FIXTURE_MARKER, FIXTURE_REF, ZERO, seal
from counterguard.snapshot_comparison_data import inspect_snapshot_target
from counterguard.snapshot_comparison_models import SnapshotTargetEntry
from counterguard.snapshot_study_features import audit_snapshot_study_features
from counterguard.snapshot_study_fit import snapshot_study_target_key
from counterguard.snapshot_study_models import (
    SnapshotStudyContext,
    SnapshotStudyFitProtocol,
    SnapshotStudyLabelReview,
    SnapshotStudySample,
    SnapshotStudySplit,
)
from counterguard.study_data import persist
from counterguard.study_features import VOCABULARY_PIN
from counterguard.study_fit_models import StudyBasisPin, StudyHoldoutCommitment, StudyTrainMember
from tests.unit.test_study_features import golden


def prepare_snapshot_training(workspace, source, commit_files):
    persist(workspace / "source.json", source)
    members, repositories, snapshots = [], {}, {}
    specs = (
        ("a", "v2", "value_return", True, "return x + 1"),
        ("b", "v2", "value_return", True, "return x + 1"),
        ("c", "v1", "value_return", False, "return x"),
        ("d", "v2", "stdout_write", False, "print(x + 1)"),
    )
    for name, version, interface, applies, body in specs:
        basis = f"Tool-owned synthetic fixture: {version}, {interface}, {body}; applies={applies}."
        files = {
            FIXTURE_REF: FIXTURE_MARKER,
            "src/snapshot_target/__init__.py": b"# Tool-owned fixture package\n",
            "src/snapshot_target/core.py": f"def target(x):\n {body}\n".encode(),
            "pyproject.toml": (
                b'[project]\nname="snapshot-target"\ndependencies=[]\nrequires-python=">=3.12"\n'
            ),
            "LICENSE": b"CounterGuard tool-owned fixture\n",
            "README.md": basis.encode(),
        }
        repo, revision = commit_files(name, files)
        target, _ = inspect_snapshot_target(
            repo,
            revision,
            target_id=name,
            entry=SnapshotTargetEntry(
                target_module="snapshot_target.core",
                target_symbol="target",
                source_ref="src/snapshot_target/core.py",
                import_root="src",
            ),
            license_ref="LICENSE",
            interface_kind=interface,
            interface_basis_ref="README.md",
        )
        repositories[target.repository_identity_digest] = repo
        context = seal(
            SnapshotStudyContext(
                context_id=name,
                created_at=datetime.now(UTC),
                operator="fixture reviewer",
                reason="Independent manual synthetic feature annotation",
                metadata_basis=basis,
                target_digest=target.artifact_digest,
                source_ref="src/snapshot_target/core.py",
                source_digest=digest_bytes(files["src/snapshot_target/core.py"]),
                symbol="target",
                contract_family="rgb",
                contract_version=version,
                interface_kind=interface,
                module_group="validation",
                artifact_digest=ZERO,
            )
        )
        expected = golden(()).model_copy(
            update={"contract_version": version, "interface_kind": interface}
        )
        audit = audit_snapshot_study_features(
            target, files, context, expected, context_anchor=context.artifact_digest
        )
        assert audit.matched
        sample = seal(
            SnapshotStudySample(
                sample_id=name,
                project_group="project-" + name,
                target_ref=f"{name}/target.json",
                target_digest=target.artifact_digest,
                context_ref=f"{name}/context.json",
                context_digest=context.artifact_digest,
                audit_ref=f"{name}/audit.json",
                audit_digest=audit.artifact_digest,
                artifact_digest=ZERO,
            )
        )
        label = seal(
            SnapshotStudyLabelReview(
                created_at=datetime.now(UTC),
                operator="fixture reviewer",
                reason=basis,
                sample_digest=sample.artifact_digest,
                target_digest=target.artifact_digest,
                source_digest=source.artifact_digest,
                guard_digest=source.guard_digest,
                guard_applicable=applies,
                confirmed_legal_counterexample=not applies,
                basis_pins=(
                    StudyBasisPin(ref="README.md", content_digest=digest_bytes(files["README.md"])),
                ),
                artifact_digest=ZERO,
            )
        )
        for kind, record in (
            ("target", target),
            ("context", context),
            ("audit", audit),
            ("sample", sample),
            ("label", label),
        ):
            persist(workspace / name / (kind + ".json"), record)
        members.append(
            StudyTrainMember(
                sample_id=name,
                project_group=sample.project_group,
                repository_identity_digest=target.repository_identity_digest,
                target_key=snapshot_study_target_key(target),
                sample_ref=f"{name}/sample.json",
                sample_digest=sample.artifact_digest,
                label_ref=f"{name}/label.json",
                label_digest=label.artifact_digest,
            )
        )
        snapshots[name] = files
    split = seal(
        SnapshotStudySplit(
            split_id="snapshot-fixture-split",
            initial=tuple(members[:3]),
            refinement_additions=(members[3],),
            holdout=(
                StudyHoldoutCommitment(
                    sample_id="held",
                    project_group="held-project",
                    repository_identity_digest=digest_bytes(b"opaque-held-snapshot-repo"),
                    target_key=digest_bytes(b"opaque-held-snapshot-target"),
                    sample_digest=digest_bytes(b"opaque-held-snapshot-sample"),
                    label_digest=digest_bytes(b"opaque-held-snapshot-label"),
                ),
            ),
            artifact_digest=ZERO,
        )
    )
    protocol = seal(
        SnapshotStudyFitProtocol(
            protocol_id="snapshot-fixture-protocol",
            source_ref="source.json",
            source_digest=source.artifact_digest,
            guard_digest=source.guard_digest,
            source_project_group="source-project",
            split_ref="split.json",
            split_digest=split.artifact_digest,
            vocabulary_digest=VOCABULARY_PIN,
            artifact_digest=ZERO,
        )
    )
    persist(workspace / "split.json", split)
    persist(workspace / "protocol.json", protocol)
    return protocol, split, repositories, snapshots
