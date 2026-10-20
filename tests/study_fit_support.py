"""Tool-owned, explicitly synthetic training data shared by static and Git tests."""

from datetime import UTC, datetime

from counterguard.digests import canonical_json_bytes, digest_bytes
from counterguard.standalone_capture import ZERO, _seal
from counterguard.study_data import inspect_target, persist
from counterguard.study_features import VOCABULARY_PIN, audit_study_features
from counterguard.study_fit import study_target_key
from counterguard.study_fit_models import (
    StudyBasisPin,
    StudyFitProtocol,
    StudyHoldoutCommitment,
    StudyLabelReview,
    StudySample,
    StudySplit,
    StudyTrainMember,
)
from tests.unit.test_study_features import context, golden


def prepare_training(workspace, source, commit_files, *, reexport=False, decoy_context=False):
    """commit_files is either a deterministic Git-shaped double or actual tool Git."""
    persist(workspace / "source.json", source)
    members, repositories, snapshots = [], {}, {}
    specifications = (
        ("a", "v2", "value_return", True, "return x + 1"),
        ("b", "v2", "value_return", True, "return x + 1"),
        ("c", "v1", "value_return", False, "return x"),
        ("d", "v2", "stdout_write", False, "print(x + 1)"),
    )
    for name, version, interface, applies, body in specifications:
        spec = (
            f"Tool-owned fixture {version} {interface}: {body}; explicit applicability={applies}."
        )
        files = {
            "src/fixture_target/__init__.py": b"# Tool-owned static fixture\n",
            "src/fixture_target/core.py": f"def target(x):\n {body}\n".encode(),
            "pyproject.toml": (
                b'[project]\nname="fixture-target"\ndependencies=[]\nrequires-python=">=3.12"\n'
            ),
            "LICENSE": b"CounterGuard tool-owned fixture\n",
            "README.md": spec.encode(),
        }
        if reexport:
            files["src/fixture_target/__init__.py"] = (
                b"from .core import implementation as target\n"
            )
            files["src/fixture_target/core.py"] = (
                f"def implementation(x):\n {body}\n\ndef target(x):\n return x\n"
            ).encode()
        repo, revision = commit_files(name, files)
        target, _ = inspect_target(
            repo,
            revision,
            target_id=name,
            module="fixture_target" if reexport else "fixture_target.core",
            symbol="target",
            import_root="src",
            profile="static-reexport-v2" if reexport else "direct",
            license_ref="LICENSE",
        )
        repositories[target.repository_identity_digest] = repo
        source_bytes = files["src/fixture_target/core.py"]
        feature_context = context(
            source_bytes,
            context_id=name,
            source_ref="src/fixture_target/core.py",
            contract_family="price",
            contract_version=version,
            interface_kind=interface,
            metadata_basis=spec,
            symbol="implementation" if reexport and not decoy_context else "target",
        )
        expected = golden(()).model_copy(
            update={
                "contract_family": "price",
                "contract_version": version,
                "interface_kind": interface,
            }
        )
        audit = audit_study_features(
            source_bytes, feature_context, expected, context_anchor=feature_context.artifact_digest
        )
        assert audit.matched
        sample = _seal(
            StudySample(
                sample_id=name,
                project_group="project-" + name,
                target_ref=f"{name}/target.json",
                target_digest=target.artifact_digest,
                context_ref=f"{name}/context.json",
                context_digest=feature_context.artifact_digest,
                audit_ref=f"{name}/audit.json",
                audit_digest=audit.artifact_digest,
                artifact_digest=ZERO,
            )
        )
        label = _seal(
            StudyLabelReview(
                created_at=datetime.now(UTC),
                operator="tool-owned fixture reviewer",
                reason=spec,
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
        for kind, model in (
            ("target", target),
            ("context", feature_context),
            ("audit", audit),
            ("sample", sample),
            ("label", label),
        ):
            persist(workspace / name / (kind + ".json"), model)
        members.append(
            StudyTrainMember(
                sample_id=name,
                project_group=sample.project_group,
                repository_identity_digest=target.repository_identity_digest,
                target_key=study_target_key(target),
                sample_ref=f"{name}/sample.json",
                sample_digest=sample.artifact_digest,
                label_ref=f"{name}/label.json",
                label_digest=label.artifact_digest,
            )
        )
        snapshots[name] = files
    holdout = StudyHoldoutCommitment(
        sample_id="held",
        project_group="separate-held-project",
        repository_identity_digest=digest_bytes(b"opaque-held-fixture-repository"),
        target_key=digest_bytes(b"opaque-held-fixture-target"),
        sample_digest=digest_bytes(b"opaque-held-fixture-sample"),
        label_digest=digest_bytes(b"opaque-held-fixture-label"),
    )
    split = _seal(
        StudySplit(
            split_id="tool-fixture-split",
            initial=tuple(members[:3]),
            refinement_additions=(members[3],),
            holdout=(holdout,),
            artifact_digest=ZERO,
        )
    )
    protocol = _seal(
        StudyFitProtocol(
            protocol_id="tool-fixture-protocol",
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
    assert b"source_id" not in canonical_json_bytes(expected)
    return protocol, split, repositories, snapshots
