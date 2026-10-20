"""Independent syntax goldens and feature-only research learning; no target execution."""

import json
import random
import subprocess
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from counterguard.digests import canonical_json_bytes, digest_bytes
from counterguard.errors import (
    ArtifactIntegrityError,
    FeatureExtractionError,
    InsufficientScopeEvidence,
)
from counterguard.features import extract_ast_features
from counterguard.predicates import VOCABULARY_DIGEST, FeatureVector
from counterguard.scope import TrainingExample, learn_scope
from counterguard.standalone_capture import ZERO, _seal
from counterguard.study_features import (
    VOCABULARY_PIN,
    StudyFeatureContext,
    StudyFeatureRecord,
    audit_study_features,
    extract_study_features,
    study_training_example,
    verify_study_feature_audit,
    verify_study_feature_record,
)
from scripts.audit_study_features import main as feature_command

SHAPE = (
    "parameter-shape.study.v1:posonly=0;poskw=1;defaults=0;vararg=0;kwonly=0;kwdefaults=;varkw=0"
)

# Hand-written before calling the extractor; exact sets, not just token membership.
GOLDENS = (
    ("plain", "def target(x):\n return x + 1", ()),
    ("none", "def target(x):\n return 1 if x is None else 0", ("branch:none",)),
    (
        "for-range",
        "def target(x):\n for value in x:\n  if value < 0 or value > 255:\n   return 0\n return 1",
        ("range:check",),
    ),
    ("generator-range", "def target(x):\n return all(0 <= v <= 255 for v in x)", ("range:check",)),
    (
        "generator-filter",
        "def target(x):\n return (v for v in x if x is not None)",
        ("branch:none",),
    ),
    ("parse", "def target(x):\n return int(x)", ("int:parse",)),
    ("multiply", "def target(x):\n return x * 2", ("decimal:multiply",)),
    ("subtract", "def target(x):\n return x - 2", ("decimal:subtract",)),
    ("ascii", "def target(x):\n return x.isascii()", ("str:isascii",)),
    ("decimal", "def target(x):\n return x.isdecimal()", ("str:isdecimal",)),
    (
        "regex",
        "import re\ndef target(x):\n return re.fullmatch('[0-9]+', x)",
        ("regex:ascii_digits",),
    ),
    (
        "round",
        "from decimal import ROUND_HALF_UP\ndef target(x):\n return ROUND_HALF_UP",
        ("round:half_up",),
    ),
    (
        "no-helper-inline",
        "def helper(x):\n return all(0 <= v <= 255 for v in x)\ndef target(x):\n return helper(x)",
        (),
    ),
)


@pytest.fixture(autouse=True)
def no_process(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Study feature checks must not launch Git, Docker or any process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)


def context(source, **updates):
    values = dict(
        context_id="fixture-context",
        created_at=datetime.now(UTC),
        operator="fixture reviewer",
        reason="Explicit tool-owned syntax fixture review",
        metadata_basis="Fixture specification: value-returning validation helper in rgb module",
        source_ref="src/fixture/core.py",
        source_digest=digest_bytes(source),
        symbol="target",
        contract_family="rgb",
        contract_version="v2",
        interface_kind="value_return",
        module_group="validation",
        artifact_digest=ZERO,
    )
    return _seal(StudyFeatureContext(**(values | updates)))


def extract(text, **metadata):
    source = text.encode()
    review = context(source, **metadata)
    return extract_study_features(source, review, context_anchor=review.artifact_digest)


def golden(tokens):
    return FeatureVector(
        contract_family="rgb",
        contract_version="v2",
        interface_kind="value_return",
        symbol_signature=SHAPE,
        module_group="validation",
        ast_features=frozenset(tokens),
    )


