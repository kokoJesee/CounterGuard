# 新研究的候选登记

这里的 [candidates.jsonl](candidates.jsonl) 是开发期来源登记，不是已经验收的数据集。其 `study-candidate-ledger.v1` 仅记录候选来源、探测状态和未通过原因，不是拟议的正式 study-sample Schema。

目前三批累计登记 13 个仓库候选，纳入场景 0；没有 train/holdout 标签、冻结 split、scope_v2 protocol 或学习结果。不可将这些记录直接送入 learner，也不能将它们当作未见留出样本。后续各批只追加记录，先前行的原始字节与摘要保持不变。

每行区分来源 revision 与 preflight_revision；例如 Luhn 的历史 B/F 提案与 HEAD 预检不是同一次检查，不能混用状态。所有 `guard_transfer_compatibility` 仍为 unconfirmed。

来源依据、可重复命令和下一步见[数据卡](../../docs/experiments/scope-v2/data-card.md)，实际观测见[首批](../../docs/results/scope-study-feasibility-v1/README.md)、[第二批](../../docs/results/scope-study-feasibility-v2/README.md)与[第三批回执](../../docs/results/scope-study-feasibility-v3/README.md)。冻结的 v1 数据和口径保留原样。
