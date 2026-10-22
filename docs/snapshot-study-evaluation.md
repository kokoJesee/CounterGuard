# 完整快照的四方法研究重放

这是工具自有 fixture 的工程接口：完整 Git 来源 → 特征与训练拟合 → 四方法重放 → N×4 评测、核验和导出。
它不接受外部观察记录，不裁决真实标签，也不授予生产 Registry、Shadow 或 Active 权限。
正式跨项目数据、分组和留出实验尚未由这条接口完成。

## 四种方法共用什么

每个查询共用同一份来源 Evidence/最小 Guard、完整固定目标、全部原 case 映射、runner 和执行策略。
同一 Guard 的全部查询必须共用同一对 fit、拟合审核锚和 B2 的来源接口类别，不能按查询调参。

| 方法 | 决定 |
|---|---|
| `b1_always` | 所有通过完整性检查的查询都适用 |
| `b2_interface` | 查询接口类别等于获审来源接口类别时适用 |
| `learned_initial` | 重建 initial fit，再对实际查询特征计算原条款 |
| `learned_refined` | 重建 refined fit，再对同一查询特征计算原条款 |

拟合被拒绝时返回 `unknown`，保留原 refusal 原因；不退回 B1 或伪装成 `inapplicable`。
`inapplicable` 和 `unknown` 都不发现或启动 Docker，`run=null`，没有授权、运行目录或原始 Run 引用。
报告分别显示通过、Guard 失败、明确跳过、未知和执行故障；跳过不计通过。
pytest 真失败、收集错误、超时和执行错误保持不同结果，执行故障不计检出。

新 `snapshot-study-*.v1` [执行 Schema](../schemas/snapshot-study-replay-v1/)和
[评测 Schema](../schemas/snapshot-study-evaluation-v1/)独立于旧比较和外部观察类型。
来源事实复用旧只读读取器时，先生成只含原始事实引用的内部视图；这个视图不落盘、不调度执行。
旧 parser 仍拒绝新研究计划。实际调度只使用新计划、新审核和新授权，绑定两份 fit 及查询 context/audit。

## 审核与评测

拟合审核、逐查询执行审核、评测审核是三个独立锚。调用方在计划之外保管这些摘要。
CLI roster 还需要原始字节摘要，避免更换 roster 就替换全部可信锚；摘要不是远程身份认证。

评测计划冻结排序后的成员与全部四方法。每个成员绑定原始计划、人工 fixture 标签、Guard、固定逻辑目标及项目组。
查询标签的依据来自目标提交中的文件 pin，必须在首次运行前全部核对；实际重放不读取查询标签来决定作用域。
同 Guard/目标、同 Guard/sample 的重复行、样本别名和同仓库多组声明都拒绝。
这些检查不能自动识别远端复制谱系或证明人工语义正确。

`evaluate` 在任何输出/容器之前检查全矩阵和路径预算，随后逐项保存实际结果。
最后再次核对全部输入。途中发生变化时保留已经发生的 Run 和 `failure.json`，不发布完整评测。
完整性错误直接拒绝，不以 `unknown` 掩盖损坏来源。

`verify` 从固定 Git 来源、两份 fit、查询特征、审核、原始授权及 JUnit 重建每一行，
再重算完整矩阵、项目指标、配对变化和源 Bug 表。自摘要正确的假计数仍拒绝。
`report`、`compare`、`export` 均先执行这一核验，不启动容器或再次拟合目标代码。

指标沿用[纯汇总口径](study-metrics.md)：micro / per-Guard / macro、逐项目、initial→refined 配对及四项差值。
零分母保持 null；unknown 不算通过或明确纠正。评测包含已知人工 fixture 查询，不能声明为正式封存留出。

源 Bug 表单列 Guard 原始 buggy/fixed 自检，不进入查询指标分母，角色固定为
`unscoped_guard_self_check_not_learned_scope_replay`。
它证明原最小 Guard 的双向自检，**不证明学习后的 Scope 仍会适用于来源缺陷**。
后者仍须正式实验单独提供按学习阶段的来源重放。
结果的 `research_support` 固定为 `fixture_engineering_only_not_scientific_evidence`，不输出研究通过结论。

