# 四方法纯指标汇总验收

已实现[研究 fixture 的纯汇总](../../study-metrics.md)：复用冻结指标公式，增加完整 N×4 成员校验、
逐项目指标、initial→refined 配对变化及四项 delta；提供 summarize/verify CLI 与两份独立 Schema。
本次是算术工程验收，**没有执行真实目标或证明研究收益**。

## 实测

- 日常快层 **1171 passed / 268 deselected**，253.40 秒；没有跑全量。
- 新汇总与既有公式专项 **40 passed**；全部包含在快层内，不能相加。
- 独立进程执行 CLI help、summarize、verify，三项退出均为 0。
- Ruff、4 个 Python 文件格式、2 份新 Schema 与 29 份既有研究 Schema 一致性检查通过。
- Docker、外部目标运行、训练和 holdout 读取均为 0；没有新依赖、标签、正式协议或发布 tag。

精确 JUnit 统计、代码 pins、私有失败记录摘要及 CLI 收据见 [acceptance.json](acceptance.json)。
首次专项的失败已保留：两条测试预期分别误要求外层拒绝文案、误认为同字节不可变发布也应失败；
另一个超大输入被直接用作参数 ID，触发 Windows 环境变量长度上限及连带 setup/teardown 错误。
修正测试并补齐 CLI 对不可变冲突的有限错误返回后，在新 JUnit 文件中通过；未调整公式、标签或分母。
本地 smoke helper 首次缺少测试目录导入路径，在实际 CLI 执行前停止；修正本地路径后通过，未改产品标准。

## 可重复的算术样本

[fixture-input.json](fixture-input.json)含 6 个合成 Guard/样本对、24 个预测槽位与 2 个合成项目组。
输入在单元测试中人工定义，不来自真实 replay，也不把项目组名字当作谱系独立性证据。
[fixture-summary.json](fixture-summary.json)为当前实现的规范输出；既有 v1 数据/标签没有修改。

其中 2 对适用、4 对不适用，只有 1 对是 true_bug，false_alert_rate 的分母为其余 5 对：

| 项目 | initial | refined |
|---|---|---|
| 混淆 TP / FP / TN / FN | 2 / 2 / 2 / 0 | 2 / 0 / 4 / 0 |
| scope false application rate | 2/4 | 0/4 |
| false alert rate | 2/5 | 0/5 |
| bug recall | 1/1 | 1/1 |

表格是对合成预测的手算核对，不是当前外部数据的实验结论。
另有未知转移、七类执行故障、零分母、项目错配、缺/重复方法、标签错配、重签假指标、
20 次乱序和禁止 subprocess/执行器/learner 的测试。unknown 保留独立计数，不等于明确纠正或执行通过。

```powershell
uv run python scripts/summarize_study_metrics.py summarize --input docs/results/study-metrics-v1/fixture-input.json --output <fresh-summary.json>
uv run python scripts/summarize_study_metrics.py verify --input docs/results/study-metrics-v1/fixture-input.json --result <fresh-summary.json>
uv run pytest tests/unit/test_study_metrics.py tests/unit/test_evaluation.py -m "not slow" -q
uv run pytest -m "not slow" -q
uv run ruff check .
uv run python scripts/export_study_metric_schemas.py --check
```

跨代码版本先用新输出重算，不能重签或覆盖本页历史 summary。算术 verify 只重算给定矩阵，
不证明输入来自真实 Run/JUnit、语义审核或获准的最终留出。
完整 evaluate/compare/report/export 的来源、状态与正式研究判据编排仍需继续开发。

## 外部数据状态

[有界长度政策调查](../../research/colored-arity-policy.md)新增了固定上游三通道文档及历史依据，
但未解除四项错误长度的异常/消息规范未决；没有追加外部容器、删除 case 或贴标签。
termcolor 来源修复仍 1，已观察外部 pair 仍 1，正式研究场景仍 0，colored 保留探索用途。
本轮源码变化按既定规则使需要当前验证的旧链过期；历史真实观察保留在其 `60cbb71` 版本，未补签或重复捕获。
开发计划、待审语义材料、原始 JUnit/网络响应及本机日志只留本地。
