# CounterGuard

CounterGuard turns verified bug evidence into reusable regression guards with explicit
applicability boundaries.

> English · [中文](README.zh-CN.md)

MVP 0.1.0 covers the trusted local Python/pytest pipeline: bidirectional Evidence, minimal
Guard compilation, initial/refined Scope learning, Replay, and an offline Demo. See the
[architecture](docs/architecture.md), [frozen evaluation](docs/evaluation.md), and
[release/install procedure](docs/release.md). The [attack-surface checklist](docs/attack-surface-checklist.md)
distinguishes tested behavior from remaining risks and the requirements for untrusted repositories.
Historical verification has an explicit [version boundary](docs/known-limitations.md#历史验证结论的边界).

The wheel provides the CLI and library. Install the `runner` extra to execute tests; it declares
the pytest dependency already used by the project. The offline Demo also needs the source
distribution's examples, benchmarks, experiments and contract tests; these are not bundled in
the library wheel. No PyPI or GitHub publication is implied by local acceptance.

The local `v0.1.0` tag anchors the validated MVP, including the missing-runner install hint.
Its distributions live in `dist/v0.1.0-freeze/`; earlier D14 files retain their original hashes.
Without pytest, execution fails before output creation with exit 3 and an
`counterguard[runner]` installation hint. Both install choices are in the quickstart.

Start with the [offline quickstart](docs/quickstart.md). Although the scenario is named
`mvp.yaml`, it currently requires JSON syntax; YAML indentation, comments and anchors are
unsupported. The quickstart includes valid input and a real missing-contract `unknown` replay.

W3-A development adds [read-only repository inspection](docs/repository-inspection.md) with
explicit file/contract mappings. It reports affected/unaffected/unknown candidates and never
permits execution. This source feature is newer than the frozen v0.1.0 wheel; the
[security model](docs/security-model.md) keeps Docker and untrusted-code execution as W3-B work.

Day 3 now captures and verifies bidirectional bug Evidence. Each artifact records the selected
contract and test digests, target digests, structured case results, raw logs, and pytest exit
semantics. The capture service accepts only a real buggy test failure followed by a fixed pass as
reproduced Evidence. Day 4 compiles the failed cases into independent Guard assets and self-checks
them on the fixed target before publication. Day 5 freezes the experiment protocol, generates
baseline scopes, and executes both baselines on the nine training rows. Day 6 extracts AST features
without executing targets and audits all 15 frozen annotations. Day 7 fits initial and refined
scopes using the frozen training phases and independently audited module context.

Day 8 verifies that bundle and automatically decides applicability before starting pytest.
Pass, violation, inapplicable, unknown, and infrastructure failures are reported separately.

Day 9 evaluates all four frozen methods on holdout without refitting. Day 10 adds an offline
independent candidate boundary: recorded proposals reference authoritative contract cases,
trusted code renders the tests, and a Verification Gate promotes only real buggy failures
followed by fixed passes. This does not yet generate new oracle cases or call a live model.

```powershell
uv run counterguard capture --request examples/demo/requests/discount_agent.json --agent-source recorded --workspace artifacts/day10
uv run counterguard capture --request examples/demo/requests/query_agent.json --agent-source recorded --workspace artifacts/day10
uv run counterguard verification verify artifacts/day10/candidates/cnd_discount_agent_v1/gate.json
```

Completed requests are read-only on repeat; changed inputs require a new semantic request ID.
Untrusted Python and empty candidates are rejected before execution. Infrastructure errors
retain diagnostic runs under the candidate directory and never publish a verified Evidence.
New artifact paths, atomic temporary files and pytest caches must fit a 240 UTF-16-unit budget.

Day 11 runs that flow from clean inputs in an independent pinned workspace:

```powershell
uv run counterguard pipeline run --scenario examples/demo/mvp.yaml --workspace artifacts/pipeline-example-v1
uv run counterguard pipeline verify artifacts/pipeline-example-v1/run_manifest.json
```

The scenario uses JSON-compatible YAML and the frozen training members only. It builds both
Guards, fits initial and refined scopes, then demonstrates a real violation, a pass, and an
inapplicable target for each Guard. A successful Pipeline exits 0 while retaining those distinct
results; skipped targets never become passes. It does not execute holdout targets or copy old
artifacts. Completed workspaces are read-only; failures and changed inputs require a new output
version. Runtime artifacts use paths relative to the workspace's `w/`, while top-level manifest
links use the source project root.

Day 12 adds the one-command offline Demo and reports from the same JSON facts:

```powershell
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
uv run counterguard demo --workspace artifacts/quickstart-v1 --format json
uv run counterguard demo --workspace artifacts/quickstart-v1 --format markdown
uv run counterguard demo --workspace artifacts/quickstart-v1 --verify-only
```

The first command creates `report.json` and `report.md` alongside the Pipeline. Repeating it
only verifies and renders existing records. The report keeps `scope_decision`,
`execution_outcome`, and `final_verdict` separate: inapplicable/unknown produce
`not_run` + `skipped`, while infrastructure failures produce `inconclusive`. It shows the
minimal failed cases, initial/refined rules, actual clause checks and source links.
The default Demo uses recorded proposals and trusted local fixtures, with no network or
live model requirement. It does not provide a sandbox for arbitrary Python.

`capture`, `compile`, `learn` (alias of `scope learn`), `replay run`, and `evaluate`
(alias of `experiment evaluate`) accept `--format text|json|markdown`. Explicit formats
use `command-report.v1`: `payload` retains the original artifact, and `replays` contains
normalized execution conclusions when applicable. Without `--format`, existing commands
keep their original JSON shape; Demo defaults to text. Formatting does not change exit codes.
See [the CLI contract](docs/cli.md) for the schemas, state mapping and audit commands.

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

Contract metadata and module groups remain explicitly confirmed; AST features are now extracted
automatically and compared with the frozen manual annotations. Contract family acts as a
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
$env:COUNTERGUARD_TARGET = "examples.discount.implementations.final_price_v1_buggy"
uv run pytest tests/contract_tests/test_membership_discount_v1.py
Remove-Item Env:COUNTERGUARD_TARGET
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
$env:COUNTERGUARD_TARGET = "examples.validation.implementations.query_limit_v1_buggy"
uv run pytest tests/contract_tests/test_query_limit_v1.py
Remove-Item Env:COUNTERGUARD_TARGET
```

Legal v2 query parsers and v1 batch parsers are labeled inapplicable even though their signatures
and parsing structure are similar to the source guard.

## Development checks

```powershell
uv sync
uv run pytest -m "not slow" -q
uv run ruff check .
```

Daily checks use the fast tier. Before delivery, run the complete suite once:

```powershell
uv run pytest -q --durations=20
```

The unfiltered command still runs every test. Integration/e2e, heavy prepared fixtures and real
child processes are marked `slow`; run them directly by file when changing their behavior, or
use `uv run pytest -m slow -q`. Fast tests reject real process launches during fixture setup,
execution and teardown. Tier definitions and timing evidence are in [testing.md](docs/testing.md).

## Capture verified Evidence

Run from the repository root with the trusted example fixtures:

```powershell
uv run python scripts/prepare_scope_v1.py
uv run counterguard evidence verify artifacts/evidence/evd_discount_v1_member_rate_fix_v2/evidence.json
uv run counterguard evidence inventory
```

The preparation script captures both scenarios and compiles their Guards without modifying the
frozen protocol. On a clean checkout it first creates semantic v1 predecessors; in the existing
development workspace it uses the intact historical D4 records. Existing v2 assets are verified
and reused. The discount JSON has `reproduced=true`, buggy exit code `1`, fixed exit code `0`, and the failed cases
`member-price` and `member-rounding`. Both commands print machine-readable JSON. Repeating the same
capture verifies and reuses the existing artifact; changed inputs with the same identity are
rejected. Input and log references are relative to the selected workspace (`--cwd`).

New Evidence uses `evidence.v2`, with `capture_revision`, an explicit `supersedes` link, and
`recapture_reason`. New calendar suffixes are rejected. Legacy records retain their bytes and
digests. **Only `evidence verify` returning 0 makes Evidence usable**; a newer usable successor
removes the predecessor from default selection without making it invalid. Inventory reports each
state independently, and its successful exit means the inspection completed. See the
[lifecycle rules](docs/evidence-lifecycle.md) for recapture commands and historical retention.

CLI exit codes are `0` for reproduced Evidence, `1` for a completed but unreproduced attempt, `2`
for invalid inputs, `3` for execution failures, and `5` for artifact integrity failures. Pytest
exit codes `2` through `5`, missing or ambiguous case results, and timeouts cannot count as a
reproduced bug. Diagnostic Evidence is retained when a run fails to reproduce.

The Day 3 acceptance record is in [docs/progress/day3.md](docs/progress/day3.md). Generated runtime
artifacts under `artifacts/` are excluded from Git.

## Compile and directly replay a minimal Guard

```powershell
uv run counterguard compile --guard-id grd_discount_member_rate_regression_v2 --evidence artifacts/evidence/evd_discount_v1_member_rate_fix_v2/evidence.json --artifact-root artifacts
uv run counterguard guard verify artifacts/guards/grd_discount_member_rate_regression_v2/guard.json
uv run python -m counterguard guard run artifacts/guards/grd_discount_member_rate_regression_v2/guard.json --target examples.discount.implementations.final_price_v1_fixed:calculate_price
```

The discount Guard contains two assertions; the query-limit Guard contains the one zero-rejection
assertion. Each asset stores `guard.json` and a deterministic, standalone `test_guard.py`.
Full provenance auditing requires the source Evidence and logs; loading and directly running a
Guard does not require the historical contract file. Guard runs return `0` for pass, `1` for an
assertion failure, `3` for execution errors, and `5` for corrupted assets. These direct smoke runs
do not yet decide Scope applicability.

`python -m counterguard` and the installed console script share one CLI. The
[execution policy](docs/pytest-execution-policy.md) explains plugin/conftest loading and the explicit
exception whitelist. The [Day 4 record](docs/progress/day4.md) includes the completed acceptance
commands, artifact identities, and six direct replay results.

The current `guard-test.v2` generator gives an actionable configuration error when manually run
without `COUNTERGUARD_TARGET` or `COUNTERGUARD_SYMBOL`. Use `guard run --target module:symbol`
to supply them consistently. Old v1 assets remain auditable.

## Run the frozen training baselines

```powershell
uv run python scripts/prepare_scope_v1.py
uv run counterguard experiment verify --protocol experiments/scope_v1.json
uv run counterguard benchmark baselines --protocol experiments/scope_v1.json --split train
```

| Method | TP | FP | TN | FN | Guard executions |
|---|---:|---:|---:|---:|---:|
| B1 always | 4 | 5 | 0 | 0 | 9 |
| B2 interface | 4 | 3 | 2 | 0 | 7 |

Each applicable row actually executes its minimal Guard. The two skipped rows are `not_run`.
Scope counts are independent of execution outcomes: an inapplicable Guard remains a false
application even if its assertions pass. The command returns 0 when the frozen scope counts match
and no infrastructure errors occur; expected assertion failures are benchmark data.

Four immutable Scope artifacts and the report, predictions, and raw replay records are written
under `artifacts/scopes/scope-v1/` and `artifacts/experiments/scope-v1/train-baselines/`.
Definitions, sample membership, source text, and executable Guard meaning are pinned by digest;
fresh capture timestamps do not change the semantic pin, while full provenance is still audited.
The D5 command rejects holdout execution. Day 7 now implements the two frozen learned methods.
See the [Day 5 acceptance record](docs/progress/day5.md).

The [independent training derivation](docs/results/scope-v1/expected-train-derivation.md) lists
all nine rows: four applicable and five inapplicable. B2 rejects two interface mismatches while
retaining three inapplicable rows sharing the original interface. These counts do not depend on
whether the Guard assertions pass. The exact semantic digest field set and downstream usage are
documented in [data contracts](docs/data-contracts.md).

## Audit automatic AST features

```powershell
uv run counterguard features audit --benchmark-root benchmarks --output artifacts/audits/day6-feature-parity.json
```

The audit compares all 15 samples with the frozen annotations, including both splits, without
executing targets or passing applicability labels into extraction. Each row records missing and
unexpected tokens, metadata differences, and the source hashes of its feature record.
`branch:none` means an If/IfExp condition checks a formal parameter against Python `None` using
identity comparison. It does not mean no branch exists; plain computation can have no branch
token and an empty AST set. Unsupported target structures and syntax errors fail explicitly.

Same-input feature records and reports are deterministic. Changed source cannot overwrite the
same version/sample record. A mismatch exits 1; invalid annotation input exits 2; extraction
errors exit 3; immutable artifact conflicts exit 5. All errors retain a JSON report.
See the [feature contract](docs/data-contracts.md) and [Day 6 record](docs/progress/day6.md).

Module groups now come from `benchmarks/context/scope_v1.json`, not the expected annotations.
The [context policy](docs/module-context-policy.md) corrects the historical D6 interpretation:
duplicating a group in expected/actual did not independently audit it. FeatureRecord v2 records
the context pin. Audits preserve immutable historical reports and input snapshots; disputes follow
the [adjudication process](docs/feature-adjudication.md).

## Fit initial and refined scopes

```powershell
uv run python scripts/prepare_scope_v1.py
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase initial --output artifacts/experiments/scope-v1/fitted/learning-v2/initial
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase refined --output artifacts/experiments/scope-v1/fitted/learning-v2/refined
```

Both initial rules use `contract_version == v1`. Adding the two frozen legal counterexamples and
fully refitting produces version AND interface rules: `final_price` for discount and
`query_parameter` for input-limit. On all nine training rows, initial yields TP=4/FP=2/TN=3/FN=0;
refined yields TP=4/FP=0/TN=5/FN=0. These are scope classifications; D8 separately executes the
applicable Guards.

The pure solver receives only exact `TrainingExample` values containing a `FeatureVector` and
strict applicability bool. FeatureRecord, provenance dictionaries, identity fields, and leaking
subclasses are rejected. The fit wrapper separately verifies source-bug/fixed identities, a legal
counterexample, the frozen protocol/context, and fresh feature parity. Holdout never enters fit.

Twenty permutations preserve each pure learning result and digest. Persisted scopes and fit
manifests retain actual creation times and reuse the same bytes on repeat. Refused learning exits
4; schema/type input errors exit 2; artifact errors exit 5. See the [Day 7 record](docs/progress/day7.md).

Learning v2 exposes `predicate_count` and `combination_count`: discount is 8/92 and input-limit
is 10/175. Old v1 counts and digests remain readable. The new bundle directory prevents overwriting
historical D7 provenance. Dependency and recomputation rules are in [data contracts](docs/data-contracts.md).

The eager learner caches predicate coverage without changing candidate enumeration, ranking, or
learning bytes/digests. Optional clause-removal witnesses can be exported from an existing audited
fit without launching pytest or rewriting upstream artifacts:

```powershell
uv run python scripts/explain_fitted_scopes.py --fit artifacts/experiments/scope-v1/fitted/learning-v2/refined/fit-manifest.json --output artifacts/analyses/scope-explanations-v1/refined
```

Each certificate binds the original learning digest and training multiset, and lists the negative
feature vectors admitted if each clause is removed. It proves necessity relative to supplied labels;
it does not certify label correctness or generalization. Changed content needs a new output version.
Binary confusion counts reject unknown rather than counting it as inapplicable. See the
[methodology assessment](docs/research/methodology-transfer-2026-10-14.md) for lazy refinement,
mutation testing, and shrinking designs and limits.

## Run Scope-aware training replay

```powershell
uv run counterguard benchmark replay --protocol experiments/scope_v1.json --phase refined --split train
```

The expected exit code is **1**, because two applicable targets really violate their Guards.
The report is written first: 2 pass, 2 violation, 5 skipped_inapplicable, with exactly 4 pytest
processes. Every skipped row has `run=null`; unknown uses `skipped_unknown`, never inapplicable
or pass. D8 rejects holdout execution.

JSON and Markdown reports are under `artifacts/experiments/scope-v1/train-replays/refined/`.
Each immutable `artifacts/replays/<replay_id>/result.json` binds actual inputs and raw logs.
`replay verify <result.json>` audits current inputs without executing pytest; a successful audit
does not mean the recorded verdict was pass.

Individual replay can explicitly omit contract metadata to produce unknown without starting pytest:

```powershell
uv run counterguard replay run --guard artifacts/guards/grd_discount_member_rate_regression_v2/guard.json --scope artifacts/experiments/scope-v1/fitted/learning-v2/refined/grd_discount_member_rate_regression_v2.json --target examples.discount.implementations.final_price_v1_fixed:calculate_price
```

This returns 4 and preserves the missing-information reason. Supply `--contract` for the declared
target contract to evaluate it normally. Input integrity is checked before execution and again
afterward; changes during a run produce stale with the actual run preserved. See the
[Day 8 acceptance record](docs/progress/day8.md).

## Evaluate all four methods on the frozen holdout

```powershell
uv run counterguard experiment evaluate --protocol experiments/scope_v1.json --split holdout --fitted artifacts/experiments/scope-v1/fitted --output artifacts/experiments/scope-v1/final
uv run counterguard experiment verify --run artifacts/experiments/scope-v1/final
```

Evaluation consumes existing fits, executes the same six rows for all methods, and separately probes
both source bugs in both learned phases. Holdout metrics exclude these four source probes. Scope
and end-to-end metrics report per-Guard, micro and macro results, with explicit numerators,
denominators and null reasons. The query Guard has no held-out bug, so its Bug recall is null.

The frozen confusion policy counts unknown as a negative prediction and also reports its rate and
decision coverage. Raw results retain unknown; skipped cases never become passed tests.

Reports and raw replays are immutable. Reusing an output performs a read-only audit; a real repeat
needs a new output directory and retains fresh execution IDs/times. Only stable prediction/metric
projections are expected to have identical bytes. `evaluate` exits 0 when the experiment meets its
frozen acceptance, not when every Guard passes. `verify` checks evidence integrity without execution.
The six labels are already public, so this is engineering validation rather than a blind benchmark.
