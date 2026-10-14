# 方法论来源核验（2026-10-14）

本文件只记录原始来源及其能够支持的结论。对 EvidenceGuard 的建议明确标为工程推论；不修改冻结协议、样本或历史 artifact。核验时对照了 `src/evidenceguard/scope.py` 与 `docs/data-contracts.md`。

## CEGAR 与 lazy abstraction

Clarke 等人的 [CAV 2000 原论文](https://web.stanford.edu/class/cs357/cegar.pdf) 描述：抽象模型可能出现具体模型没有的反例，检查其可实现性，再精化抽象以排除该路径。作者的 [2003 扩展论文](https://www.cs.cmu.edu/~emc/papers/Papers%20In%20Refereed%20Journals/Counterexample-guided%20abstraction%20refinement.pdf) 第 1.1 节进一步说明其过近似与性质保持关系。

Henzinger、Jhala、Majumdar、Sutre 的 [POPL 2002 原论文 Lazy Abstraction](https://web.stanford.edu/class/archive/cs/cs295/cs295.1086/papers/lazy.pdf) 说明：按需构建抽象可达模型，允许不同位置采用不同精度，从反例的 pivot 位置局部精化，并复用先前工作。论文的第 5 节还讨论复用子树与精化循环的取舍。[作者托管的同篇论文](https://ranjitjhala.github.io/static/lazy_abstraction.pdf) 可供交叉核对。

**工程推论：** EvidenceGuard 的“已确认合法反例 → 作用域收紧”具有反例驱动精化的结构相似性，但它没有上述抽象可达模型、路径可实现性检查或形式化的性质保持证明。不能把所有 Scope false positive 直接改名为 spurious counterexample，也不能把“每遇到一条负例就增加一条全局 AND”称为完整实现 BLAST lazy abstraction。

目前的 `learn_scope` 在固定候选域内枚举 1–3 条合取，并以完整训练集、逐条件负例见证及固定排名选优。工程上，纯贪心加条件不能自动继承最少条件数保证；每条条件有见证只证明不可单独删除，不证明全局最优。排序输入与 tie-break 可以恢复同一训练集合的顺序无关性，但无法证明追加历史不同的增量路径会得到相同结果。若要替换算法，应先定义新算法版本及反例选择、回溯、删冗余和失败处理规则，不原地修改 `scope_v1`。

## ICE 与 ConVer

Garg、Löding、Madhusudan、Neider 的 [ICE: A Robust Framework for Learning Invariants，CAV 2014](https://madhu.cs.illinois.edu/CAV14ice.pdf) 第 3 节把样本分为正例、负例和蕴含对 `(x, y)`；后者要求 `H(x) ⇒ H(y)`。其用途是表达状态间的归纳关系，而不是凭特征共现产生蕴含。

[ConVer 的 arXiv 页面](https://arxiv.org/abs/2605.27051) 确认该论文存在，v1 于 2026-05-26 提交。[正文 IV-C SMART ICE](https://arxiv.org/html/2605.27051v1#S4.SS3) 区分工具错误与语义反例；[VI-B 的消融结果](https://arxiv.org/html/2605.27051v1#S6.SS2) 却描述部分后端的解析错误、无法解码反例污染负例库，收益并非所有后端一致。

**不确定：** ConVer 的设计说明与实验解释之间存在张力；本次没有审计作者完整实现，无法确认实际错误隔离的覆盖程度。不能把其文字设计当作已验证的实现保证，也不能据此承诺 ICE 对本项目一定有效。

**工程推论：** 当前 Scope 的目标是 Guard 适用性分类，不是程序状态不变式；仓库还没有可信的状态转移或适用性保持变换来提供蕴含对。现在直接添加 `version ⇒ interface` 一类规则没有证据来源。值得迁移的是干净的反馈分类、冲突拒绝与反例来源审计；当前已有工具错误/语义失败区分应继续保持。

## Mutation testing

[Stryker 官方等价 mutant 文档](https://stryker-mutator.io/docs/mutation-testing-elements/equivalent-mutants/) 说明等价 mutant 不能通过行为测试区分，并明确工具没有自动完整识别它们的办法。[官方结果与指标文档](https://stryker-mutator.io/docs/mutation-testing-elements/mutant-states-and-metrics/) 区分 killed、survived、timeout、runtime error 与 compile error；其默认指标将 timeout 计入 detected，运行/编译错误不计入有效 mutant 分母。

**工程推论：** 有限契约 case 全部通过，只能证明这些观察没有发现差异；即便 mutant 不等价，也可能只在未覆盖输入上改变行为。必须区分“观察到差异”“未观察到差异”“另有依据确认等价”“运行无结论”。EvidenceGuard 不能照搬将 timeout 当 detected 的口径来宣称获得了缺陷断言证据。

`guard_applicable` 和 `guard_violation` 是独立轴：原接口、版本与上下文中，修复实现、等价 mutant 和缺陷 mutant 都可能适用同一 Guard；差别是执行是否违反断言。因此“非等价 = Scope 正例 / 等价 = Scope 负例”不成立。变异可作为独立的检出能力样本池，但不能自动写回现有 Scope 标签。

可以保留 15 个手工样本，另建带 operator、源码 digest、父实现、观察输入、执行结果与审定状态的 mutation 数据集，用新协议/拆分统计。若非等价性仅按 Guard 是否杀死来判，随后再用它计算 Guard 检出率，会形成循环定义；应使用独立契约/观察 oracle，且标明覆盖范围。只在已确认非等价且已确认适用的子集计算 `killed / (killed + survived)` 时，必须同时报告未审定/错误/超时的数量，避免隐藏分母选择。

**隔离判断（工程判断）：** AST 变异计划的生成可以完全不执行代码。真正跑 mutant 会执行模块导入及其代码；当前 pytest 子进程、插件隔离与超时不构成安全沙箱。Docker 尚未落地前，不应在宿主上批量执行未知仓库 mutant。未来即使采用 Docker，也需要明确文件挂载、网络、权限和资源限制；容器名称本身不构成安全保证。

## Property-based shrinking

[Hypothesis 官方策略文档](https://hypothesis.readthedocs.io/en/latest/reference/strategies.html) 定义各类型向何种简单值缩减。[失败执行说明](https://hypothesis.readthedocs.io/en/latest/explanation/test-case-count.html) 说明 shrinking 会增加执行，并重跑最终失败输入检查不稳定性。[显式 case 的说明](https://hypothesis.readthedocs.io/en/latest/tutorial/replaying-failures.html) 明确 `@example` 不会自动缩减，不能仅把已有契约套上这个装饰器就获得 shrinking。

作者的 [QuickerCheck 原论文](https://arxiv.org/abs/2404.16062) 区分确定性与贪心并行 shrinking；二者可得到局部最小反例，但贪心不保证与顺序 shrinking 得到同一个结果。因此应声明具体简化关系与预算，不能普遍宣称“全局最小”。

**工程推论：** EvidenceGuard 目前按失败 case 筛选是删除整条断言；纵向 shrinking 会改动输入，必须重新计算正确期望，而不能沿用原 case 的 expected。fixed 实现返回值只能作为候选 oracle；正式契约仍需独立认可。每个被接受的缩减候选应同时满足参数类型/合法域、确实更简单、buggy 存在断言失败、fixed 通过且两侧没有工具错误。新输入形成新契约/新 Evidence/新 Guard，不覆盖旧 case 或历史产物。对当前两个简单场景的实际收益尚不确定，需要执行成本与可读性数据。

## 本轮建议边界

- 优先实现解释性见证或计算等价的 eager 搜索优化；用旧算法参照与既有确定性验收证明输出字节、排序和 digest 不变。
- mutation 先分清结果类型与分母，生成/执行以及样本纳入规则另行版本化。
- lazy 算法、ICE 蕴含与纵向 shrinking 先保留具体设计；当前证据不足以承诺提高效果，且替换算法或改输入会影响来源链。

以上工程建议不是上述论文对 EvidenceGuard 的有效性证明；性能收益、适用性保持和未知 mutant 的等价性仍需本项目自己的验证。
