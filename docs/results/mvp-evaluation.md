# MVP 冻结评测汇总

这是冻结留出评测的汇总，不是新的留出实验。

原 manifest：`sha256:154d19625e3f858d82235bb348c18b4cedf07f6b31bdeee70e8b4aad6399ad38`。

| 方法 | TP / FP / TN / FN | 执行数 | false_alert_rate | bug_recall |
|---|---|---:|---|---|
| b1_always | 2 / 4 / 0 / 0 | 6 | 2/5 | 1/1 |
| b2_interface | 2 / 2 / 2 / 0 | 4 | 1/5 | 1/1 |
| learned_initial | 2 / 2 / 2 / 0 | 4 | 1/5 | 1/1 |
| learned_refined | 2 / 0 / 4 / 0 | 2 | 0/5 | 1/1 |

逐样本配对汇总（原值）：`{"corrected_false_applications": 2, "delta_false_application_rate": -0.5, "delta_recall": 0.0, "new_false_applications": 0, "new_false_rejections": 0, "retained_applicable_cases": 2}`。

false_alert_rate 的分母为全部 5 个合规目标；input-limit 族的 Bug recall 分母为 0，保留 null。
四方法共 16 次执行，来源缺陷另复检 4 次，不混入留出分母。

[完整口径](../evaluation.md)、[原始报告](scope-v1/evaluation/report.md)、[历史验证覆盖限制](../known-limitations.md#历史验证结论的边界)。
没有重签或改写旧产物。
