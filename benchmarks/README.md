# Benchmark data contract

Each sample keeps scope classification separate from contract execution.

- `features` is the complete and only feature input allowed for scope learning.
- `guard_applicable` is provided separately as a supervised target; it is never a feature.
- `contract_ref` and `target` are execution and traceability metadata.
- `labels.guard_applicable` says whether the named guard may run in the sample context.
- `labels.guard_violation` is `true` or `false` only when the guard applies; otherwise it is
  `null`.
- `labels.contract_compliant` describes the target against its own declared contract. It is an
  evaluation label and must never be passed to the Scope Learner.
- `labels.basis` records the human-readable reason for the confirmed label.

The Scope Learner must not receive sample IDs, paths, module or symbol names, contract IDs,
contract examples, expected outputs, violation/compliance labels, or basis text. Several of those fields contain
words such as `buggy`, `fixed`, `v1`, or `legal` and would leak the answer.

`ast_features` is currently a manually confirmed, presence-only summary using the controlled
vocabulary enforced by the test suite. It is not a serialized AST. Every operation represented by
the current vocabulary should be listed when it appears in the target. Day 6 now extracts the same
controlled vocabulary automatically and requires exact equality with these frozen annotations.
It never rewrites them to match the implementation.

The benchmark intentionally includes all four meaningful combinations that can exist:

| Guard applicable | Target compliant with own contract | Guard violation |
|---|---|---|
| yes | yes | false |
| yes | no | true |
| no | yes | null |
| no | no | null |

Training and holdout files are separate. Holdout samples may be used for evaluation only; they
must not participate in predicate generation, selection, tie-breaking, or threshold tuning.

The current benchmark treats `contract_family` as a trusted prefilter and learns the boundary
within one family. It therefore tests whether version and interface predicates can separate legal
counterexamples. Cross-family negatives require per-guard labels on the same sample and are left
for a later schema revision.

Day 4 compiles only the source Evidence's failed cases: two discount assertions and the zero-limit
rejection. The current independent identities are `grd_discount_member_rate_regression_v2` and
`grd_query_limit_zero_regression_v2`. An applicable Guard violation is measured by these minimal
assertions, separately from full-contract compliance. The existing 15 labels retain their values
after this migration; the integrity tests check the minimal assertions explicitly.

D5 freezes the four method definitions in `experiments/scope_v1.json`, with two-stage training and
holdout membership in `benchmarks/splits/scope_v1.json`. B1 always runs; B2 reads only
`interface_kind` and compares it with the frozen Guard interface. The D5 command executes only
training rows and rejects `--split holdout`. Protocol verification may audit holdout metadata and
source pins; these public fixtures are engineering checks, not a blind evaluation.

`branch:none` is the historical token name for an If/IfExp condition that compares a formal
parameter with Python `None` using `is` or `is not`. No qualifying condition means no such token;
it is never a fallback for the absence of branches. Full boundaries are in `docs/data-contracts.md`.
The nine-row manual baseline derivation is in
`docs/results/scope-v1/expected-train-derivation.md`.

`module_group` is independently derived from the reviewed architectural package mapping in
`context/scope_v1.json`; the frozen group pin is verified before D7 fit. Expected group annotations
are compared with this source rather than copied. Changes require a new context/protocol version.
`docs/module-context-policy.md` records the D6 correction, and `docs/feature-adjudication.md`
defines how annotation errors are independently reviewed without rewriting frozen results.
