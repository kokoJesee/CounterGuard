# 评测口径与结果

权威标准是[冻结协议](../experiments/scope_v1.json)和[冻结 split](../benchmarks/splits/scope_v1.json)。这一页只汇总已有结果：不改标签，不重新标注，也不把公开过的 holdout 说成新的盲测。

训练集共 9 行。initial 用其中 7 行，refined 加入两个已确认的合法反例后用满 9 行。两族规则都从 `contract_version == v1` 变成 version AND interface；learner 保留的每条 clause 都有不可删除的反例见证。这只说明规则相对给定标签是必要的，不证明它是全局最小，也不证明能泛化到样本外。

留出集是 6 行 × 4 方法，共 24 份预测。下面的 micro 计数来自原始 manifest 和 metrics：

| 方法 | TP / FP / TN / FN | Guard 执行数 | false_alert_rate | bug_recall |
|---|---|---:|---|---|
| B1 always | 2 / 4 / 0 / 0 | 6 | 2 / 5 | 1 / 1 |
| B2 interface | 2 / 2 / 2 / 0 | 4 | 1 / 5 | 1 / 1 |
| learned initial | 2 / 2 / 2 / 0 | 4 | 1 / 5 | 1 / 1 |
| learned refined | 2 / 0 / 4 / 0 | 2 | 0 / 5 | 1 / 1 |

这里的 FP 指错误应用，不要求 Guard 真的报错。冻结公式是：

```text
false_alert_rate = count(alert and not true_bug) / count(not true_bug)
true_bug = guard_applicable and guard_violation
```

这个留出集里 5 个非 true_bug 目标恰好都合规，但分母并不是只统计合规目标：不适用却违反自身契约的目标同样算 not true_bug。`bug_recall` 的分母是「适用且有缺陷」的目标，合并后只有 1 个；input-limit 这一族的留出缺陷数为 0，所以它报 `null`，不能写成 100%。

原始报告还给出 per-Guard / macro 指标、unknown 比率、执行有效性和零分母原因，那张 micro 表不能代替全部指标。

从 initial 到 refined，修正了 2 个错误应用，保留 2 个真实适用样本，没有新增 FP/FN。四方法实际执行 16 次，来源缺陷另外复检 4 次，这 4 次不进入 holdout 分母。标准六行 Demo 得到的是 2 pass / 2 violation / 2 skipped_inapplicable、实际 Replay 4 次，它和留出评测是两条不同的数据路径。

发布汇总见 [Markdown](results/mvp-evaluation.md)，引用的都是冻结的原始数据和摘要，并附带历史版本的只读复验说明。发布冻结不会重跑留出集去生成「当前版本的新结果」；现行代码拒绝旧 manifest 的源码绑定是预期行为，切回原提交复验也只继承旧版本的检查范围，见[历史结论的边界](known-limitations.md#历史结论的边界)。

这 15 行全部公开，只有两个契约族，元数据是手工确认的，执行也在受控本地环境里。它能支持的是机制和工程一致性的结论，不能用来主张任意仓库、程序等价、安全执行未知代码或真实模型稳定性。

准备新研究时，可以运行[公开结果独立盘点](experiments/scope-v2/design.md#独立盘点入口)。它只重算历史事实，不执行目标、不重新宣称旧链在当前实现下通过，也不实现 scope_v2 评测。
