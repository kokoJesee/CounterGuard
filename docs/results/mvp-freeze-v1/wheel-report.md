# EvidenceGuard demo

pipeline: artifacts/wd/run_manifest.json
artifact_digest: sha256:00add6db420e3f212c3f2b70b6acaa3795176c6c4b70f96664a80ff106ec24bb

Command completion/acceptance is separate from individual test results.
skipped and unknown are never counted as pass.

scenario: scope_v1_offline_v1
run_id: pip_5fe5d1fb008b448884b1cbf1f78bfa76
demo accepted: true
Replay executions: 4
verdict_counts: {"pass": 2, "skipped_inapplicable": 2, "violation": 2}

| Guard / sample | scope_decision | execution_outcome | final_verdict | raw_verdict | reason / failed cases |
|---|---|---|---|---|---|
| grd_discount_member_rate_regression_v2 / train-v1-discount-amount | inapplicable | not_run | skipped | skipped_inapplicable | - |
| grd_discount_member_rate_regression_v2 / train-v1-fixed | applicable | pass | pass | pass | - |
| grd_discount_member_rate_regression_v2 / train-v1-source-bug | applicable | fail | violation | violation | member-price, member-rounding |
| grd_query_limit_zero_regression_v2 / train-batch-v1-legal | inapplicable | not_run | skipped | skipped_inapplicable | - |
| grd_query_limit_zero_regression_v2 / train-query-v1-fixed | applicable | pass | pass | pass | - |
| grd_query_limit_zero_regression_v2 / train-query-v1-source-bug | applicable | fail | violation | violation | below-minimum |

## Scope refinement

grd_discount_member_rate_regression_v2
minimal failed cases: member-price, member-rounding
initial: contract_version eq v1
refined: contract_version eq v1 AND interface_kind eq final_price
evidence: artifacts/wd/w/artifacts/evidence/evd_discount_agent_v1/evidence.json
gate: artifacts/wd/w/artifacts/candidates/cnd_discount_agent_v1/gate.json
guard: artifacts/wd/w/artifacts/guards/grd_discount_member_rate_regression_v2/guard.json
initial_learning: artifacts/wd/w/artifacts/fitted/initial/grd_discount_member_rate_regression_v2.learning.json
initial_scope: artifacts/wd/w/artifacts/fitted/initial/grd_discount_member_rate_regression_v2.json
refined_learning: artifacts/wd/w/artifacts/fitted/refined/grd_discount_member_rate_regression_v2.learning.json
refined_scope: artifacts/wd/w/artifacts/fitted/refined/grd_discount_member_rate_regression_v2.json

grd_query_limit_zero_regression_v2
minimal failed cases: below-minimum
initial: contract_version eq v1
refined: contract_version eq v1 AND interface_kind eq query_parameter
evidence: artifacts/wd/w/artifacts/evidence/evd_query_agent_v1/evidence.json
gate: artifacts/wd/w/artifacts/candidates/cnd_query_agent_v1/gate.json
guard: artifacts/wd/w/artifacts/guards/grd_query_limit_zero_regression_v2/guard.json
initial_learning: artifacts/wd/w/artifacts/fitted/initial/grd_query_limit_zero_regression_v2.learning.json
initial_scope: artifacts/wd/w/artifacts/fitted/initial/grd_query_limit_zero_regression_v2.json
refined_learning: artifacts/wd/w/artifacts/fitted/refined/grd_query_limit_zero_regression_v2.learning.json
refined_scope: artifacts/wd/w/artifacts/fitted/refined/grd_query_limit_zero_regression_v2.json

Frozen training examples; not a new holdout evaluation.

### grd_discount_member_rate_regression_v2 / train-v1-discount-amount

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq final_price; actual=discount_amount; matched=False
- replay: artifacts/wd/w/artifacts/replays/rpl_90767fba2cae497bba0509c1f5d9f14a/result.json

### grd_discount_member_rate_regression_v2 / train-v1-fixed

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq final_price; actual=final_price; matched=True
- replay: artifacts/wd/w/artifacts/replays/rpl_6d5b7bbeaf034ab68ed7226cce56e1a2/result.json

### grd_discount_member_rate_regression_v2 / train-v1-source-bug

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq final_price; actual=final_price; matched=True
- replay: artifacts/wd/w/artifacts/replays/rpl_92d64309eaec4e7da7452787043d7b50/result.json

### grd_query_limit_zero_regression_v2 / train-batch-v1-legal

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq query_parameter; actual=worker_batch; matched=False
- replay: artifacts/wd/w/artifacts/replays/rpl_cc8b2bcefa664f0d85bd046df27edcc8/result.json

### grd_query_limit_zero_regression_v2 / train-query-v1-fixed

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq query_parameter; actual=query_parameter; matched=True
- replay: artifacts/wd/w/artifacts/replays/rpl_994112a36a694da98f34393d0208b608/result.json

### grd_query_limit_zero_regression_v2 / train-query-v1-source-bug

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq query_parameter; actual=query_parameter; matched=True
- replay: artifacts/wd/w/artifacts/replays/rpl_3adc186cf36c4b7cb396af23df0823a6/result.json
