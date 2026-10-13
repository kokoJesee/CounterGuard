# EvidenceGuard

EvidenceGuard turns verified bug evidence into reusable regression guards with explicit
applicability boundaries.

The MVP keeps two questions separate:

1. Does a guard apply to this code context?
2. If it applies, does the implementation violate the guard?

The current benchmark contains two executable fixture families. The membership discount and
input-limit examples deliberately share signatures and code shapes within each family while using
different contract versions or interface meanings.

## Current Day 2 benchmark

There are 15 labeled scenarios: nine training samples and six holdout samples. Each guard has
applicable and inapplicable examples in both splits. The holdout implementations use code shapes
that are absent from training.

The scope features deliberately exclude contract IDs, paths, module names, target names, expected
outputs, and oracle values. A single version or interface predicate is insufficient for either
guard; both dimensions are needed to exclude the prepared legal counterexamples.

The precise field boundary and label semantics are documented in `benchmarks/README.md`. Notably,
the data includes an inapplicable target that violates its own contract, proving that applicability
cannot be inferred from target correctness.

All scope features are manually confirmed metadata at this stage. Contract family acts as a
trusted prefilter; the future learner will be evaluated on version and interface boundaries within
each family.

### Membership discount guard

The source guard is the `membership_discount` final-price contract at version `v1`:

- members pay 80% of the original amount;
- non-members pay the original amount;
- results use two decimal places and half-up rounding;
- negative amounts are rejected.

The same contract test passes for the fixed target:

```powershell
uv run pytest tests/contract_tests/test_membership_discount_v1.py
```

It fails reproducibly for the buggy target, which charges members 90%:

```powershell
$env:EVIDENCEGUARD_TARGET = "examples.discount.implementations.final_price_v1_buggy"
uv run pytest tests/contract_tests/test_membership_discount_v1.py
Remove-Item Env:EVIDENCEGUARD_TARGET
```

The benchmark labels under `benchmarks/` record guard applicability separately from contract
violation. Inapplicable samples always use `null` for `guard_violation`; this prevents a legal v2
implementation from being counted as a v1 violation.

### Query-limit validation guard

The source query contract defaults to 20, accepts only ASCII decimal digit strings whose values are
from 1 through 100, and rejects signed, padded, Unicode-digit, malformed, or out-of-range input.
The same contract test passes on the fixed parser:

```powershell
uv run pytest tests/contract_tests/test_query_limit_v1.py
```

It fails reproducibly on the source bug, which accidentally accepts zero:

```powershell
$env:EVIDENCEGUARD_TARGET = "examples.validation.implementations.query_limit_v1_buggy"
uv run pytest tests/contract_tests/test_query_limit_v1.py
Remove-Item Env:EVIDENCEGUARD_TARGET
```

Legal v2 query parsers and v1 batch parsers are labeled inapplicable even though their signatures
and parsing structure are similar to the source guard.

## Development checks

```powershell
uv sync
uv run pytest
uv run ruff check .
```
