# Benchmark data contract

Each sample keeps scope classification separate from contract execution.

- `features` is the complete and only input allowed for scope learning.
- `contract_ref` and `target` are execution and traceability metadata.
- `labels.guard_applicable` says whether the named guard may run in the sample context.
- `labels.guard_violation` is `true` or `false` only when the guard applies; otherwise it is
  `null`.
- `labels.contract_compliant` describes the target against its own declared contract. It is an
  evaluation label and must never be passed to the Scope Learner.
- `labels.basis` records the human-readable reason for the confirmed label.

The Scope Learner must not receive sample IDs, paths, module or symbol names, contract IDs,
contract examples, expected outputs, label fields, or basis text. Several of those fields contain
words such as `buggy`, `fixed`, `v1`, or `legal` and would leak the answer.

`ast_features` is currently a manually confirmed, presence-only summary using the controlled
vocabulary enforced by the test suite. It is not a serialized AST. Every operation represented by
the current vocabulary should be listed when it appears in the target. Production AST extraction
is intentionally deferred to the feature-extraction milestone.

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

For these initial fixtures, each Guard replays the full declared contract, so an applicable Guard
violation currently equals failure of the target's own contract. Future Guards may encode only one
regression property; at that point Guard execution and full-contract compliance must be measured
independently.
