# 四方法研究指标的纯汇总

`summarize_study_metrics` 对工具自有算术 fixture 的完整 N×4 预测矩阵计算指标。
它复用冻结的 `evaluation_metrics.py` 公式，增加按项目分组、initial→refined 配对与指标差值。
该接口不读取研究仓库、训练、打开 holdout、启动执行器或裁决标签；它不是正式 evaluate。

## 输入与结果

严格类型见 [study_metrics.py](../src/counterguard/study_metrics.py)，两份新 Schema 位于
[study-metrics-v1](../schemas/study-metrics-v1/)。旧 Schema 和公式保持原样。

- `study-metric-input.v1`：purpose 固定为 tool_owned_research_fixture_only；每行含 project_group 与原 Prediction。
  接受 4–512 行，每个 `(guard_id, sample_id)` 必须完整覆盖四种方法，无重复，四方法使用同一标签。
  同一 sample 不能随方法或 Guard 改换项目；外层及嵌套标签只接受精确类型，并重新校验复制构造的记录。
- `study-metric-summary.v1`：完整 micro/per-Guard/macro，逐项目同口径结果、逐行配对变化、
  Δbug_recall、Δfalse_alert_rate、Δunknown_rate、Δdecision_coverage，规范化行摘要、全包实现指纹和自身摘要。
  没有运行时间戳；输入乱序 20 次时规范行与整个结果摘要相同。

输入的 fixture 声明和标签是调用方的信任前提，不是代码能证明的真实项目身份或语义。
本接口没有来源授权含义，不能将外部 B1 观察改名后送入它来获得正式实验资格。
当前 termcolor→colored 只有一对探索性 B1 观察，缺四方法矩阵与正式标签，不构成本接口的真实研究输入。

## 指标口径

完整公式沿用[既有评测](evaluation.md)，新实现不调整标准或分母：

```text
true_bug = guard_applicable and guard_violation
alert = (scope_decision == applicable) and (verdict == violation)
false_alert_rate = count(alert and not true_bug) / count(not true_bug)
bug_recall = count(alert and true_bug) / count(true_bug)
```

unknown 是混淆矩阵中的负预测，同时保留 unknown 计数、coverage、skipped_unknown；它不是 inapplicable 或通过。
配对的 corrected_false_application 只计 initial=applicable → refined=inapplicable，不把转为 unknown 算明确纠正。
执行故障不算检出；零分母指标与不能定义的差值为 null。macro 列出实际非 null 的 Guard，不能把 null 当 0。
每个项目单独保留同样四方法指标，不能用总体收益掩盖某个项目的退化。

本接口不提供 research_supported 字段：来源 Bug 保持检出、分组独立性、标签审核、正式协议、
留出访问和原始重放来源尚须完整评测编排核对。算术改善本身不能代替这些条件。

## 命令

```powershell
uv run python scripts/summarize_study_metrics.py summarize --input <fixture-matrix.json> --output <new-summary.json>
uv run python scripts/summarize_study_metrics.py verify --input <same-fixture-matrix.json> --result <summary.json>
uv run python scripts/export_study_metric_schemas.py --check
```

读取最多 4 MiB；重复 JSON key、非有限数、类型/成员/标签/项目错配和未知字段拒绝。
输出遵守不可变写入：相同字节幂等，不同字节返回 5 且保留原文件。
成功汇总或复核返回 0；输入/完整性/IO 拒绝返回 5，参数错误返回 2，不回显任意原文或本机路径。

`verify` 重算整个矩阵和当前实现绑定，保持合法 Schema 并重签的假计数/嵌套指标仍拒绝。
它只证明算术投影与给定输入一致；不独立核验输入是否来自真实 Run/JUnit、来源契约或可信标签审核。
不能据此把虚构 run_outcome 当成实际容器执行证明。

源码变化使旧执行链需要在后续实际使用前按[重算规则](data-contracts.md)重物化。
历史 termcolor/colored 观察保持原记录及其 `60cbb71` 源码版本，本轮没有额外 Docker 或重捕获。
验收结果见[纯汇总回执](results/study-metrics-v1/README.md)。