@pytest.mark.parametrize("name,text,tokens", GOLDENS, ids=[r[0] for r in GOLDENS])
def test_independent_goldens_match_every_feature_and_supply_line_witnesses(name, text, tokens):
    source = text.encode()
    review = context(source)
    audit = audit_study_features(
        source, review, golden(tokens), context_anchor=review.artifact_digest
    )
    assert audit.matched
    assert audit.missing == audit.unexpected == audit.metadata_mismatches == ()
    assert {w.token for w in audit.record.witnesses} == set(tokens)
    for witness in audit.record.witnesses:
        assert witness.line <= witness.end_line <= len(text.splitlines())
    assert (
        verify_study_feature_audit(audit, source, review, context_anchor=review.artifact_digest)
        == audit
    )
    assert StudyFeatureRecord.model_validate_json(audit.record.model_dump_json()) == audit.record


@pytest.mark.parametrize(
    "text,tokens",
    [
        ("def target(x):\n return (int(v) for int in x for v in x)", ()),
        ("def target(x):\n values = (int for int in x)\n return int(x)", ("int:parse",)),
        ("def target(x):\n return (v for int in int(x) for v in x)", ("int:parse",)),
        ("def target(x):\n return (v for v in x for int in int(x))", ()),
        ("def target(x):\n for int in x:\n  pass\n return int(x)", ()),
        (
            "import re\ndef target(x):\n return (re.fullmatch('[0-9]', v) for re in x for v in x)",
            (),
        ),
        (
            "import re\ndef target(x):\n unused = (re for re in x)\n"
            " return re.fullmatch('[0-9]', x)",
            ("regex:ascii_digits",),
        ),
        ("def target(x):\n return (v for x in x for v in x if x is None)", ()),
        ("def target(x):\n return ((int(v) for v in y) for int in x for y in x)", ()),
        ("def target(x):\n return (v for (int, v) in x if int(v))", ()),
    ],
)
def test_generator_and_for_lexical_scopes_do_not_leak_or_hide_outer_iterables(text, tokens):
    assert extract(text).features.ast_features == frozenset(tokens)


def test_parameter_shadowing_and_generator_filter_condition_are_explicit():
    assert extract(
        "def target(is_member):\n return (v for v in () if is_member)"
    ).features.ast_features == {"branch:is_member"}
    assert not extract(
        "def target(is_member):\n return (v for is_member in () for v in () if is_member)"
    ).features.ast_features


@pytest.mark.parametrize(
    "text",
    [
        "def target(x):\n return all(v < 0 for v in x) or all(v > 255 for v in x)",
        "def target(x):\n if any(v < 0 for v in x) or any(v > 255 for v in x): return 1\n return 0",
        "def target(x):\n return (v for v in x if v < 0 if v > 255)",
        "def target(x):\n return (v < 0 for v in x if v > 255)",
        "def target(x):\n for v in x:\n  if v < 0: return 1\n  if v > 255: return 2\n return 0",
    ],
)
def test_incomplete_bounds_in_different_conditions_or_generators_never_merge(text):
    assert "range:check" not in extract(text).features.ast_features


@pytest.mark.parametrize(
    "text",
    [
        "def target(x):\n return [int(v) for v in x]",
        "def target(x):\n return {int(v) for v in x}",
        "def target(x):\n return (v for v in x if (y := v))",
        "def target(x):\n while x:\n  x -= 1\n return x",
        "def target(x):\n try: return int(x)\n except ValueError: return 0",
        "def target(x):\n def helper(): return 1\n return helper()",
        "def target(x):\n return lambda: int(x)",
        "def target(x):\n import re\n return x",
        "def target(x):\n del x\n return 0",
        "def target(x):\n for x.value in ():\n  pass\n return x",
        "def target(x):\n return (v for x.value in ())",
        "@wrap\ndef target(x):\n return x",
        "async def target(x): return x",
        "def target(x, x): return x",
        "def target(x): return x\ndef target(x): return x",
        "def target[int](x): return int(x)",
        "def target(x):\n type Alias = int\n return x",
        "def another(x): return x",
        "def target(: return 0",
    ],
)
def test_unreviewed_constructs_are_unknown_never_successful_empty_features(text):
    with pytest.raises(FeatureExtractionError):
        extract(text)


