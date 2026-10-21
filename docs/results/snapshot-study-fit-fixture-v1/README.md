# 完整快照研究训练层验收

工具自有的完整快照来源已接入独立的特征与拟合接口，严格类型、CLI 和11份新 Schema 已实现。
本阶段关闭训练层的工程缺口；**完整快照的四方法重放和评测编排仍待接入**。
没有真实项目标签、外部训练数据或正式 scope_v2 冻结。

接口见[完整快照研究拟合](../../snapshot-study-fit.md)，有限机器回执见[qualification.json](qualification.json)。
回执绑定当前包指纹和源码/测试文件 pin；该版本的原始 JUnit 与失败记录只留本地。

## 已测范围

| 命令 | 实际结果 |
|---|---|
| `uv run pytest -m "not slow" -q` | 1286 passed / 291 deselected，665.09秒 |
| `uv run pytest tests/integration/test_snapshot_study_fit.py -q` | 1 passed、无skip，601.15秒 |
| `uv run ruff check .` | passed |
| `uv run python scripts/export_snapshot_study_schemas.py --check` | 11份一致 |

快速层与Docker专项并行运行，耗时不能直接与以往串行验收对比。本批没有跑全量。
新增单元专项另有18passed；首轮12个setup error源于规范序列化后的list不能构造严格frozenset，
修复为保留原内层对象，没有放宽FeatureVector或Schema。原失败与后续回执分别保留。

真实专项只构造工具自有Git历史，启动**4个自有Docker容器**：B/F Evidence捕获2、最小Guard自检2。
来源声明随后从B/F/H、契约、审核、Evidence/Guard和原始JUnit重建；不是给来源JSON补一个正确自摘要。
四个训练仓库的目标完整固定树也重新读取，工作树恶意改动与根conftest不进入来源或执行。
拟合/核验没有追加Docker或调用本地executor，宿主目标import哨兵未触发。

人工synthetic初始集合为2正1负，精化另加1个合法负例，纯learner分别得到1条和2条条件。
这只是显式构造的fixture，不能证明真实跨项目收益或增加独立来源数。
20次乱序保持原learner的规则和学习摘要，保留clause反例见证；拒绝结果为scope=null并可重建。
learner只收到精确FeatureVector/bool，外层字段、标签依据和仓库身份留在适配层。

initial不读取refinement内容；holdout阶段在读取协议前拒绝，holdout没有文件读取入口。
还覆盖重签来源/目标/标签/对账、错误审核锚、撤回、训练/留出别名与组交叉、来源混入留出、
错误输出路径和新旧用途交叉解析。真实Git/Docker测试同时标slow/docker。

## 仍未覆盖

外部快照、外部语义标签、快照学习规则的Docker重放、N×4评测、正式protocol/split/context与留出消费
不在本阶段实现或实测范围。外部observation-only与生产snapshot用途未扩大。
webcolors的Try仍不在当前研究语法子集内，不能用空特征代替拒绝。
远程审核身份、防回滚、自动最新撤回、恶意目标干扰容器内pytest/JUnit等既有限制保持。

新增包源码改变实现指纹，历史观察保留为原实现下的事实；需要当前结论时使用新ID/目录重建，
不重签旧artifact、不改冻结数据/原examples/运行依赖或发布标签。
