# EvidenceGuard

EvidenceGuard turns verified bug evidence into reusable regression guards with explicit
applicability boundaries.

The MVP keeps two questions separate:

1. Does a guard apply to this code context?
2. If it applies, does the implementation violate the guard?

This repository currently contains the first executable fixture for that distinction. The
membership discount examples deliberately share similar signatures and code shapes while using
different contract versions or interface meanings.

## Current Day 1 acceptance case

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

## Development checks

```powershell
uv sync
uv run pytest
uv run ruff check .
```
