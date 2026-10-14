"""The documented semantic projection must remain distinct from full provenance."""

from datetime import timedelta

from evidenceguard.digests import canonical_json_bytes, digest_bytes
from evidenceguard.models import Guard
from evidenceguard.protocol import GUARD_SEMANTIC_FIELDS, guard_semantic_digest
from tests.unit.test_guard import guard_payload
from tests.unit.test_models import SHA_C


def test_semantic_projection_contains_exactly_the_nine_documented_fields():
    assert GUARD_SEMANTIC_FIELDS == (
        "guard_id",
        "guard_version",
        "contract_id",
        "target_interface",
        "argument_types",
        "return_type",
        "cases",
        "generator_version",
        "test_digest",
    )
    guard = Guard.model_validate(guard_payload())
    projection = {field: getattr(guard, field) for field in GUARD_SEMANTIC_FIELDS}
    assert guard_semantic_digest(guard) == digest_bytes(canonical_json_bytes(projection))


def test_capture_identity_time_and_source_hashes_do_not_change_semantic_digest():
    guard = Guard.model_validate(guard_payload())
    recaptured = guard.model_copy(
        update={
            "created_at": guard.created_at + timedelta(days=1),
            "source_evidence_id": "evd_revision_v2",
            "source_evidence_ref": "artifacts/evidence/evd_revision_v2/evidence.json",
            "source_evidence_digest": SHA_C,
            "source_buggy_digest": SHA_C,
            "contract_digest": SHA_C,
            "artifact_digest": SHA_C,
        }
    )
    assert guard_semantic_digest(guard) == guard_semantic_digest(recaptured)


def test_executable_or_identity_changes_do_change_semantic_digest():
    guard = Guard.model_validate(guard_payload())
    for update in (
        {"guard_id": "grd_new"},
        {"guard_version": 2},
        {"test_digest": SHA_C},
        {"generator_version": "guard-test.v1"},
    ):
        assert guard_semantic_digest(guard) != guard_semantic_digest(
            guard.model_copy(update=update)
        )