def test_syntax_budgets_fail_before_any_feature_record(monkeypatch):
    import counterguard.study_features as module

    monkeypatch.setattr(module, "MAX_SOURCE_BYTES", 12)
    with pytest.raises(FeatureExtractionError, match="byte_budget"):
        extract("def target(x): return x")
    monkeypatch.setattr(module, "MAX_SOURCE_BYTES", 4096)
    monkeypatch.setattr(module, "MAX_NODES", 3)
    with pytest.raises(FeatureExtractionError, match="ast_budget"):
        extract("def target(x): return x")
    monkeypatch.setattr(module, "MAX_NODES", 16000)
    monkeypatch.setattr(module, "MAX_DEPTH", 2)
    with pytest.raises(FeatureExtractionError, match="ast_budget"):
        extract("def target(x): return x")
    monkeypatch.setattr(module, "MAX_DEPTH", 80)
    monkeypatch.setattr(module, "MAX_GENERATORS", 1)
    with pytest.raises(FeatureExtractionError, match="generator_depth"):
        extract("def target(x): return ((v for v in y) for y in x)")


def test_module_statements_and_defaults_are_parsed_but_never_executed(tmp_path):
    sentinel = tmp_path / "target-executed"
    text = (
        f"open({str(sentinel)!r}, 'w').write('bad')\n"
        "def target(x=1*2):\n return x\nraise SystemExit(90)"
    )
    assert not extract(text).features.ast_features
    assert not sentinel.exists()


def test_signature_is_derived_shape_without_names_defaults_annotations_or_labels():
    first = extract("def target(x: int=99, /, *args, y=None, **kwargs) -> str: return x")
    second = extract("def target(other=42, /, *rest, different=False, **options): return other")
    assert (
        first.features.symbol_signature
        == second.features.symbol_signature
        == (
            "parameter-shape.study.v1:posonly=1;poskw=0;defaults=1;vararg=1;"
            "kwonly=1;kwdefaults=1;varkw=1"
        )
    )
    assert first.source_digest != second.source_digest


def test_metadata_is_reviewed_context_not_annotation_or_outcome_and_anchor_is_required():
    source = b"def target(x): return x"
    review = context(source)
    record = extract_study_features(source, review, context_anchor=review.artifact_digest)
    changed = _seal(review.model_copy(update={"interface_kind": "stdout_write"}))
    with pytest.raises(ArtifactIntegrityError, match="anchor"):
        extract_study_features(source, changed, context_anchor=review.artifact_digest)
    with pytest.raises(ArtifactIntegrityError, match="source_digest"):
        extract_study_features(source + b"\n", review, context_anchor=review.artifact_digest)
    bad = _seal(
        record.model_copy(
            update={"features": golden(("int:parse",)), "witnesses": record.witnesses}
        )
    )
    with pytest.raises(ValidationError):
        verify_study_feature_record(bad, source, review, context_anchor=review.artifact_digest)
    bad = _seal(record.model_copy(update={"implementation_digests": {"fake.py": ZERO}}))
    with pytest.raises(ArtifactIntegrityError, match="does_not_rebuild"):
        verify_study_feature_record(bad, source, review, context_anchor=review.artifact_digest)


def test_mismatch_preserves_both_sides_and_cannot_be_resigned_as_matched():
    source = b"def target(x): return int(x)"
    review = context(source)
    expected = golden(("branch:none",)).model_copy(update={"module_group": "manual-group"})
    audit = audit_study_features(source, review, expected, context_anchor=review.artifact_digest)
    assert not audit.matched
    assert audit.expected == expected
    assert audit.record.features.ast_features == {"int:parse"}
    assert audit.missing == ("branch:none",)
    assert audit.unexpected == ("int:parse",)
    assert audit.metadata_mismatches == ("module_group",)
    bad = _seal(audit.model_copy(update={"matched": True, "missing": (), "unexpected": ()}))
    with pytest.raises(ArtifactIntegrityError, match="does_not_rebuild"):
        verify_study_feature_audit(bad, source, review, context_anchor=review.artifact_digest)


