"""Bind unchanged syntax extraction to complete, tool-owned snapshot targets."""

from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.predicates import FeatureVector
from counterguard.snapshot_admission import FIXTURE_MARKER, FIXTURE_REF, ZERO, require, seal
from counterguard.snapshot_comparison_models import SnapshotComparisonTarget
from counterguard.snapshot_study_models import (
    SnapshotStudyContext,
    SnapshotStudyFeatureAudit,
    SnapshotStudyFeatureRecord,
)
from counterguard.static_exports import resolve_static_reexport
from counterguard.study_features import StudyFeatureContext, _exact, extract_study_features


def _subject(target, files, context, anchor):
    target = _exact(target, SnapshotComparisonTarget)
    context = _exact(context, SnapshotStudyContext)
    require(
        target.artifact_digest == digest_json_artifact(target)
        and context.artifact_digest == anchor == digest_json_artifact(context)
        and context.target_digest == target.artifact_digest,
        "snapshot_study_feature_anchor_or_target_changed",
    )
    require(files.get(FIXTURE_REF) == FIXTURE_MARKER, "snapshot_study_fixture_required")
    require(
        target.manifest.artifact_digest == digest_json_artifact(target.manifest)
        and set(files) == {p.path for p in target.manifest.files}
        and all(digest_bytes(files[p.path]) == p.content_digest for p in target.manifest.files),
        "snapshot_study_feature_manifest_changed",
    )
    definition = target.entry.source_ref, target.entry.target_symbol
    if context.source_ref != definition[0] or context.symbol != definition[1]:
        export = resolve_static_reexport(
            files,
            module=target.entry.target_module,
            symbol=target.entry.target_symbol,
            import_root=target.entry.import_root,
            algorithm="static-root-reexport.v2",
        )
        definition = export["definition_ref"], export["definition_symbol"]
    require(
        context.source_ref in target.package_refs
        and (context.source_ref, context.symbol) == definition
        and context.interface_kind == target.interface_kind,
        "snapshot_study_feature_definition_mismatch",
    )
    # Both contracts are tool-owned fixture types. Reuse only the existing syntax
    # engine; the externally visible record binds the new target and context.
    values = {name: getattr(context, name) for name in StudyFeatureContext.model_fields}
    values.update(
        schema_version="study-feature-context.v1",
        purpose="tool_owned_research_fixture_only",
        artifact_digest=ZERO,
    )
    return seal(StudyFeatureContext(**values))


def extract_snapshot_study_features(target, files, context, *, context_anchor):
    inner = _subject(target, files, context, context_anchor)
    record = extract_study_features(
        files[context.source_ref], inner, context_anchor=inner.artifact_digest
    )
    # Keep exact nested types; FeatureVector's canonical serializer deliberately
    # renders its frozenset as JSON arrays and is not a Python constructor input.
    values = {name: getattr(record, name) for name in type(record).model_fields}
    values.update(
        schema_version="snapshot-study-feature-record.v1",
        purpose="tool_owned_snapshot_study_only",
        extractor="ast-features.snapshot-study.v1",
        target_digest=target.artifact_digest,
        context_digest=context.artifact_digest,
        artifact_digest=ZERO,
    )
    return seal(SnapshotStudyFeatureRecord(**values))


def audit_snapshot_study_features(target, files, context, expected, *, context_anchor):
    expected = _exact(expected, FeatureVector)
    record = extract_snapshot_study_features(target, files, context, context_anchor=context_anchor)
    actual = record.features
    metadata = tuple(
        field
        for field in sorted(type(expected).model_fields)
        if field != "ast_features" and getattr(actual, field) != getattr(expected, field)
    )
    missing = tuple(sorted(expected.ast_features - actual.ast_features))
    unexpected = tuple(sorted(actual.ast_features - expected.ast_features))
    return seal(
        SnapshotStudyFeatureAudit(
            record=record,
            expected=expected,
            expected_digest=digest_bytes(canonical_json_bytes(expected)),
            matched=not (metadata or missing or unexpected),
            missing=missing,
            unexpected=unexpected,
            metadata_mismatches=metadata,
            artifact_digest=ZERO,
        )
    )


def verify_snapshot_study_feature_audit(target, files, context, audit):
    audit = _exact(audit, SnapshotStudyFeatureAudit)
    rebuilt = audit_snapshot_study_features(
        target, files, context, audit.expected, context_anchor=context.artifact_digest
    )
    require(audit == rebuilt, "snapshot_study_feature_audit_not_rebuilt")
    return rebuilt
