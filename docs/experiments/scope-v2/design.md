# 新数据上的作用域精化研究

状态：研究准备规格；数据、协议和执行适配尚未冻结。本文记录实验设计与实现边界，不是新研究已完成的声明。

## 要回答的问题

新增已确认的合法反例后，学习作用域能否减少错误应用，同时保留原有缺陷检出能力？

主要比较是同一批留出行上的 learned initial → learned refined 配对变化。B1 always 与 B2 fixed interface 是参照。initial/refined 使用同一 `conjunction.v1`：枚举 1–3 条合取，零训练 FP/FN，每条保留条件都有反例见证，按既有确定性顺序裁决。此次不改成 lazy refinement，不加入 ICE、参数 shrinking 或自动变异样本。

`scope_v1` 是工程回归参照，其 15 行和全部标签已经公开。它不能成为新盲测，也不能因当前结果与历史相同而获得新的泛化结论。

## 当前能力盘点

| 接口 | 可复用部分 | 新研究缺少什么 | 实现依据 |
|---|---|---|---|
| Protocol / split | 冻结 v1；独立 fixture protocol/split/人工标签审核与实际来源重建 | 外部 scope_v2 的分组、标签、协议仍未冻结；fixture 不增加真实场景 | [研究拟合](../../study-fit.md) |
| 纯 learner | 特征白名单、零误差搜索、并列裁决、clause 见证；独立 fixture fit/Scope 与核验 | 外部数据与标签不开放；自有 fixture 另经两条可信审核锚接入研究重放 v2 | [scope.py](../../../src/counterguard/scope.py)、[研究拟合](../../study-fit.md) |
| Feature / context | 冻结 v1 提取与对账；独立研究 fixture 版本支持 For/GeneratorExp、行见证和精确 learner 投影 | 外部接口类别、研究 context 与正式 fit/split 尚未冻结；静态记录不提供执行权限 | [研究特征](../../study-features.md)、[context 政策](../../module-context-policy.md) |
| Evidence / Guard | 受限 contract.v3–v6 → Docker evidence.v4 → 最小 guard.v3/v4、自检和独立重建 | 每个真实来源仍需完整 B/F、H 内契约、闭包与人工审核；版本按 oracle/profile 选择，不适用则停 | [standalone capture](../../standalone-capture.md)、[Guard](../../standalone-guards.md)、[v2 导出](../../static-reexports-v2.md) |
| Scope / replay | 生产 standalone 使用精确 B/F 快照；研究 v2 对自有 fixture 支持四方法、fit 来源重建与三态决定，旧 v1 行为不变 | 不能放宽生产 snapshot Scope、执行未获准外部目标或把 fixture 当外部实验 | [standalone_replay.py](../../../src/counterguard/standalone_replay.py)、[学习规则重放](../../research-fitted-replay.md) |
| Metrics / evaluation | 既有分子/分母、配对变化与报告逻辑 | v1 外层绑定类型与硬编码期望不能直接用于新 Guard/真实仓库 | [evaluation.py](../../../src/counterguard/evaluation.py)、[metrics](../../../src/counterguard/evaluation_metrics.py) |
| 纯研究指标汇总 | 自有 fixture N×4、按项目汇总、配对与差值、确定性及算术独立重建 | 不核验原始 Run/标签来源、不打开 holdout、不执行目标；不是正式 evaluate | [study-metrics](../../study-metrics.md) |
| 独立历史事实盘点 | 只读标准库脚本，核对公开预测/标签/计数/pin | 不检查旧 Docker 授权或完整运行来源，不批准 scope_v2 | [研究入口](../../../scripts/run_scope_study.py) |

删掉 Literal、预期计数或来源 pin 并不构成新研究支持。新数据先做可行性探测，再独立定义版本化的研究模型和 Docker 适配。不能提前制造一个“通过”的 scope_v2 protocol。

## 独立盘点入口

在源码仓库根运行：

```powershell
uv run python scripts/run_scope_study.py inventory
uv run pytest tests/unit/test_study_inventory.py -m "not slow" -q
```