def test_inner_feature_projection_rejects_records_subclasses_labels_and_construct_bypasses():
    record = extract("def target(x): return x")
    assert type(study_training_example(record.features, True)) is TrainingExample
    for wrong in (record, record.model_dump(), record.features.model_dump()):
        with pytest.raises(TypeError):
            study_training_example(wrong, True)

    class LeakyVector(FeatureVector):
        source_id: str = "forbidden"

    leaked = LeakyVector.model_validate_json(record.features.model_dump_json())
    with pytest.raises(TypeError):
        study_training_example(leaked, True)
    with pytest.raises(TypeError):
        study_training_example(record.features, 1)
    with pytest.warns(UserWarning, match="serializer warnings"), pytest.raises(ValidationError):
        study_training_example(record.features.model_copy(update={"module_group": 99}), True)
    assert set(type(study_training_example(record.features, True).features).model_fields) == {
        "contract_family",
        "contract_version",
        "interface_kind",
        "symbol_signature",
        "module_group",
        "ast_features",
    }


def test_original_learner_determinism_zero_errors_and_counterexample_support_are_retained():
    base = extract("def target(x): return x").features
    positives = tuple(
        study_training_example(base.model_copy(update={"module_group": group}), True)
        for group in ("one", "two")
    )
    initial_negative = study_training_example(
        base.model_copy(update={"contract_version": "v1"}), False
    )
    addition = study_training_example(
        base.model_copy(update={"interface_kind": "stdout_write"}), False
    )
    initial = learn_scope((*positives, initial_negative))
    rows = [*positives, initial_negative, addition]
    refined = learn_scope(tuple(rows))
    assert [(c.field, c.value) for c in initial.clauses] == [("contract_version", "v2")]
    assert [(c.field, c.value) for c in refined.clauses] == [
        ("contract_version", "v2"),
        ("interface_kind", "value_return"),
    ]
    assert refined.training_confusion.model_dump() == {"tp": 2, "fp": 0, "tn": 2, "fn": 0}
    for seed in range(20):
        random.Random(seed).shuffle(rows)
        assert learn_scope(tuple(rows)) == refined
    for clause in refined.clauses:
        reduced = [c for c in refined.clauses if c != clause]
        assert any(
            not row.guard_applicable
            and all(getattr(row.features, c.field) == c.value for c in reduced)
            for row in rows
        )
    with pytest.raises(InsufficientScopeEvidence, match="counterexample"):
        learn_scope(positives)
    with pytest.raises(TypeError):
        learn_scope((extract("def target(x): return x"),))


def test_new_versions_do_not_make_frozen_extractor_accept_loops_or_generators():
    assert VOCABULARY_PIN != VOCABULARY_DIGEST
    for source in (
        "def target(x):\n for v in x: pass\n return x",
        "def target(x): return (v for v in x)",
    ):
        with pytest.raises(FeatureExtractionError):
            extract_ast_features(source, "target")
        assert extract(source).extractor == "ast-features.study.v1"


def test_context_does_not_accept_truth_labels_or_protocol_extensions():
    source = b"def target(x): return x"
    for field in (
        "guard_applicable",
        "guard_violation",
        "split",
        "expected_ast_features",
        "fit_ref",
    ):
        with pytest.raises(ValidationError):
            StudyFeatureContext.model_validate_json(
                json.dumps(context(source).model_dump(mode="json") | {field: True})
            )
    for field in ("operator", "reason", "metadata_basis"):
        with pytest.raises(ValidationError):
            context(source, **{field: "  "})


def command_fixture(tmp_path):
    source = b"def target(x): return int(x)"
    review = context(source, source_ref="target.py")
    (tmp_path / "target.py").write_bytes(source)
    (tmp_path / "context.json").write_bytes(canonical_json_bytes(review))
    (tmp_path / "expected.json").write_bytes(canonical_json_bytes(golden(("int:parse",))))
    return review, [
        "--workspace",
        str(tmp_path),
        "--context",
        "context.json",
        "--context-digest",
        review.artifact_digest,
    ]


