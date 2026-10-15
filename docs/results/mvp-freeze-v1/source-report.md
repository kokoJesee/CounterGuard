# EvidenceGuard demo

pipeline: artifacts/freeze-demo/run_manifest.json
artifact_digest: sha256:171c5811af2f52c03ddf0fd7a4a435d845cd5a15cdb4f431175f62a3a6bb7021

Command completion/acceptance is separate from individual test results.
skipped and unknown are never counted as pass.

scenario: scope_v1_offline_v1
run_id: pip_5734999652d74f30ba2aa7a47961576d
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
evidence: artifacts/freeze-demo/w/artifacts/evidence/evd_discount_agent_v1/evidence.json
gate: artifacts/freeze-demo/w/artifacts/candidates/cnd_discount_agent_v1/gate.json
guard: artifacts/freeze-demo/w/artifacts/guards/grd_discount_member_rate_regression_v2/guard.json
initial_learning: artifacts/freeze-demo/w/artifacts/fitted/initial/grd_discount_member_rate_regression_v2.learning.json
initial_scope: artifacts/freeze-demo/w/artifacts/fitted/initial/grd_discount_member_rate_regression_v2.json
refined_learning: artifacts/freeze-demo/w/artifacts/fitted/refined/grd_discount_member_rate_regression_v2.learning.json
refined_scope: artifacts/freeze-demo/w/artifacts/fitted/refined/grd_discount_member_rate_regression_v2.json

grd_query_limit_zero_regression_v2
minimal failed cases: below-minimum
initial: contract_version eq v1
refined: contract_version eq v1 AND interface_kind eq query_parameter
evidence: artifacts/freeze-demo/w/artifacts/evidence/evd_query_agent_v1/evidence.json
gate: artifacts/freeze-demo/w/artifacts/candidates/cnd_query_agent_v1/gate.json
guard: artifacts/freeze-demo/w/artifacts/guards/grd_query_limit_zero_regression_v2/guard.json
initial_learning: artifacts/freeze-demo/w/artifacts/fitted/initial/grd_query_limit_zero_regression_v2.learning.json
initial_scope: artifacts/freeze-demo/w/artifacts/fitted/initial/grd_query_limit_zero_regression_v2.json
refined_learning: artifacts/freeze-demo/w/artifacts/fitted/refined/grd_query_limit_zero_regression_v2.learning.json
refined_scope: artifacts/freeze-demo/w/artifacts/fitted/refined/grd_query_limit_zero_regression_v2.json

Frozen training examples; not a new holdout evaluation.

### grd_discount_member_rate_regression_v2 / train-v1-discount-amount

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq final_price; actual=discount_amount; matched=False
- replay: artifacts/freeze-demo/w/artifacts/replays/rpl_44071ebf6eaf43569bb9f8f06195044b/result.json

### grd_discount_member_rate_regression_v2 / train-v1-fixed

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq final_price; actual=final_price; matched=True
- replay: artifacts/freeze-demo/w/artifacts/replays/rpl_d5038211a9a844288ef55de25cf2c10c/result.json

### grd_discount_member_rate_regression_v2 / train-v1-source-bug

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq final_price; actual=final_price; matched=True
- replay: artifacts/freeze-demo/w/artifacts/replays/rpl_4913bad1d71f47b5bc215900974f4c82/result.json

### grd_query_limit_zero_regression_v2 / train-batch-v1-legal

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq query_parameter; actual=worker_batch; matched=False
- replay: artifacts/freeze-demo/w/artifacts/replays/rpl_d7200f7218ae4348ae3f3001c2dafd5a/result.json

### grd_query_limit_zero_regression_v2 / train-query-v1-fixed

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq query_parameter; actual=query_parameter; matched=True
- replay: artifacts/freeze-demo/w/artifacts/replays/rpl_b692bc386f0244ac8bf2ff7018bc4120/result.json

### grd_query_limit_zero_regression_v2 / train-query-v1-source-bug

- contract_version eq v1; actual=v1; matched=True
- interface_kind eq query_parameter; actual=query_parameter; matched=True
- replay: artifacts/freeze-demo/w/artifacts/replays/rpl_ab4e23f5dc4b4838ae5c84d138a612c0/result.json
