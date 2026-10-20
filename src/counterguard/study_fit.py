"""Rebuild reviewed training inputs and fit without opening any held-out labels."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from counterguard.change_analysis import inspection_implementation_digests
from counterguard.digests import canonical_json_bytes, digest_bytes
from counterguard.errors import InsufficientScopeEvidence
from counterguard.path_limits import require_publication
from counterguard.project_config import reject_links, repository_path
from counterguard.scope import FIELD_ORDER, learn_scope
from counterguard.scope_explanations import explain_scope
from counterguard.standalone_capture import ZERO, _model, _ref, _require, _seal
from counterguard.static_exports import resolve_static_reexport
from counterguard.study_data import (
    StudyNotReady,
    inspect_source,
    inspect_target,
    persist,
    repository_identity,
)
from counterguard.study_features import (
    VOCABULARY_PIN,
    StudyFeatureAudit,
    StudyFeatureContext,
    study_training_example,
    verify_study_feature_audit,
)
from counterguard.study_fit_models import (
    Phase,
    StudyFit,
    StudyFitInput,
    StudyFitProtocol,
    StudyFitReview,
    StudyLabelReview,
    StudyLearnedScope,
    StudySample,
    StudySplit,
)
from counterguard.study_models import StudySource, StudyTarget


def study_target_key(target):
    """A renamed target_id or artifact reference must not create another observation."""
    return digest_bytes(
        canonical_json_bytes(
            {
                "repository": target.repository_identity_digest,
                "revision": target.revision,
                "module": target.module,
                "symbol": target.symbol,
            }
        )
    )


def _protocol(source_repo, workspace, protocol_ref):
    protocol = _model(workspace, protocol_ref, StudyFitProtocol)
    _require(protocol.vocabulary_digest == VOCABULARY_PIN, "study_fit_vocabulary_changed")
    split = _model(workspace, protocol.split_ref, StudySplit)
    source = _model(workspace, protocol.source_ref, StudySource)
    _require(
        (split.artifact_digest, source.artifact_digest, source.guard_digest)
        == (protocol.split_digest, protocol.source_digest, protocol.guard_digest),
        "study_fit_protocol_subject_changed",
    )
    rebuilt, _, _ = inspect_source(
        source_repo, workspace, source.guard_ref, source_id=source.source_id
    )
    _require(rebuilt == source, "study_fit_source_not_rebuilt")
    _require(
        all(
            r.project_group != protocol.source_project_group
            and r.repository_identity_digest != source.repository_identity_digest
            for r in split.holdout
        ),
        "study_fit_source_in_holdout",
    )
    for member in split.initial + split.refinement_additions:
        _require(
            member.repository_identity_digest != source.repository_identity_digest
            or member.project_group == protocol.source_project_group,
            "study_fit_source_group_misdeclared",
        )
    return protocol, split, source


def _review(workspace, review_ref, anchor):
    review = _model(workspace, review_ref, StudyFitReview)
    _require(review.artifact_digest == anchor, "study_fit_review_anchor_changed")
    current, seen = review, {review_ref}
    for _ in range(32):
        if current.previous_ref is None:
            return review
        _require(current.previous_ref not in seen, "study_fit_review_cycle")
        seen.add(current.previous_ref)
        previous = _model(workspace, current.previous_ref, StudyFitReview)
        _require(previous.artifact_digest == current.previous_digest, "study_fit_previous_changed")
        _require(previous.created_at <= current.created_at, "study_fit_review_time_regressed")
        current = previous
    raise StudyNotReady("study_fit_review_budget_exceeded")


def _destination(workspace, path, repositories):
    path = path if path.is_absolute() else workspace / path
    reject_links(path)
    path = path.resolve()
    _require(path.is_relative_to(workspace), "study_fit_output_escapes_workspace")
    _require(
        not any(path.is_relative_to(repo) for repo in repositories), "study_fit_output_in_repo"
    )
    repository_path(path.relative_to(workspace).as_posix())
    require_publication(path)
    return path


def issue_fit_review(
    source_repo,
    workspace,
    protocol_ref,
    *,
    output_ref,
    operator,
    reason,
    action="approve",
    previous_ref=None,
    previous_anchor=None,
):
    """Trusted local action before fitting; never calls the learner or reads holdout files."""
    source_repo, workspace = Path(source_repo), Path(workspace)
    reject_links(source_repo)
    reject_links(workspace)
    source_repo, workspace = source_repo.resolve(strict=True), workspace.resolve(strict=True)
    protocol, split, source = _protocol(source_repo, workspace, protocol_ref)
    previous = None
    if previous_ref is not None:
        previous = _review(workspace, previous_ref, previous_anchor)
    else:
        _require(previous_anchor is None, "study_fit_previous_incomplete")
    review = _seal(
        StudyFitReview(
            created_at=datetime.now(UTC),
            operator=operator,
            reason=reason,
            action=action,
            protocol_digest=protocol.artifact_digest,
            split_digest=split.artifact_digest,
            source_digest=source.artifact_digest,
            implementation_digests=inspection_implementation_digests(),
            previous_ref=previous_ref,
            previous_digest=previous.artifact_digest if previous else None,
            artifact_digest=ZERO,
        )
    )
    destination = _destination(workspace, Path(output_ref), (source_repo,))
    return persist(destination, review)


@dataclass(frozen=True)
class StudyFitSession:
    source_repo: Path
    workspace: Path
    repositories: dict[str, Path]
    review_anchor: str

    def __post_init__(self):
        from counterguard.models import Digest

        TypeAdapter(Digest).validate_python(self.review_anchor)
        for name in ("source_repo", "workspace"):
            path = Path(getattr(self, name))
            reject_links(path)
            object.__setattr__(self, name, path.resolve(strict=True))
        repositories = {}
        for key, value in self.repositories.items():
            TypeAdapter(Digest).validate_python(key)
            path = Path(value)
            reject_links(path)
            path = path.resolve(strict=True)
            _require(repository_identity(path) == key, "study_fit_repository_identity_changed")
            repositories[key] = path
        object.__setattr__(self, "repositories", repositories)

    def _load(self, protocol_ref, review_ref, phase):
        # This check must stay before reading protocol, training rows or commitments.
        TypeAdapter(Phase).validate_python(phase)
        review = _review(self.workspace, review_ref, self.review_anchor)
        _require(
            review.implementation_digests == inspection_implementation_digests(),
            "study_fit_implementation_stale",
        )
        if review.action != "approve":
            raise StudyNotReady("study_fit_review_withdrawn")
        protocol, split, source = _protocol(self.source_repo, self.workspace, protocol_ref)
        _require(
            (protocol.artifact_digest, split.artifact_digest, source.artifact_digest)
            == (review.protocol_digest, review.split_digest, review.source_digest),
            "study_fit_review_subject_changed",
        )
        members = split.initial
        if phase == "refined":
            if not split.refinement_additions:
                raise StudyNotReady("study_fit_refinement_missing")
            members += split.refinement_additions
        members = tuple(sorted(members, key=lambda row: row.sample_id))
        inputs, examples = [], []
        additions = {r.sample_id for r in split.refinement_additions}
        for member in members:
            pin, example = self._sample(member, source)
            if phase == "refined" and member.sample_id in additions:
                _require(
                    not example.guard_applicable, "study_fit_refinement_must_be_legal_negative"
                )
            inputs.append(pin)
            examples.append(example)
        return protocol, split, source, review, tuple(inputs), tuple(examples)

    def _sample(self, member, source):
        workspace = self.workspace
        sample = _model(workspace, member.sample_ref, StudySample)
        _require(
            (sample.sample_id, sample.project_group, sample.artifact_digest)
            == (member.sample_id, member.project_group, member.sample_digest),
            "study_fit_member_changed",
        )
        target = _model(workspace, sample.target_ref, StudyTarget)
        _require(
            target.artifact_digest == sample.target_digest
            and target.repository_identity_digest == member.repository_identity_digest
            and study_target_key(target) == member.target_key,
            "study_fit_target_subject_changed",
        )
        if target.repository_identity_digest not in self.repositories:
            raise StudyNotReady("study_fit_target_repository_missing")
        repo = self.repositories[target.repository_identity_digest]
        rebuilt, files = inspect_target(
            repo,
            target.revision,
            target_id=target.target_id,
            module=target.module,
            symbol=target.symbol,
            import_root=target.import_root,
            profile=target.profile,
            license_ref=target.license_ref,
        )
        _require(rebuilt == target, "study_fit_target_not_rebuilt")
        context = _model(workspace, sample.context_ref, StudyFeatureContext)
        audit = _model(workspace, sample.audit_ref, StudyFeatureAudit)
        definition = (target.source_ref, target.symbol)
        if target.profile == "static-reexport-v2":
            export = resolve_static_reexport(
                files,
                module=target.module,
                symbol=target.symbol,
                import_root=target.import_root,
                algorithm="static-root-reexport.v2",
            )
            definition = (export["definition_ref"], export["definition_symbol"])
        _require(
            context.artifact_digest == sample.context_digest
            and audit.artifact_digest == sample.audit_digest
            and context.source_ref in {p.path for p in target.closure_pins}
            and (context.source_ref, context.symbol) == definition,
            "study_fit_feature_subject_changed",
        )
        verify_study_feature_audit(
            audit, files[context.source_ref], context, context_anchor=sample.context_digest
        )
        if not audit.matched:
            raise StudyNotReady("study_fit_feature_annotation_mismatch")
        label = _model(workspace, member.label_ref, StudyLabelReview)
        _require(
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
            "study_fit_label_subject_changed",
        )
        _require(
            all(
                p.ref in files and digest_bytes(files[p.ref]) == p.content_digest
                for p in label.basis_pins
            ),
            "study_fit_label_basis_changed",
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
        candidates = set()
        for row in examples:
            if row.guard_applicable:
                candidates.update((f, "eq", getattr(row.features, f)) for f in FIELD_ORDER[:-1])
                candidates.update(
                    ("ast_features", "contains", t) for t in row.features.ast_features
                )
        if len(candidates) > protocol.max_predicates:
            raise StudyNotReady("study_fit_predicate_budget_exceeded")
        binding_digest = digest_bytes(canonical_json_bytes(inputs))
        learning, explanation, scope, refusal = None, None, None, None
        try:
            learning = learn_scope(examples)
        except InsufficientScopeEvidence as error:
            refusal = error.reason_code
        if learning is not None:
            explanation = explain_scope(learning, examples)
            scope = _seal(
                StudyLearnedScope(
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
        result = _seal(
            StudyFit(
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
            destination = _destination(
                self.workspace, Path(output), (self.source_repo, *self.repositories.values())
            )
            persist(destination, result)
        return result

    def verify(self, path):
        result = _model(self.workspace, _ref(Path(path), self.workspace), StudyFit)
        rebuilt = self.fit(result.protocol_ref, result.review_ref, phase=result.phase)
        _require(result == rebuilt, "study_fit_result_does_not_rebuild")
        return rebuilt