def test_static_cli_audit_idempotence_mismatch_and_no_overwrite(tmp_path, capsys):
    _, args = command_fixture(tmp_path)
    args += ["--expected", "expected.json", "--output", "audit.json"]
    assert feature_command(args) == 0
    assert json.loads(capsys.readouterr().out)["matched"]
    raw = (tmp_path / "audit.json").read_bytes()
    assert feature_command(args) == 0
    capsys.readouterr()
    (tmp_path / "expected.json").write_bytes(canonical_json_bytes(golden(())))
    assert feature_command(args) == 5
    assert (tmp_path / "audit.json").read_bytes() == raw
    capsys.readouterr()
    args[-1] = "mismatch.json"
    assert feature_command(args) == 4
    assert not json.loads(capsys.readouterr().out)["matched"]


def test_static_cli_unknown_and_integrity_diagnostics_are_finite(tmp_path, capsys):
    _, args = command_fixture(tmp_path)
    args += ["--output", "record.json"]
    (tmp_path / "target.py").write_bytes(b"bad source")
    assert feature_command(args) == 5
    assert json.loads(capsys.readouterr().out)["reason_code"] == "study_feature_input_invalid"
    source = b"def target(x): return [v for v in x]"
    review = context(source, source_ref="target.py")
    (tmp_path / "target.py").write_bytes(source)
    (tmp_path / "context.json").write_bytes(canonical_json_bytes(review))
    args[5] = review.artifact_digest
    assert feature_command(args) == 4
    assert json.loads(capsys.readouterr().out)["reason_code"] == "study_feature_syntax_unsupported"
    assert not (tmp_path / "record.json").exists()


def test_static_cli_rejects_output_escape_and_symlink_input(tmp_path, capsys):
    _, args = command_fixture(tmp_path)
    assert feature_command(args + ["--output", "../escape.json"]) == 5
    capsys.readouterr()
    # Do not require platform-specific symlink privileges: reject_links already has its own suite.
    import counterguard.standalone_capture as capture

    original = capture.reject_links

    def deny_source(path):
        if path.name == "context.json":
            raise ValueError("synthetic link")
        return original(path)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(capture, "reject_links", deny_source)
        assert feature_command(args + ["--output", "record.json"]) == 5
    assert not (tmp_path / "record.json").exists()


def test_resigned_witness_lines_and_metadata_still_require_independent_rebuild():
    source = b"def target(x):\n return int(x)\n"
    review = context(source)
    record = extract_study_features(source, review, context_anchor=review.artifact_digest)
    for updates in (
        {"witnesses": (record.witnesses[0].model_copy(update={"line": 1}),)},
        {"features": record.features.model_copy(update={"module_group": "false-group"})},
        {"vocabulary_digest": ZERO},
        {"artifact_digest": ZERO},
    ):
        bad = record.model_copy(update=updates)
        if "artifact_digest" not in updates:
            bad = _seal(bad)
        with pytest.raises(ArtifactIntegrityError, match="does_not_rebuild"):
            verify_study_feature_record(bad, source, review, context_anchor=review.artifact_digest)


def test_new_algorithm_agrees_on_the_old_algorithms_supported_golden_subset():
    for name, source, tokens in GOLDENS:
        if name not in {"for-range", "generator-range", "generator-filter"}:
            assert extract_ast_features(source, "target") == frozenset(tokens)
            assert extract(source).features.ast_features == frozenset(tokens)


def test_local_annotations_supply_no_tokens_but_their_values_still_do():
    assert not extract("def target(x):\n local: int(x)\n return x").features.ast_features
    assert extract(
        "def target(x):\n local: object = int(x)\n return local"
    ).features.ast_features == {"int:parse"}


def test_module_conditional_imports_and_definitions_cannot_impersonate_library_bindings():
    for source in (
        "if choice:\n from custom import int\ndef target(x): return int(x)",
        "import re\nif choice:\n import custom as re\n"
        "def target(x): return re.fullmatch('[0-9]', x)",
        "if choice:\n def int(x): return x\ndef target(x): return int(x)",
    ):
        assert not extract(source).features.ast_features
    with pytest.raises(FeatureExtractionError, match="star_binding"):
        extract("from custom import *\ndef target(x): return int(x)")
    # A method's local import does not change module bindings.
    assert extract(
        "class Box:\n def method(self):\n  from custom import int\ndef target(x): return int(x)"
    ).features.ast_features == {"int:parse"}
