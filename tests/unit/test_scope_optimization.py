"""Differential checks against an independent, row-wise exhaustive search."""

import itertools
import json
import random
from pathlib import Path

import pytest

from evidenceguard.baselines import ConfusionCounts, ScopeClause
from evidenceguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from evidenceguard.errors import InsufficientScopeEvidence
from evidenceguard.predicates import VOCABULARY, FeatureVector
from evidenceguard.scope import ScopeLearningResult, TrainingExample, learn_scope
from tests.unit.test_scope import row

ORDER = (
    "contract_family",
    "contract_version",
    "interface_kind",
    "symbol_signature",
    "module_group",
    "ast_features",
)


def reference_search(examples):
    """Use sets of row indexes, without the production coverage/scoring helpers."""
    positive = {i for i, item in enumerate(examples) if item.guard_applicable}
    negative = set(range(len(examples))) - positive
    keys = set()
    for i in positive:
        features = examples[i].features
        keys.update((field, "eq", getattr(features, field)) for field in ORDER[:-1])
        keys.update(("ast_features", "contains", token) for token in features.ast_features)
    candidates = tuple(ScopeClause(field=f, op=o, value=v) for f, o, v in sorted(keys))

    def covered(clauses):
        return {
            i
            for i, item in enumerate(examples)
            if all(
                getattr(item.features, clause.field) == clause.value
                if clause.op == "eq"
                else clause.value in item.features.ast_features
                for clause in clauses
            )
        }

    supported = []
    tested = 0
    for size in (1, 2, 3):
        for clauses in itertools.combinations(candidates, size):
            tested += 1
            if covered(clauses) != positive:
                continue
            if all(covered(clauses[:i] + clauses[i + 1 :]) & negative for i in range(size)):
                supported.append(clauses)
    if not supported:
        return None
    clauses = min(
        supported,
        key=lambda rule: (
            len(rule),
            sum(c.field == "ast_features" for c in rule),
            tuple(sorted(ORDER.index(c.field) for c in rule)),
            canonical_json_bytes(rule),
        ),
    )
    draft = ScopeLearningResult(
        clauses=clauses,
        training_dataset_digest=digest_bytes(
            canonical_json_bytes(
                sorted(
                    [item.model_dump(mode="json") for item in examples],
                    key=canonical_json_bytes,
                )
            )
        ),
        training_confusion=ConfusionCounts(tp=len(positive), fp=0, tn=len(negative), fn=0),
        predicate_count=len(candidates),
        combination_count=tested,
        artifact_digest="sha256:" + "0" * 64,
    )
    return draft.model_copy(update={"artifact_digest": digest_json_artifact(draft)})


@pytest.mark.parametrize("seed", range(40))
def test_coverage_masks_preserve_full_payload_or_refusal_on_varied_datasets(seed):
    rng = random.Random(seed)
    tokens = tuple(VOCABULARY)[:4]
    features = {}
    for _ in range(12):
        item = FeatureVector(
            contract_family="family",
            contract_version=rng.choice(("v1", "v2")),
            interface_kind=rng.choice(("price", "amount")),
            symbol_signature=rng.choice(("a", "b")),
            module_group=rng.choice(("retail", "shared")),
            ast_features=frozenset(token for token in tokens if rng.choice((False, True))),
        )
        features[canonical_json_bytes(item)] = item
    items = tuple(features.values())
    examples = tuple(
        TrainingExample(features=item, guard_applicable=i < 2 or rng.choice((False, True)))
        for i, item in enumerate(items)
    ) + (TrainingExample(features=items[-1], guard_applicable=False),)
    # Avoid accidental conflicting labels, while retaining duplicate positive rows.
    examples = tuple(item for item in examples[:-1] if item.features != items[-1]) + examples[-1:]
    examples += (examples[0],)
    expected = reference_search(examples)
    if expected is None:
        with pytest.raises(InsufficientScopeEvidence) as error:
            learn_scope(examples)
        assert error.value.reason_code == "no_supported_rule"
    else:
        assert canonical_json_bytes(learn_scope(examples)) == canonical_json_bytes(expected)


def test_masks_cover_more_than_sixty_four_rows_and_three_necessary_clauses():
    examples = tuple(row(True) for _ in range(80)) + (
        row(False, contract_version="v2"),
        row(False, interface_kind="other"),
        row(False, module_group="other"),
    )
    assert canonical_json_bytes(learn_scope(examples)) == canonical_json_bytes(
        reference_search(examples)
    )
    assert len(learn_scope(examples).clauses) == 3


def test_predicate_matching_is_cached_once_per_candidate_and_training_row(monkeypatch):
    import evidenceguard.scope as scope

    calls = []
    original = scope._matches

    def tracked(clauses, features):
        calls.append(clauses)
        return original(clauses, features)

    monkeypatch.setattr(scope, "_matches", tracked)
    examples = (row(True), row(True), row(False, contract_version="v2"))
    result = learn_scope(examples)
    assert len(calls) == result.predicate_count * len(examples)
    assert all(len(clauses) == 1 for clauses in calls)
    assert result.combination_count == 25  # The full eager search still happened.


def test_both_frozen_phases_match_the_row_wise_reference_byte_for_byte():
    root = Path(__file__).resolve().parents[2]
    split = json.loads((root / "benchmarks/splits/scope_v1.json").read_bytes())
    samples = {
        item["sample_id"]: item
        for path in (root / "benchmarks/train").glob("*_scope_samples.json")
        for item in json.loads(path.read_bytes())
    }
    for phases in split["phases"].values():
        for ids in (phases["initial"], phases["initial"] + phases["refinement_additions"]):
            examples = tuple(
                TrainingExample(
                    features=FeatureVector.model_validate_json(
                        json.dumps(samples[sid]["features"])
                    ),
                    guard_applicable=samples[sid]["labels"]["guard_applicable"],
                )
                for sid in ids
            )
            assert canonical_json_bytes(learn_scope(examples)) == canonical_json_bytes(
                reference_search(examples)
            )
