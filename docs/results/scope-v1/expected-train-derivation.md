# scope_v1 训练预期的独立推导

这份记录依据已确认的 benchmark 标签和冻结的 protocol 定义手算，不根据 Guard 运行结果反推作用域。单位是一行 `(guard_id, sample_id)`；仅使用 9 个 train 样本。对应四方法定义在 `experiments/scope_v1.json`，这里推导其中两个 Baseline 的训练验收值。

人工判定依据：discount 的 v1 final-price、input-limit 的 v1 query-parameter 是适用语义；不同契约版本或接口含义不适用。这里使用版本和接口确认**真实标签**；B2 自己只允许比较接口，不能借用标签判据中的版本。

| 训练行 | 人工适用标签 | 接口 | B1 恒适用 | B2 仅接口 |
|---|---|---|---|---|
| `train-v1-source-bug` | true | final_price | TP | TP |
| `train-v1-fixed` | true | final_price | TP | TP |
| `train-v2-legal` | false | final_price | FP | FP |
| `train-v1-discount-amount` | false | discount_amount | FP | TN |
| `train-query-v1-source-bug` | true | query_parameter | TP | TP |
| `train-query-v1-fixed` | true | query_parameter | TP | TP |
| `train-query-v2-legal` | false | query_parameter | FP | FP |
| `train-query-v2-own-contract-bug` | false | query_parameter | FP | FP |
| `train-batch-v1-legal` | false | worker_batch | FP | TN |

9 行中 **4 applicable、5 inapplicable**：

- B1 恒判适用：4 个正例为 TP，5 个负例为 FP，没有 TN/FN，即 **4/5/0/0**。
- B2 接口匹配：保留全部 4 个正例；5 个负例中的 3 个仍共享源 Guard 接口，因此 FP=3；两个不同接口负例被排除，因此 TN=2、FN=0，即 **4/3/2/0**。

| Guard | B1 TP/FP/TN/FN | B2 TP/FP/TN/FN |
|---|---|---|
| discount | 2/2/0/0 | 2/1/1/0 |
| input-limit | 2/3/0/0 | 2/2/1/0 |
| 按行合并 micro | 4/5/0/0 | 4/3/2/0 |

`train-query-v2-own-contract-bug` 不适用，即使它违反自身 v2 契约。Guard 执行是否通过均不改变上表的 TP/FP/TN/FN。这是 expected_train 的依据，而不是“实现运行后得到同样数值”的循环论证。

审计者可从两个 `benchmarks/train/*_scope_samples.json` 对照 9 行身份、标签和接口，再独立按两列逐个计数；不需要运行 `baselines.py` 或 pytest。
