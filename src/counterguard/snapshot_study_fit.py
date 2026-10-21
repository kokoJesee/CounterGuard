"""Train-only, independently anchored fitting from complete tool-owned snapshots."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes
from counterguard.errors import InsufficientScopeEvidence
from counterguard.models import Digest
from counterguard.project_config import reject_links, repository_path
from counterguard.scope import FIELD_ORDER, learn_scope
from counterguard.scope_explanations import explain_scope
from counterguard.snapshot_admission import ZERO, require, seal
from counterguard.snapshot_comparison_data import inspect_snapshot_target
from counterguard.snapshot_comparison_models import SnapshotComparisonTarget
from counterguard.snapshot_execution import SnapshotSession
from counterguard.snapshot_models import SnapshotEvidence
from counterguard.snapshot_study_features import verify_snapshot_study_feature_audit
from counterguard.snapshot_study_models import (
    SnapshotStudyContext,
    SnapshotStudyFeatureAudit,
    SnapshotStudyFit,
    SnapshotStudyFitProtocol,
    SnapshotStudyFitReview,
    SnapshotStudyLabelReview,
    SnapshotStudyLearnedScope,
    SnapshotStudySample,
    SnapshotStudySource,
    SnapshotStudySplit,
)
from counterguard.standalone_capture import _model
from counterguard.study_data import StudyNotReady, persist, repository_identity
from counterguard.study_features import VOCABULARY_PIN, study_training_example
from counterguard.study_fit import _destination
from counterguard.study_fit_models import Phase, StudyFitInput


def snapshot_study_target_key(target):
    require(type(target) is SnapshotComparisonTarget, "snapshot_study_target_type_required")
    return digest_bytes(
        canonical_json_bytes(
            {
                "repository": target.repository_identity_digest,
                "revision": target.manifest.commit,
                "module": target.entry.target_module,
                "symbol": target.entry.target_symbol,
            }
        )
    )


def inspect_snapshot_study_source(source, *, evidence_ref, guard_ref, source_id):
    require(type(source) is SnapshotSession, "snapshot_study_fixture_source_type_required")
    repository_path(evidence_ref)
    repository_path(guard_ref)
    guard = source.verify_guard(
        source.workspace / guard_ref, evidence_path=source.workspace / evidence_ref
    )
    binding, review = source.context()
    evidence = _model(source.workspace, evidence_ref, SnapshotEvidence)
    return seal(
        SnapshotStudySource(
            source_id=source_id,
            repository_identity_digest=repository_identity(source.repo),
            evidence_ref=evidence_ref,
            guard_ref=guard_ref,
            binding_digest=binding.artifact_digest,
            evidence_digest=evidence.artifact_digest,
            guard_digest=guard.artifact_digest,
            source_review_digest=review.artifact_digest,
            buggy_commit=binding.contract.buggy_commit,
            fixed_commit=binding.contract.fixed_commit,
            head_commit=binding.head_commit,
            case_ids=guard.case_ids,
            artifact_digest=ZERO,
        )
    )


def _protocol(source_engine, protocol_ref):
    workspace = source_engine.workspace
    protocol = _model(workspace, protocol_ref, SnapshotStudyFitProtocol)
    require(protocol.vocabulary_digest == VOCABULARY_PIN, "snapshot_study_vocabulary_changed")
    split = _model(workspace, protocol.split_ref, SnapshotStudySplit)
    source = _model(workspace, protocol.source_ref, SnapshotStudySource)
    require(
        (split.artifact_digest, source.artifact_digest, source.guard_digest)
        == (protocol.split_digest, protocol.source_digest, protocol.guard_digest),
        "snapshot_study_protocol_subject_changed",
    )
    rebuilt = inspect_snapshot_study_source(
        source_engine,
        evidence_ref=source.evidence_ref,
        guard_ref=source.guard_ref,
        source_id=source.source_id,
    )
    require(rebuilt == source, "snapshot_study_source_not_rebuilt")
    require(
        all(
            r.project_group != protocol.source_project_group
            and r.repository_identity_digest != source.repository_identity_digest
            for r in split.holdout
        ),
        "snapshot_study_source_in_holdout",
    )
    require(
        all(
            r.repository_identity_digest != source.repository_identity_digest
            or r.project_group == protocol.source_project_group
            for r in split.initial + split.refinement_additions
        ),
        "snapshot_study_source_group_misdeclared",
    )
    return protocol, split, source


def _review(workspace, ref, anchor):
    review = _model(workspace, ref, SnapshotStudyFitReview)
    require(review.artifact_digest == anchor, "snapshot_study_fit_anchor_changed")
    current, seen = review, {ref}
    for _ in range(32):
        if current.previous_ref is None:
            return review
        require(current.previous_ref not in seen, "snapshot_study_fit_review_cycle")
        seen.add(current.previous_ref)
        previous = _model(workspace, current.previous_ref, SnapshotStudyFitReview)
        require(
            previous.artifact_digest == current.previous_digest
            and previous.created_at <= current.created_at,
            "snapshot_study_fit_predecessor_changed",
        )
        current = previous
    raise StudyNotReady("snapshot_study_fit_review_budget_exceeded")


def issue_snapshot_study_fit_review(
    source,
    protocol_ref,
    *,
    output_ref,
    operator,
    reason,
    action="approve",
    previous_ref=None,
    previous_anchor=None,
):
    """Approve input pins without invoking learner, target Python or held-out files."""
    require(type(source) is SnapshotSession, "snapshot_study_fixture_source_type_required")
    protocol, split, declaration = _protocol(source, protocol_ref)
    previous = None
    if previous_ref is not None:
        previous = _review(source.workspace, previous_ref, previous_anchor)
    else:
        require(previous_anchor is None, "snapshot_study_fit_predecessor_incomplete")
    review = seal(
        SnapshotStudyFitReview(
            created_at=datetime.now(UTC),
            operator=operator,
            reason=reason,
            action=action,
            protocol_digest=protocol.artifact_digest,
            split_digest=split.artifact_digest,
            source_digest=declaration.artifact_digest,
            implementation_digests=inspection_implementation_digests(),
            previous_ref=previous_ref,
            previous_digest=previous.artifact_digest if previous else None,
            artifact_digest=ZERO,
        )
    )
    return persist(_destination(source.workspace, Path(output_ref), (source.repo,)), review)


@dataclass(frozen=True)
class SnapshotStudyFitSession:
    source: SnapshotSession
    repositories: dict[str, Path]
    review_anchor: str

    def __post_init__(self):
        require(type(self.source) is SnapshotSession, "snapshot_study_fixture_source_type_required")
        TypeAdapter(Digest).validate_python(self.review_anchor)
        repositories = {}
        for key, value in self.repositories.items():
            TypeAdapter(Digest).validate_python(key)
            reject_links(value)
            path = Path(value).resolve(strict=True)
            require(repository_identity(path) == key, "snapshot_study_repository_identity_changed")
            repositories[key] = path
        object.__setattr__(self, "repositories", repositories)

    @property
    def workspace(self):
        return self.source.workspace

    def _load(self, protocol_ref, review_ref, phase):
        # Reject holdout before opening even the protocol/commitment file.
        TypeAdapter(Phase).validate_python(phase)
        review = _review(self.workspace, review_ref, self.review_anchor)
        require(
            review.implementation_digests == inspection_implementation_digests(),
            "snapshot_study_fit_implementation_stale",
        )
        if review.action != "approve":
            raise StudyNotReady("snapshot_study_fit_review_withdrawn")
        protocol, split, source = _protocol(self.source, protocol_ref)
        require(
            (protocol.artifact_digest, split.artifact_digest, source.artifact_digest)
            == (review.protocol_digest, review.split_digest, review.source_digest),
            "snapshot_study_fit_review_subject_changed",
        )
        members = split.initial
        if phase == "refined":
            if not split.refinement_additions:
                raise StudyNotReady("snapshot_study_refinement_missing")
            members += split.refinement_additions
        inputs, examples = [], []
        additions = {r.sample_id for r in split.refinement_additions}
        for member in sorted(members, key=lambda row: row.sample_id):
            pin, example = self._sample(member, source)
            if phase == "refined" and member.sample_id in additions:
                require(
                    not example.guard_applicable, "snapshot_study_refinement_not_legal_negative"
                )
            inputs.append(pin)
            examples.append(example)
        return protocol, split, source, review, tuple(inputs), tuple(examples)

    def _sample(self, member, source):
        sample = _model(self.workspace, member.sample_ref, SnapshotStudySample)
        require(
            (sample.sample_id, sample.project_group, sample.artifact_digest)
            == (member.sample_id, member.project_group, member.sample_digest),
            "snapshot_study_member_changed",
        )
        target = _model(self.workspace, sample.target_ref, SnapshotComparisonTarget)
        require(
            target.artifact_digest == sample.target_digest
            and target.repository_identity_digest == member.repository_identity_digest
            and snapshot_study_target_key(target) == member.target_key,
            "snapshot_study_target_subject_changed",
        )
        if target.repository_identity_digest not in self.repositories:
            raise StudyNotReady("snapshot_study_target_repository_missing")
        repo = self.repositories[target.repository_identity_digest]
        rebuilt, files = inspect_snapshot_target(
            repo,
            target.manifest.commit,
            target_id=target.target_id,
            entry=target.entry,
            license_ref=target.license_ref,
            interface_kind=target.interface_kind,
            interface_basis_ref=target.interface_basis_ref,
            budget=target.manifest.budget,
        )
        require(target == rebuilt, "snapshot_study_target_not_rebuilt")
        context = _model(self.workspace, sample.context_ref, SnapshotStudyContext)
        audit = _model(self.workspace, sample.audit_ref, SnapshotStudyFeatureAudit)
        require(
            context.artifact_digest == sample.context_digest
            and audit.artifact_digest == sample.audit_digest,
            "snapshot_study_feature_subject_changed",
        )
        verify_snapshot_study_feature_audit(target, files, context, audit)
        if not audit.matched:
            raise StudyNotReady("snapshot_study_feature_annotation_mismatch")
        label = _model(self.workspace, member.label_ref, SnapshotStudyLabelReview)
        require(
            (
                label.artifact_digest,
                label.sample_digest,
                label.target_digest,
                label.source_digest,
                label.guard_digest,
            )
            == (
                member.label_digest,
                sample.artifact_digest,
                target.artifact_digest,
                source.artifact_digest,
                source.guard_digest,
            ),
            "snapshot_study_label_subject_changed",
        )
        require(
            all(
                pin.ref in files and digest_bytes(files[pin.ref]) == pin.content_digest
                for pin in label.basis_pins
            ),
            "snapshot_study_label_basis_changed",
        )
        return StudyFitInput(
            member=member,
            target_digest=target.artifact_digest,
            context_digest=context.artifact_digest,
            audit_digest=audit.artifact_digest,
        ), study_training_example(audit.record.features, label.guard_applicable)

    def fit(self, protocol_ref, review_ref, *, phase, output=None):
        protocol, split, source, review, inputs, examples = self._load(
            protocol_ref, review_ref, phase
        )
        predicates = set()
        for row in examples:
            if row.guard_applicable:
                predicates.update((f, "eq", getattr(row.features, f)) for f in FIELD_ORDER[:-1])
                predicates.update(
                    ("ast_features", "contains", t) for t in row.features.ast_features
                )
        if len(predicates) > protocol.max_predicates:
            raise StudyNotReady("snapshot_study_fit_predicate_budget_exceeded")
        binding_digest = digest_bytes(canonical_json_bytes(inputs))
        learning, explanation, scope, refusal = None, None, None, None
        try:
            learning = learn_scope(examples)
        except InsufficientScopeEvidence as error:
            refusal = error.reason_code
        if learning is not None:
            explanation = explain_scope(learning, examples)
            scope = seal(
                SnapshotStudyLearnedScope(
                    protocol_digest=protocol.artifact_digest,
                    split_digest=split.artifact_digest,
                    source_digest=source.artifact_digest,
                    guard_digest=source.guard_digest,
                    review_digest=review.artifact_digest,
                    phase=phase,
                    training_binding_digest=binding_digest,
                    learning_digest=learning.artifact_digest,
                    explanation_digest=explanation.artifact_digest,
                    clauses=learning.clauses,
                    artifact_digest=ZERO,
                )
            )
        result = seal(
            SnapshotStudyFit(
                protocol_ref=protocol_ref,
                protocol_digest=protocol.artifact_digest,
                split_digest=split.artifact_digest,
                source_digest=source.artifact_digest,
                guard_digest=source.guard_digest,
                review_ref=review_ref,
                review_digest=review.artifact_digest,
                phase=phase,
                inputs=inputs,
                training_binding_digest=binding_digest,
                implementation_digests=inspection_implementation_digests(),
                status="refused" if refusal else "fitted",
                refusal_code=refusal,
                learning=learning,
                explanation=explanation,
                scope=scope,
                artifact_digest=ZERO,
            )
        )
        if output is not None:
            persist(
                _destination(
                    self.workspace, Path(output), (self.source.repo, *self.repositories.values())
                ),
                result,
            )
        return result

    def verify(self, path):
        path = Path(path)
        path = path if path.is_absolute() else self.workspace / path
        reject_links(path)
        require(path.resolve().is_relative_to(self.workspace), "snapshot_study_fit_path_escape")
        ref = path.resolve().relative_to(self.workspace).as_posix()
        result = _model(self.workspace, ref, SnapshotStudyFit)
        rebuilt = self.fit(result.protocol_ref, result.review_ref, phase=result.phase)
        require(result == rebuilt, "snapshot_study_fit_not_rebuilt")
        return rebuilt