`inventory` 分支只读历史事实，不 import 仓库目标，不调用生产 learner/evaluator，不启动 Git/Docker/pytest 子进程。测试也拦截真实子进程启动。
同一脚本另有自有 fixture 的 `audit/replay/verify`，见[研究重放](../../research-replay.md)。
训练专用 `fit/verify` 由独立 [fit_scope_study.py](../../../scripts/fit_scope_study.py) 提供；聚合入口尚未路由 fit，`evaluate/compare/report/export` 尚未实现。
独立[纯指标命令](../../study-metrics.md)已补齐 fixture 矩阵的算术层，不消费外部观察或替代这些完整编排命令。
独立的静态特征命令见[研究特征](../../study-features.md)，自有 fixture 的 learned replay
另见[研究重放 v2](../../research-fitted-replay.md)；正式外部评测未接通。
完整快照另有独立的[特征/训练接口](../../snapshot-study-fit.md)，已用真实自有Git/Docker来源验收，
并以工具自有fixture接通[四方法重放与N×4评测](../../snapshot-study-evaluation.md)。
这项工程桥接不增加真实样本、外部标签或正式留出；旧词法闭包fit仍不接受快照或外部观察记录。

该命令只读固定路径的 v1 protocol/split、9 个训练样本、6 个公开留出样本、原始 24 份预测和已发布汇总。它独立计算 B1/B2 训练计数、四方法留出混淆矩阵、false alert/bug recall 分母、执行数与配对变化，并比较原始数据和历史发布 pin。重复/缺失行、标签错配、文件篡改、重新签名的不同历史 manifest、重复 JSON key 和非有限数字会拒绝。

输出采用 `scope-study-inventory.v1`，含原始输入摘要、盘点脚本摘要、计数及自身摘要。退出 0 只表示公开事实一致，5 表示拒绝；`execution_allowed=false`、`target_execution_count=0`。没有新时间戳或假执行记录。同一输入/脚本输出稳定，原始字节换行变化可能改变输入摘要。

历史 manifest 对应旧实现/执行环境；本命令不宣称旧来源链在当前实现下已 verify，也不把其记录的 16 次执行当本次新运行。结果见[独立盘点记录](../../results/scope-study-inventory-v1/README.md)。

## 样本、来源与四方法

分别报告三种数量：独立修复事件 `scenario_id`、固定仓库/提交/符号/闭包的 `sample_id`、`(guard_id, sample_id)` 评测行。同一修复的多条测试、fork/mirror 或参数变体不增加独立修复数；N 行对应四方法的 4N 个结果槽位。

采集目标为 30–50 个有来源证明的独立修复场景，不是统计效力保证。先用小批真实候选测成本和可比性；不足时公开实际数量，不填入近重复或将合成变异冒充真实修复。

| 方法 | 规则 | 不允许读取的材料 |
|---|---|---|
| B1 always | 对预先纳入可比 cohort 的行恒判 applicable | 标签与人工例外 |
| B2 interface | 只比较 interface_kind 与来源 Guard 冻结接口 | version、path、AST、标签或特例 |
| learned initial | 只用 initial 成员学习 | refinement / holdout 标签 |
| learned refined | initial 加冻结合法反例后完整重训 | holdout 标签 |

共同安全准入在 Scope 前执行，B1 也不得越过来源、调用表示、闭包、runner 和 Docker 限额。研究桥接未通过前不运行新研究目标。所有方法使用同一审核执行路径、输入与预算。

合法反例必须有独立规范依据、确实不适用，且满足自身契约。Guard 报错本身不证明适用或不适用，测试通过也不证明程序等价。`guard_violation` 仅对 applicable 标签有语义；实际误执行是否报警由 replay 另记。

契约以真实回归测试/规范为依据，必须由所有者按支持 profile 的要求提交到 H。上游文件与工具方添加逐项区分。工具不能补造 H 或向上游发 PR 来代替所有者动作。机械提取草案不等于 oracle 已获审核。

上段的 B/F/H 来源链针对**来源 Guard**。独立比较目标不要求再拥有一个真实修复 B/F 或另建来源 Evidence/Guard；其要求是固定快照、许可和谱系依据、自身行为规范、可审核调用映射及完整安全准入。
原有来源契约来自 H 的约束保持不变，现有 standalone capture 路径也不增加外置契约例外。未来研究目标输入须另行版本化和审核，不能通过替换生产 Guard 的仓库/入口或放宽 snapshot Scope 来实现跨项目执行。

