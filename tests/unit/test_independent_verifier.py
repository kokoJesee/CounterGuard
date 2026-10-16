"""Candidate admission, context isolation and deterministic trusted rendering."""

import json
import random
from pathlib import Path

import pytest
from pydantic import ValidationError

from counterguard.digests import digest_bytes
from counterguard.independent_verifier import (
    AgentContext,
    CandidateTest,
    VerificationRequest,
    assess_candidate,
    propose_candidate,
    render_candidate,
)
from counterguard.model_client import MAX_RESPONSE_BYTES, RecordedModelClient
from counterguard.verification_gate import _context

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def context():
    request = VerificationRequest.model_validate_json(
        (ROOT / "examples/demo/requests/discount_agent.json").read_bytes()
    )
    return _context(request, ROOT)


def response():
    return json.loads((ROOT / "tests/fixtures/agent_responses/discount_v1.json").read_bytes())


def test_provider_receives_only_context_allowlist(context, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "KEY_MUST_STAY_OUT_OF_CONTEXT")

    class Spy:
        def generate(self, value):
            assert type(value) is AgentContext
            assert set(AgentContext.model_fields) == {
                "schema_version",
                "contract_ref",
                "contract_digest",
                "contract_json",
                "buggy_target",
                "buggy_target_digest",
                "buggy_source_code",
            }
            serialized = value.model_dump_json()
            assert "fixed_target" not in serialized
            assert "applicability_label" not in serialized
            assert "violation_label" not in serialized
            assert "expected_train" not in serialized
            assert "KEY_MUST_STAY_OUT_OF_CONTEXT" not in serialized
            return json.dumps(response()).encode()

    record = propose_candidate(
        Spy(),
        context,
        candidate_id="cnd_demo_v1",
        request_ref="request.json",
        request_digest=context.contract_digest,
        response_ref="response.json",
    )
    assert record.status == "admitted"
    assert record.created_at.utcoffset().total_seconds() == 0


@pytest.mark.parametrize("field", ["fixed_target", "benchmark_labels", "target_metrics"])
def test_context_type_rejects_extra_fields(context, field):
    with pytest.raises(ValidationError):
        AgentContext.model_validate({**context.model_dump(), field: "not allowed"})


def test_recorded_client_refuses_whole_request_before_reading():
    request = VerificationRequest.model_validate_json(
        (ROOT / "examples/demo/requests/discount_agent.json").read_bytes()
    )
    client = RecordedModelClient(ROOT / "nonexistent-response.json")
    with pytest.raises(TypeError, match="AgentContext only"):
        client.generate(request)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ({"test_code": "import os; os.remove('anything')"}, "candidate_schema"),
        ({"evidence_ref": "I_am_already_verified.json"}, "candidate_schema"),
        ({"expected": 0}, "candidate_schema"),
        ({"case_ids": []}, "candidate_schema"),
        ({"case_ids": ["member-price", "member-price"]}, "candidate_schema"),
        ({"case_ids": ["member-price"]}, "case_coverage"),
        ({"case_ids": ["unknown-case"]}, "case_coverage"),
        ({"contract_digest": "sha256:" + "0" * 64}, "contract_digest"),
    ],
)
def test_invalid_proposals_have_safe_reason_only(context, mutation, reason):
    candidate, actual = assess_candidate(json.dumps({**response(), **mutation}).encode(), context)
    assert candidate is None
    assert actual == reason


@pytest.mark.parametrize("raw", [b"{not json", b"\xff", b"[]", b"null"])
def test_malformed_responses_do_not_echo_the_input(context, raw):
    assert assess_candidate(raw, context) == (None, "candidate_schema")


def test_bounded_response(context):
    assert assess_candidate(b"x" * (MAX_RESPONSE_BYTES + 1), context) == (
        None,
        "response_too_large",
    )


def test_twenty_input_permutations_preserve_candidate_and_test_digest(context):
    original = response()
    expected = CandidateTest.model_validate_json(json.dumps(original))
    expected_test = render_candidate(expected, context)
    for seed in range(20):
        shuffled = list(original["case_ids"])
        random.Random(seed).shuffle(shuffled)
        candidate, reason = assess_candidate(
            json.dumps({**original, "case_ids": shuffled}).encode(), context
        )
        assert reason is None
        assert candidate == expected
        assert render_candidate(candidate, context) == expected_test
        assert digest_bytes(render_candidate(candidate, context)) == digest_bytes(expected_test)


def test_trusted_renderer_uses_original_oracle_and_no_builtins_lookup(context):
    candidate, _ = assess_candidate(json.dumps(response()).encode(), context)
    rendered = render_candidate(candidate, context).decode()
    assert "getattr(builtins" not in rendered
    assert '"expected":"80.00"' in rendered
    assert '"raises":"ValueError"' in rendered
