# 完整快照的研究特征与训练拟合

工具自有的完整快照来源现在可以接入独立训练接口。它从真实 Git B/F/H、Evidence、最小 Guard
和原始 JUnit 重建来源，重新读取固定目标全树，再核对特征和人工 fixture 标签。
这一步实现训练层；四方法执行与评测编排尚未接通。

用途固定为 `tool_owned_snapshot_study_only`。旧研究 fixture、完整快照比较和外部 observation-only
parser 不接受这些新记录，训练结果也不提供生产 Registry 或 Docker 调度权限。
外部 TTE/webcolors 的历史观察不能转换成 fixture 数据或自动获得标签。

## 事实来源与特征

`inspect_snapshot_study_source` 只接受精确的 `SnapshotSession`，并调用完整 Guard 来源核验；
外部 Session 和子类都拒绝。来源声明绑定 B/F/H、源审核、Evidence、Guard 和实际最小 case 集。
目标沿用完整快照读取器、容量、包内 bootstrap/原生文件和未安装依赖检查。

`SnapshotStudyContext` 绑定目标摘要、定义文件/符号/字节、元数据依据、真实审核时间和操作者。
定义只能精确匹配直接入口或现有 `static-root-reexport.v2` 的解析结果，不能借闭包中的同名 helper。
`ast-features.snapshot-study.v1` 复用现有[研究语法和十个 token](study-features.md)，不加入新语法。
Try、类方法、fixture 和动态分发仍明确不支持；不生成一份空特征来代替拒绝。

特征 record 绑定完整目标和 context，对账保存人工 expected 与实际结果、逐行见证和全部差异。
核验会重新提取，正确的自摘要不能代替源码/定义/元数据一致。
内层仍只有精确 `FeatureVector`；标签、来源 ID、项目组和审核理由不进入 learner。
元数据与语义标签依赖可信本机操作者审阅，摘要一致不证明其语义正确。

## 训练审核与结果

新[严格 Schema](../schemas/snapshot-study-v1/)覆盖 source、context、feature record/audit、sample、
label、split、protocol、review、fit 和 learned Scope。训练审核摘要由调用方独立保存，不能从可变协议自行取回批准。
撤回事件可以引用前一事件；调用方须显式提供新的可信锚，当前不提供远程身份认证、最新撤回发现或防回滚。

initial 只打开 initial 的 sample/label/context/audit；refined 另读取全部冻结 additions，且 additions 必须为获审合法负例。
holdout 只有承诺、组和仓库身份，没有文件路径；`phase=holdout` 在读取协议前拒绝。
重复逻辑目标、重复引用、训练/留出组或仓库交叉、来源项目混入留出都拒绝。
本机仓库路径摘要不能自动识别远端镜像或复制谱系，真实分组仍需人审。

原 `conjunction.v1` 保持不变：至少 2 正例和 1 负例、枚举 1–3 条合取、训练零误差、每条保留条件有反例见证。
fit 保存训练成员绑定、learning/explanation、逐条件见证和纯 learner 的 predicate/combination 数。
无反例或正例不足等情况保存 `status=refused`、原因和 `scope=null`，不会退回全适用。
同一输入的规则、学习摘要和 fit 可重建；审核使用真实时间，fit 不加入假时间戳。

## 接口与验收

准备工具自有的来源和目标、人工 context/golden 后，使用
[Python API](../src/counterguard/snapshot_study_fit.py) 的 `issue_snapshot_study_fit_review`、
`SnapshotStudyFitSession.fit/verify`。特征提取与对账在
[snapshot_study_features.py](../src/counterguard/snapshot_study_features.py)。

源码仓库根提供训练薄入口：

```powershell
uv run python scripts/fit_snapshot_study.py --help
uv run python scripts/fit_snapshot_study.py fit --help
uv run python scripts/fit_snapshot_study.py verify --help
uv run python scripts/export_snapshot_study_schemas.py --check
uv run pytest tests/unit/test_snapshot_study_fit.py -q
# 设置已核验 root-pytest8 精确 image ID 后：
uv run pytest tests/integration/test_snapshot_study_fit.py -q
```

CLI 分别要求来源执行审核锚和拟合审核锚，训练仓库由调用方显式映射。
fit 退出 0 表示已拟合、4 表示明确拒绝/不支持、5 表示输入损坏；verify 的 0 仅表示事实可重建。
输出限 workspace 内、所有来源/训练仓库之外，不能覆盖不同内容。没有 holdout 或目标执行模式。
真实 Git/Docker 测试同时标 `slow` 和 `docker`；没有镜像变量时 skip，不能将 skip 记为实测。
本阶段实际结果见[训练层验收](results/snapshot-study-fit-fixture-v1/README.md)。

新增包源码改变实现指纹。需要当前实现结论的链使用新 ID/目录重建，原 H 内容未变时可以复用 H，
不重签历史 artifact。真实来源标签、独立分组、外部拟合和正式 scope_v2 数据冻结仍未提供。