## 分组与留出隔离

主轨 `scope_v2` 计划按独立上游项目分组；镜像、复制代码、模板与修复谱系的相连组整体划分。来源 Guard 的 B/F 项目属于 source/train，不同时进入主轨 holdout。

首批可行性要先确认：其他项目是否存在真实且语义可比的目标。不能用另一个项目的“同名函数”代替契约匹配。缺少自然跨项目目标时，主轨记 insufficient_data，暂不扩张评测器；同项目跨提交探索须另有协议 ID、范围和明确确认，不能冒充项目隔离。

训练开发只能读取 train。维护者/独立保管者准备和封存最终标签，开发者只收到承诺摘要；正式 gate 后解封。没有独立保管条件或执行者已读全部标签时，记录 `holdout_exposure=known`，只称冻结留出验证。摘要/日志不提供身份认证或真正的权限隔离。

initial/refinement 的成员选择按预先声明的来源时间或固定队列进行；若用初始规则的错误应用选反例，只在训练候选池内执行，排序/预算先冻结。split 的拟议确定性种子为 20261018，最终还需连同排序/人工分配依据写入新协议。

任何 AST/标注分歧先保留双方值和依据，再由维护者裁决。冻结后更改标签/词汇/分组要另开版本；看过最终结果后不能通过改规则恢复“未见数据”资格。

## 指标与结论资格

公式继承[冻结口径](../../evaluation.md)，新协议必须显式列出每项分子/分母与聚合方式：

```text
true_bug = guard_applicable and guard_violation
alert = applicable_prediction and actual_guard_violation
scope_FAR = FP / (FP + TN)
scope_recall = TP / (TP + FN)
bug_recall = count(alert and true_bug) / count(true_bug)
false_alert_rate = count(alert and not true_bug) / count(not true_bug)
unknown_rate = count(unknown) / N
decision_coverage = 1 - unknown_rate
```

unknown 在主混淆矩阵中是负预测，另列 coverage 和配对转移；它不是 inapplicable。skip/unknown 不算执行通过，执行异常不算 violation，分母为 0 输出 null。训练 source Bug 检出表不并入 holdout recall 分母。

报告 micro（先合计）与 macro（每 Guard 等权，列明非 null 成员）、per-Guard/per-project；相同项目/修复的多行不当作独立统计样本。没有预注册的分析设计和足够独立组时，只报告效应大小与逐行证据。

主判据为：micro Δscope_FAR < 0、Δscope_recall ≥ 0、Δbug_recall ≥ 0（非零留出分母）、有实际纠正的错误应用、无新增错误应用/错误拒绝、来源 Bug 保持实际检出、无基础设施失败。留出无 true_bug 时不能证明留出缺陷检出；某 Guard 的退化不能藏在 micro 收益中。

工程验收与研究支持分开：结果可重建但判据未满足，可以交付负结果；来源/安全/完整性未通过则不得宣称完整实验通过。无规则的 Guard 保存明确拒绝，不按结果删去。

## 下一道准入

最新真实材料是[colored 固定观察](../../results/colored-observation-v1/README.md)及[长度政策补查](../../research/colored-arity-policy.md)。
工具自有链另有[学习重放](../../research-fitted-replay.md)和[纯指标汇总](../../study-metrics.md)，不能替外部数据分配标签。
静态 profile 扩展不批准外部跨项目执行；研究通道的自有 fixture 验收也不代替外部源审与语义裁决。
字面量 8/8 不等于 8 个合法反例，也不等于有足够的独立训练/留出数据。

候选采集需逐项满足：完整来源与许可、可表示契约、合法 H、受限闭包、自然跨项目可比性。记录所有未通过项、网络/工具/人工/等待耗时；不支持则停止该候选，不改标准。

这些条件尚未实测全部满足。未通过前不冻结 scope_v2、不开正式标签，也不把新研究规格当成生产功能。新派生链使用新 ID/目录，既有 benchmark/examples/协议/context、artifact 与发布标签保留。
