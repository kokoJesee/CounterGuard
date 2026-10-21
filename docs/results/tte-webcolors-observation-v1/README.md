# TerminalTextEffects → webcolors 固定快照观察

本次在单独获审的外部快照用途下，从真实输入校验修复生成 Evidence 和最小 Guard，
再对固定 webcolors 目标分别运行来源 Guard 与目标自身 oracle。工程链完整通过；
**本页只记录行为事实，不分配适用性标签、不训练 Scope，也不把一个 pair 说成正式实验数据集。**

## 固定来源与结果

| 项目 | 固定输入或结果 |
|---|---|
| 上游来源 | [ChrisBuilds/terminaltexteffects](https://github.com/ChrisBuilds/terminaltexteffects)，MIT |
| B / F | `bb541505aa05d12e6f43d62d803b05836a5db09a` / `b360e0723d2c8e88e7db4f98c162b99b87442bd9` |
| owner H | [kokoJesee/terminaltexteffects@068dc27](https://github.com/kokoJesee/terminaltexteffects/commit/068dc27c61e8f6fc1cf25f500fdeccd0fddcd009)，父提交为 F |
| H 边界 | 独立分支 `counterguard/hex-rejection-v1`；只新增 `contracts/tte.hex-rejection.v1.json`，提交含 `NOT upstream`；默认分支未移动 |
| 来源入口 | `terminaltexteffects.utils.colorterm:fg` |
| 原契约 | 6 个原始非法字符串，均要求 `ValueError` 与字面量消息 `Invalid RGB hex color code` |
| 目标 | [ubernostrum/webcolors@6c8da68](https://github.com/ubernostrum/webcolors/tree/6c8da6832eb4ae2591a1883a0d1371263d6cd4db)，BSD-3-Clause，入口 `webcolors:normalize_hex` |
| 镜像 | root-pytest8：`sha256:561d706ee4938783c17e92efda0058ce4ebcc04e021981292a16b0a12ecd0d16` |
| 来源捕获 | B 6 failed、F 6 passed，`reproduced=true` |
| 最小 Guard | 实际失败集为全部 6 个原 case；B 6 failed、F 6 passed 自检通过 |
| webcolors 原 Guard | 两次均 `test_failed`，每次 6 failed，逐 case 签名相同 |
| webcolors 自身 oracle | 两次均 `passed`，每次 6 passed，逐 case 签名相同 |

来源与目标的成功返回用途不同；这里只比较六个非法 hex 输入的拒绝行为。
webcolors 符合自身固定文档、实现和测试所支持的 `ValueError` 与消息约束，但不符合来源 Guard 的消息。
因此，原 Guard 的失败是**两个 oracle 不一致的观察事实**，不自动等于目标缺陷或来源误报。

公开的有限投影见 [observations.json](observations.json)。原始 binding、审核锚、授权、JUnit、
stdout/stderr、容器账本和完整 Run 保留在本地审计目录；公开投影不能替代原工作区里的独立 verify。

## 执行边界

真实外部容器恰好 **8 次**：来源捕获 2、最小 Guard 自检 2、目标原 Guard 2、目标自身 oracle 2。
全部使用同一个已审核镜像，没有本地 executor、宿主目标 import、依赖安装、原测试/conftest/插件加载，
也没有额外重试。来源完整快照约 108 MB，容器执行前后均重建 Git、许可、审核和输入 pin。

新建 fork 的仓库级 GitHub Actions 在 H 发布前由所有者明确授权关闭，避免独立分支触发继承的工作流；
原值和恢复方法留在本地设置变更回执。该操作没有修改上游、CounterGuard 或账号全局设置。

外部用途先通过[工具自有 fixture 资格](../external-snapshot-fixture-v1/README.md)：快速层
1268 passed / 290 deselected，来源专项 2 passed，Docker 专项 8 passed / 1 deselected，
以及 Ruff、Schema 和源码 pin 检查。真实观察使用同一已提交实现
`4d3347894f0d9f69c49e124ea14066d7d499e1cd`，执行期间包源码未变化；本批没有另跑全量。

首次真实编排在零容器时发现 runner 选择器同时传了两种互斥参数，失败记录保留；
第二次网络获取 H 返回 128，同样在零容器时停止，具体 stderr 只保留摘要，原因不确定。
最终轮复制首次已成功获取并核验的精确 H Git 对象，在新目录完成全部检查与 8 个容器，
没有放宽准入、改 oracle 或增加预算。

## 研究状态

截至本页，真实来源修复为 **2**，实际外部观察 pair 为 **2**，正式接纳的跨项目研究场景仍为 **0**。
这 6 个 case 属于同一个来源修复，不能按 6 个独立场景计数。当前数据没有标签、独立 grouping、
initial/refinement/holdout，也没有快照特征到现有四方法 fit 的获审桥接，所以不能开始正式训练或主张收益。

本批没有修改冻结 benchmark、experiment/split/context、既有 artifact 或发布标签。
远程身份签名、防回滚、最新撤回、并发原子快照和恶意目标干扰容器内 JUnit 仍未关闭。