## 命令

以下命令在源码仓库根运行；`<…>` 代表调用方已准备并独立审核的工具自有 fixture 材料。
这不是任意外部项目的接入命令。

```powershell
uv run python scripts/run_snapshot_study.py --help
uv run python scripts/run_snapshot_study.py fit --help
uv run python scripts/run_snapshot_study.py audit --workspace <workspace> --roster <roster.json> --roster-digest <trusted-raw-digest> --row <row> --plan <plan.json>
uv run python scripts/run_snapshot_study.py replay --workspace <workspace> --roster <roster.json> --roster-digest <trusted-raw-digest> --row <row> --plan <plan.json> --output <new-run>
uv run python scripts/run_snapshot_study.py evaluate --workspace <workspace> --roster <roster.json> --roster-digest <trusted-raw-digest> --evaluation-review-digest <trusted-evaluation-digest> --plan <evaluation-plan.json> --review <evaluation-review.json> --output <new-matrix>
uv run python scripts/run_snapshot_study.py verify --kind evaluation --workspace <workspace> --roster <roster.json> --roster-digest <trusted-raw-digest> --evaluation-review-digest <trusted-evaluation-digest> --result <new-matrix/evaluation.json>
uv run python scripts/run_snapshot_study.py report --workspace <workspace> --roster <roster.json> --roster-digest <trusted-raw-digest> --evaluation-review-digest <trusted-evaluation-digest> --result <new-matrix/evaluation.json> --output <new-report.md>
```

`compare` 和 `export` 使用与 `report` 相同的锚及 result 参数；output 分别为新 JSON 文件和新目录。
`audit --kind evaluation` 需要 plan、review 和评测审核锚。
roster 使用 `snapshot-study-cli-roster.v1`，字段定义见
[脚本](../scripts/run_snapshot_study.py)中的 `FixtureRoster` / `FixtureSessionSpec`。
每行显式给出 source/target 仓库、来源 binding/review、三个审核摘要和训练仓库映射，路径限 workspace 内。
不能从待核验文件中自动取得可信摘要，亦不能加入外部 purpose、holdout 路径或执行开关。

退出码：0 表示操作成功；2 为参数错误；3 为运行基础设施/完整性故障；4 为明确 unknown、拒绝拟合或不支持语法；
5 为输入/来源核验失败。完整矩阵可以包含明确 unknown；评测命令仍返回 0，报告保留 unknown 计数。
`verify` 的 0 只表示给定事实可重建，不表示全部查询通过或研究结论成立。
所有输出遵守不可变写入及路径预算，不能写进来源、目标或训练仓库，不能覆盖旧结果。

## 可重复验收

```powershell
uv run pytest tests/unit/test_snapshot_study_replay.py tests/unit/test_snapshot_study_evaluation.py tests/unit/test_snapshot_study_cli.py -q
uv run python scripts/export_snapshot_study_replay_schemas.py --check
uv run python scripts/export_snapshot_study_evaluation_schemas.py --check
# 使用 runner list 核验并设置 root-pytest8 的精确 COUNTERGUARD_RUNNER_IMAGE_DIGEST 后：
uv run pytest tests/integration/test_snapshot_study_replay.py -q
```

Docker 专项只创建工具自有历史，同时标记 slow/docker；缺少镜像变量时 skip，不能算已测。
验收记录见[四方法 fixture 回执](results/snapshot-study-replay-fixture-v1/README.md)。
没有新增运行时依赖，未扩展 AST 语法、conjunction.v1、外部用途或冻结 scope_v1。
新增包源码改变全包实现摘要，需要当前结论的来源/审核/fit/重放链必须在新 ID/目录重建；历史产物不重签。
远程身份、最新撤回、防回滚、原子快照和恶意目标干扰容器内 pytest/JUnit 仍未解决。
