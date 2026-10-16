# Scope v1 四方法留出评测

验收：通过。
六行留出标签已公开；本结果是工程一致性验证，不是盲测或广泛泛化证据。

## 作用域（micro）

| 方法 | TP | FP | TN | FN | FAR | Recall | Unknown rate | Decision coverage |
|---|---:|---:|---:|---:|---|---|---|---|
| b1_always | 2 | 4 | 0 | 0 | 1.0000（4/4） | 1.0000（2/2） | 0.0000（0/6） | 1.0000（6/6） |
| b2_interface | 2 | 2 | 2 | 0 | 0.5000（2/4） | 1.0000（2/2） | 0.0000（0/6） | 1.0000（6/6） |
| learned_initial | 2 | 2 | 2 | 0 | 0.5000（2/4） | 1.0000（2/2） | 0.0000（0/6） | 1.0000（6/6） |
| learned_refined | 2 | 0 | 4 | 0 | 0.0000（0/4） | 1.0000（2/2） | 0.0000（0/6） | 1.0000（6/6） |

## 端到端（micro，分母仅来自留出行）

| 方法 | Bug recall | False alert rate | Applicable-clean pass rate | Execution validity | Infrastructure failure rate |
|---|---|---|---|---|---|
| b1_always | 1.0000（1/1） | 0.4000（2/5） | 1.0000（1/1） | 1.0000（6/6） | 0.0000（0/6） |
| b2_interface | 1.0000（1/1） | 0.2000（1/5） | 1.0000（1/1） | 1.0000（4/4） | 0.0000（0/4） |
| learned_initial | 1.0000（1/1） | 0.2000（1/5） | 1.0000（1/1） | 1.0000（4/4） | 0.0000（0/4） |
| learned_refined | 1.0000（1/1） | 0.0000（0/5） | 1.0000（1/1） | 1.0000（2/2） | 0.0000（0/2） |

## 每 Guard 与 macro

| 方法 | Guard | FAR | Recall | Bug recall |
|---|---|---|---|---|
| b1_always | grd_discount_member_rate_regression_v2 | 1.0000（2/2） | 1.0000（1/1） | 1.0000（1/1） |
| b1_always | grd_query_limit_zero_regression_v2 | 1.0000（2/2） | 1.0000（1/1） | null（zero_denominator；分母 0） |
| b1_always | macro（Bug recall 纳入：grd_discount_member_rate_regression_v2） | 1.0000（2/2） | 1.0000（2/2） | 1.0000（1/1） |
| b2_interface | grd_discount_member_rate_regression_v2 | 0.5000（1/2） | 1.0000（1/1） | 1.0000（1/1） |
| b2_interface | grd_query_limit_zero_regression_v2 | 0.5000（1/2） | 1.0000（1/1） | null（zero_denominator；分母 0） |
| b2_interface | macro（Bug recall 纳入：grd_discount_member_rate_regression_v2） | 0.5000（1/2） | 1.0000（2/2） | 1.0000（1/1） |
| learned_initial | grd_discount_member_rate_regression_v2 | 0.5000（1/2） | 1.0000（1/1） | 1.0000（1/1） |
| learned_initial | grd_query_limit_zero_regression_v2 | 0.5000（1/2） | 1.0000（1/1） | null（zero_denominator；分母 0） |
| learned_initial | macro（Bug recall 纳入：grd_discount_member_rate_regression_v2） | 0.5000（1/2） | 1.0000（2/2） | 1.0000（1/1） |
| learned_refined | grd_discount_member_rate_regression_v2 | 0.0000（0/2） | 1.0000（1/1） | 1.0000（1/1） |
| learned_refined | grd_query_limit_zero_regression_v2 | 0.0000（0/2） | 1.0000（1/1） | null（zero_denominator；分母 0） |
| learned_refined | macro（Bug recall 纳入：grd_discount_member_rate_regression_v2） | 0.0000（0/2） | 1.0000（2/2） | 1.0000（1/1） |

## initial → refined 配对

| 样本 | initial | refined | 修正错误应用 | 保留适用 | 新 FN | 新 FP |
|---|---|---|---|---|---|---|
| holdout-v1-alternate-bug | applicable | applicable | 否 | 是 | 否 | 否 |
| holdout-v1-discount-amount-alternate | applicable | inapplicable | 是 | 否 | 否 | 否 |
| holdout-v2-alternate-legal | inapplicable | inapplicable | 否 | 否 | 否 | 否 |
| holdout-batch-v1-alternate-legal | applicable | inapplicable | 是 | 否 | 否 | 否 |
| holdout-query-v1-alternate-correct | applicable | applicable | 否 | 是 | 否 | 否 |
| holdout-query-v2-alternate-legal | inapplicable | inapplicable | 否 | 否 | 否 | 否 |

修正错误应用 2 个；保留适用样本 2 个；新增 FN/FP 0/0。

来源缺陷复检另外保存于 source-checks.jsonl，不进入留出指标分母。
跳过与 unknown 均未运行，不计为通过；真实执行身份和时间保存在原始 Replay。
predictions/metrics 是确定性投影；新执行的 Replay/manifest 保留新的实际时间与身份。
