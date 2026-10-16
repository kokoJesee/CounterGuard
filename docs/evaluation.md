# MVP 评测口径和可主张的结果

权威标准仍是 [冻结协议](../experiments/scope_v1.json) 和 [冻结 split](../benchmarks/splits/scope_v1.json)。本页汇总已有结果，不修改标准、不重新标注，也不把公开过的 holdout 当成新盲测。

训练集有 9 行，initial 使用其中 7 行，refined 加入 2 个已确认合法反例后使用 9 行。两族规则从 `contract_version == v1` 变成 version AND interface；learner 的每条保留 clause 都有不可删除的反例见证。这是相对给定标签的必要性，不是全局最小或泛化证明。

留出评测共有 6 行 × 4 方法 = 24 份预测。以下 micro 计数来自原始 manifest/metrics：

| 方法 | TP / FP / TN / FN | Guard 执行数 | false_alert_rate | bug_recall |
|---|---|---:|---|---|
| B1 always | 2 / 4 / 0 / 0 | 6 | 2 / 5 | 1 / 1 |
| B2 interface | 2 / 2 / 2 / 0 | 4 | 1 / 5 | 1 / 1 |
| learned initial | 2 / 2 / 2 / 0 | 4 | 1 / 5 | 1 / 1 |
| learned refined | 2 / 0 / 4 / 0 | 2 | 0 / 5 | 1 / 1 |

Scope 的 FP 指错误应用，不要求 Guard 实际报错。`false_alert_rate = 合规目标上实际 violation 数 / 全部合规目标数`，分母为 5，包含未执行的合规目标。`bug_recall` 分母是适用且有缺陷的目标，合并只有 1；input-limit 一族的留出缺陷分母为 0，所以该族为 null，不能写成 100%。原报告还提供 per-Guard / macro、unknown、执行有效性和零分母原因，不能用表中 micro 代替全部指标。

initial → refined 修正 2 个错误应用，保留 2 个真实适用样本，没有新增 FP/FN。四方法实际执行共 16 次，来源缺陷另复检 4 次；后四次不进入 holdout 分母。标准六行 Demo 则得到 2 pass / 2 violation / 2 skipped_inapplicable、实际 Replay 4 次，它和留出评测是不同数据路径。

发布汇总 [Markdown](results/mvp-evaluation.md) 引用冻结的原始评测数据与摘要，并附历史版本只读复验说明。发布冻结不会重跑留出集以生成“当前版本新结果”。现行代码拒绝旧 manifest 的源码绑定是预期行为；切回原提交验证通过也只继承旧版本的检查范围，见 [历史验证边界](known-limitations.md#历史验证结论的边界)。

15 行全部公开、两个契约族、手工确认元数据和受控本地执行，仅支持机制与工程一致性的结论；不支持任意仓库、程序等价、安全执行未知代码或真实模型稳定性的主张。
