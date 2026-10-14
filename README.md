# EvidenceGuard

EvidenceGuard turns verified bug evidence into reusable regression guards with explicit
applicability boundaries.

Day 3 now captures and verifies bidirectional bug Evidence. Each artifact records the selected
contract and test digests, target digests, structured case results, raw logs, and pytest exit
semantics. The capture service accepts only a real buggy test failure followed by a fixed pass as
reproduced Evidence. Day 4 compiles the failed cases into independent Guard assets and self-checks
them on the fixed target before publication. Baselines and scope learning are the next milestones.

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

The project follows frozen data contracts from evidence capture through evaluation.
It freezes the Evidence, Guard, feature, scope, replay, baseline, and evaluation contracts before
the learner consumes the holdout set. The current public fixtures provide engineering checks;
they are not a blind research evaluation.

All scope features are manually confirmed metadata at this stage. Contract family acts as a
trusted prefilter; the future learner will be evaluated on version and interface boundaries within
each family.

### Membership discount guard

The source contract for the discount Guard is `membership_discount` final-price at version `v1`:

- members pay 80% of the original amount;
- non-members pay the original amount;
- results use two decimal places and half-up rounding;
- negative amounts are rejected.

The compiled Guard retains the two member-price examples that failed on the source bug; the
remaining assertions stay in the full contract test.

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
Its compiled Guard retains only the zero-rejection regression assertion.
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

## Capture verified Evidence

Run from the repository root with the trusted example fixtures:

```powershell
uv run evidenceguard capture --evidence-id evd_discount_v1_member_rate_fix_d4 --contract examples/discount/contracts/membership_discount_final_price_v1.json --test tests/contract_tests/test_membership_discount_v1.py --buggy-target examples.discount.implementations.final_price_v1_buggy:calculate_price --fixed-target examples.discount.implementations.final_price_v1_fixed:calculate_price --artifact-root artifacts
uv run evidenceguard evidence verify artifacts/evidence/evd_discount_v1_member_rate_fix_d4/evidence.json
```

The JSON has `reproduced=true`, buggy exit code `1`, fixed exit code `0`, and the failed cases
`member-price` and `member-rounding`. Both commands print machine-readable JSON. Repeating the same
capture verifies and reuses the existing artifact; changed inputs with the same identity are
rejected. Input and log references are relative to the selected workspace (`--cwd`).

CLI exit codes are `0` for reproduced Evidence, `1` for a completed but unreproduced attempt, `2`
for invalid inputs, `3` for execution failures, and `5` for artifact integrity failures. Pytest
exit codes `2` through `5`, missing or ambiguous case results, and timeouts cannot count as a
reproduced bug. Diagnostic Evidence is retained when a run fails to reproduce.

The Day 3 acceptance record is in [docs/progress/day3.md](docs/progress/day3.md). Generated runtime
artifacts under `artifacts/` are excluded from Git.

## Compile and directly replay a minimal Guard

```powershell
uv run evidenceguard compile --guard-id grd_discount_member_rate_regression --evidence artifacts/evidence/evd_discount_v1_member_rate_fix_d4/evidence.json --artifact-root artifacts
uv run evidenceguard guard verify artifacts/guards/grd_discount_member_rate_regression/guard.json
uv run python -m evidenceguard guard run artifacts/guards/grd_discount_member_rate_regression/guard.json --target examples.discount.implementations.final_price_v1_fixed:calculate_price
```

The discount Guard contains two assertions; the query-limit Guard contains the one zero-rejection
assertion. Each asset stores `guard.json` and a deterministic, standalone `test_guard.py`.
Full provenance auditing requires the source Evidence and logs; loading and directly running a
Guard does not require the historical contract file. Guard runs return `0` for pass, `1` for an
assertion failure, `3` for execution errors, and `5` for corrupted assets. These direct smoke runs
do not yet decide Scope applicability.

`python -m evidenceguard` and the installed console script share one CLI. The
[execution policy](docs/pytest-execution-policy.md) explains plugin/conftest loading and the explicit
exception whitelist. The [Day 4 record](docs/progress/day4.md) includes the completed acceptance
commands, artifact identities, and six direct replay results.
