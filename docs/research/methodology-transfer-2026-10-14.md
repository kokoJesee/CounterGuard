# EvidenceGuard 方法迁移评估与本轮优化

日期：2026-10-14；评估起点为 D8、`conjunction.v1`、275 个既有测试。原始来源核验见 [研究记录](methodology-sources-2026-10-14.md)。本文区分文献事实、代码现状和工程建议；工程成本是单人、当前两个场景下的粗估，不是承诺。

本轮保留冻结的 eager 搜索、数据与实验口径，实施三项优化：二元计数拒绝 unknown、谓词覆盖缓存、独立的逐条件反例证书。lazy 算法替换、ICE 蕴含、mutant 生成/执行、输入 shrinking 均未实施。

## 第一部分：综合评价

### 三个方向的适用边界

| 方向 | 判断与理由 | 对应模块 | 冲突或缺口 | 成本量级 |
|---|---|---|---|---|
| CEGAR 的反馈分类与反例审计 | 适用。合法反例驱动适用边界修正；工具错误须隔离，保留每条条件的支持证据 | `scope.py`、新增 `scope_explanations.py`、`baselines.py`，执行错误仍由 `execution.py` / `replay.py` 区分 | 目前是适用性分类，没有抽象可达模型、路径可实现性检查与形式化可靠性证明 | 解释/缓存优化约 0.5–1 天；已实施 |
| lazy refinement | 值得设计，暂不替换。候选规模增大后可能减少工作；现有 92/175 个组合很小，真实运行往往更贵 | 未来 `scope_lazy.py`；新 learner、learning/fit 和协议版本 | 贪心路径、最少条件数、三条上限内的可解性、计数语义与持久化绑定均需重新论证 | 小场景原型与差分约 3–5 天；稳定的精确增量实现可能 1–2 周，收益不确定 |
| ICE 蕴含约束 | 当前不该接入。需要有可信来源的 `H(x) ⇒ H(y)` 样本对 | 未来独立 implication 模型、约束求解/审核模块，不能混入 FeatureVector | 当前没有程序状态转移或经认可的适用性保持变换；共现关系不能充当蕴含证据 | 单独模型/审计约 3–5 天；可靠约束生产方缺失，完整成本不确定 |
| mutation testing | 适合独立的 Guard 检出实验，不适合直接自动产生 Scope 正负标签 | 未来 `mutation_plan.py`、独立 observation/结果分类模块；复用执行与 Replay，不改变 learner | 有限观察不能证明等价；检出标签与适用标签不同；同源样本相关性；宿主执行风险 | 确定性 AST 计划约 1–2 天；隔离、观察 oracle、审核及报告约 1–2 周，隔离基础设施另计 |
| shrinking | 适合辅助解释新缺陷，当前优先级低 | 未来 `shrinking.py`，新契约提案 → `capture_evidence` → `compile_guard` | 需要参数域、简化序和独立期望 oracle；修改输入会改变证据链；不一定能获得全局最小 | 受控提案器约 1–3 天；加入双向执行/来源审核约 2–5 天，复杂参数另计 |

CEGAR 中的 spurious counterexample 是“抽象反例路径在具体程序中不可实现”，不是所有错误应用的统一名字。我们可以写“受 CEGAR 启发的反例驱动作用域精化”，保留现有 `scope false positive`、合法反例和真实断言违规的区别。[Clarke 等，CAV 2000](https://web.stanford.edu/class/cs357/cegar.pdf)

BLAST 的 lazy abstraction 在抽象可达树的不同位置使用不同精度，并局部精化和复用工作；机械地追加全局 AND 条件不能继承这些结论。[Henzinger 等，POPL 2002](https://web.stanford.edu/class/archive/cs/cs295/cs295.1086/papers/lazy.pdf)

ICE 的蕴含是样本对上的分类约束，不是“version 与 interface 同时出现所以必然相关”。[Garg 等，CAV 2014](https://madhu.cs.illinois.edu/CAV14ice.pdf) ConVer 的引用真实存在，但其错误隔离设计与部分实验中负例污染的解释存在张力：本轮没有审核完整实现，实际隔离覆盖程度**不确定**，其效果也不能直接外推到本项目。[ConVer v1](https://arxiv.org/html/2605.27051v1)

### B1：是否改成 lazy refinement

**现在不建议用“每遇到反例就追加一条”的贪心算法替换 v1。** 本轮实现覆盖缓存，减少重复计算，完整保留 eager 枚举与选优标准。

| 用户关心的保证 | 明确回答 |
|---|---|
| 20 次乱序规则与 digest 一致 | lazy 不必然破坏，但按输入到达顺序精化会有风险。必须从完整训练多重集规范排序，固定反例选择/谓词排名，并使每次重建与持久化历史无关。仅把最终条件排序不能消除路径依赖。增量 checkpoint 若按到达历史选择规则，还需单独证明同一最终训练集合的汇合性 |
| 每条保留条件由反例支持 | 可以保留，前提是每轮完成后针对全部已确认负例重新检查删除见证并删掉失去支持的条件；“新条件排除了本次反例”不充分。加入条件后旧条件可能变得冗余 |
| 最少条件数 | 贪心不保证。逐条件有见证只证明不可单独删除；全局替换条件可能更短。要保持 v1 最少条件与固定排名，必须证明更短/更优规则不存在，必要时回溯，最坏情况仍会退回完整搜索 |
| 冻结 `scope_v1` 结果 | 当前两个简单场景，在明确保留版本优先排名的方案下，可以期待 initial=version、refined=version AND interface，但这不是所有 lazy 实现的保证。即使规则/预测相同，新 learner 名称、搜索计数或轨迹也会改变 digest。不得原地替换 v1 或修改期望值；新算法单独版本化，并通过独立对照展示结果 |

一个可手算的最小性反例（不是新 benchmark，也不改变任何标注）：两个正例均为 version=v1、interface=A、signature=S、module=M；负例如下，其余字段相同。

| 负例 | version | interface | signature | module |
|---|---|---|---|---|
| N0 | v2 | A | S | M |
| N1 | v1 | B | T | X |
| N2 | v1 | B | S | X |
| N3 | v1 | A | T | X |

从 version=v1 开始，按 N1、N2、N3 精化，若在能排除当前反例的条件中沿用字段优先级：N1 选择 interface=A，N2 已排除，N3 再选择 signature=S。最终三个条件都有独立见证：删 version 纳入 N0，删 interface 纳入 N2，删 signature 纳入 N3。但 version=v1 AND module=M 只有两条，已排除全部负例。**不可删除不等于条件数最少。**

待确认的方案是“反例驱动的精确搜索”，而不是不可回溯追加：

1. 仍只接收精确 TrainingExample/FeatureVector；使用全部已确认训练标签，保留冲突拒绝和源 buggy/fixed 正例，holdout 不进入搜索。
2. 从较弱假设开始，规范选取被误纳的合法反例；没有新误纳时不机械增加条件。将反馈分类为合法反例、真实断言违规、工具错误/unknown，最后一类不成为语义负例。
3. 缓存谓词覆盖；按当前固定的条件数/AST 数/字段/JSON 排名扩展与回溯，必要时允许替换已有条件。最终校验 FP=FN=0、逐条件删除见证及不存在更优可行规则。
4. 区分静态候选空间大小和实际评估组合数。若实际只检查 10 个组合，不能声称枚举了 92 个。新学习记录显式保存预算、停止原因、反馈摘要与确定性轨迹；预算不足不得冒充最优或发布可用 Scope。
5. 同一最终训练多重集重启 20 次乱序均一致；另测多种追加顺序、重复负例、多条件解、无解、工具错误和预算耗尽。新轨迹的摘要也要一致，不伪造执行时间。
6. 精确 lazy 可作为 eager 的独立差分实现；若选择近似贪心，则用新的最小性声明，不能沿用 v1 保证。缓存精确算法是否明显更快，**不确定**，需要更大候选集上的独立性能数据。

版本/重算范围：新 learner → 新 learning digest → 新 Scope/fit digest → 新 Replay → 新 Evaluation。即使规则恰好一致，也只发布新版本目录；复用未变化的 Contract/Evidence/Guard/Feature 输入并重新审核其绑定。新实验协议必须独立声明算法和计数口径，原 `scope_v1`、15 个样本、拆分和已发布资产保持不动。已经公开的六行 holdout 只能继续用于工程对照，不能包装成新的盲测证据。

### B2：mutation 能否自动扩 benchmark

**可以建立独立 mutation 样本池；不能用“非等价=Scope 正例、等价=Scope 负例”自动标注。**

| mutant 情况 | 能推导什么 | 不能推导什么 |
|---|---|---|
| 可信执行在明确输入上观察到区别 | 在该观察条件下与父实现不同 | 不必然违反契约，不必然适用某个 Guard，也不证明所有输入的表现 |
| 有限契约所有 case 通过 | 契约覆盖的输入上未发现违规；若还直接比较父实现，只能称这些观察相同 | 不证明语义等价。契约通过也不一定证明输出与父实现相同，例如契约允许多个合法输出 |
| 有独立、明确范围的等价证明 | 可在证明范围内排除为等价，记录证明依据 | 不能因此标成 Scope 不适用；不能外推到证明范围之外 |
| 解析失败、导入错误、超时、环境错误 | 无法形成行为结论，单独统计 | 不得当作契约违规、等价或 Scope 负例 |

修复实现、等价 mutant、缺陷 mutant 都可能使用同一个合法接口/版本并适用同一个 Guard。区别通常是 `guard_violation`，而不是 `guard_applicable`。即便非等价 mutant 改了行为，也可能仍满足契约或改动了 Guard 未覆盖的性质。[Stryker 等价 mutant 官方说明](https://stryker-mutator.io/docs/mutation-testing-elements/equivalent-mutants/)

建议的新样本格式至少分开：父目标/源码摘要、operator/参数及 mutant 摘要、独立适用性审核与依据、契约/观察输入及结果、行为差异状态、Guard 执行状态、错误/超时、人工审定记录。状态为 observed-different、no-difference-observed、proven-equivalent（带范围证明）、inconclusive；禁止把 no-difference-observed 自动晋升为 proven-equivalent。

独立检出度量：对每个 Guard 的**已确认适用、已独立确认非等价且确有待检契约违规、执行有效**的 mutant 子集，统计 `killed / (killed + survived)`；killed 只认真实 Guard 断言违规。报告必须同时给出生成总数、待审等价性/违规性、等价、合法行为变化、不适用/unknown、错误和超时数量及纳入规则，分母为零显示未定义。标准 mutation score 与这个受限的 Guard 缺陷检出率分别命名，不冒充所有 mutant 的总体能力。用 Guard 自己是否报错来认定“应检出”，再计算它的检出率，会产生循环度量。

Stryker 默认指标将 timeout 归入 detected；EvidenceGuard 若采用“必须有真实失败断言”口径，须用新实验协议明确区别，而不能偷偷更改既有实验标准。[Stryker 状态与指标](https://stryker-mutator.io/docs/mutation-testing-elements/mutant-states-and-metrics/)

共存方式：保留 15 个手工样本与 `scope_v1` 作为稳定对照；新数据用独立 ID、协议、拆分和结果目录，不回填旧标签。按父实现/缺陷族分组拆分，避免相似 mutants 跨 train/holdout；先独立确定适用性，再做行为观察与违规判定。单一算子生成大量近似样本，不能当作大量独立缺陷或独立反例支持。

隔离：只解析源码并生成 AST 变异计划可以不执行目标。导入、执行或批量重放 mutant 会执行代码；当前 pytest 子进程、禁用插件和 timeout 没有网络/文件/权限隔离。**Docker 未落地前，不在宿主自动执行未知仓库的 mutants；本轮没有增加这一入口。** 对明确可信的现有 toy fixture，受控临时副本实验可能可行，但自动执行框架仍等隔离与协议就绪。容器执行也需明确只读来源挂载、隔离输出、网络策略、低权限及资源限额。

### Shrinking：落点与限制

现有“最小 Guard”是仅保留实际失败 case 的断言集合，不表示参数值已最小，也不证明整个断言集合在逻辑上全局最小。当前 query 的失败输入已经是单字符 `"0"`，继续缩减的收益小；discount 的 `100.00` / `12.55` 可能有更简单复现值，但是否仍复现同一缺陷、且是否保留 rounding 的解释信息，**不确定**。

Hypothesis 的显式 `@example` 不会自动 shrinking；简单套装饰器不能完成迁移。缩减要声明简化序和局部最小范围，预算耗尽只能说“当前找到的更简单输入”。[Hypothesis 显式样本说明](https://hypothesis.readthedocs.io/en/latest/tutorial/replaying-failures.html)、[QuickerCheck](https://arxiv.org/abs/2404.16062)

未来提案接受条件：类型/输入域合法、按固定 cost/字典序严格变简单、独立契约 oracle 给出正确期望、buggy 仍为真实断言失败、fixed 通过、双方都无工具错误。fixed 的返回值只可提出候选期望，不能独自批准契约。原 case 的 expected 不能无条件沿用到新 args；`amount=0` 即使更短，也可能把本次折扣缺陷隐藏。

为保留当前来源保证，新输入必须另建被认可的新契约/新 case 身份，再捕获新 Evidence、编译新 Guard，并记录原证据与缩减轨迹。影响链为 Contract → Evidence → Guard → Scope/fit → Replay/Evaluation；声明契约改变也影响对应 Feature/audit 绑定。本轮不修改任一既有 case、Evidence 或 Guard。

## 第二部分：已实施优化

| 风险/收益顺序 | 动机和改动 | 验证 | digest / 重新物化范围 | 未做 |
|---|---|---|---|---|
| 1：阻止未知值被二元计数吞掉 | `baselines.count_predictions` 只接受严格 bool 标签和 applicable/inapplicable；之前任意其他字符串，包括 unknown，被当成负预测。迁移 CEGAR/ICE 的干净反馈分类原则 | 14 个新增参数化用例拒绝 unknown、执行 verdict、空值与隐式整数标签；既有 Baseline 4/5/0/0、4/3/2/0 保持 | 有效输入结果不变，无已有 digest 或 artifact 需重建；遇 unknown 明确拒绝，需另报覆盖率 | 没有把 unknown 排除后暗改冻结分母，也没有把超时计为检出 |
| 2：缓存谓词覆盖，保留 eager 精确语义 | `scope.py` 每个候选谓词只匹配训练行一次，用 Python 整数位集做组合交集和删除见证；完整枚举 1–3 条并保持原排名 | 独立逐行/集合枚举器，40 个固定生成数据集、超过 64 行、三条件、无解、两场景两阶段逐字节对照；新增匹配调用计数；既有 20 次乱序继续运行 | 规则、predicate/combination_count、完整 learning JSON/digest 不变；无需重物化 Evidence/Guard/Feature/Learning/Scope/Replay | 没有 early-stop、采样组合或 lazy 替换；候选空间增长仍是组合级，未宣称端到端运行加速 |
| 3：独立反例证书 | 新 `scope_explanations.py`、导出脚本和 schema；每条条件输出删掉后被纳入的全部去重负例 FeatureVector，绑定原 learning 与训练多重集 digest。迁移反例驱动精化的可审计性 | 20 次乱序证书一致；单条件/空合取；去重不改变训练计数；错误 witness、摘要篡改和重新签名的虚假声明拒绝；v1/v2 学习兼容；集成拦截 subprocess，资产逐字节保护，过期输入先拒绝后不发布 | **只新增 scope-explanation.v1 自己的 digest**；在新版本目录物化，现有各层 digest 不变。上游学习/训练改变时证书需另行生成，不回写 Scope/fit | 证书只证明相对于已给标签的条件必要性；不能独立证明标签正确、未来泛化或形式化全局最小 |

反例证书入口（只读审核 fit；不重训、不启动 pytest）：

```powershell
uv run python scripts/explain_fitted_scopes.py --fit artifacts/experiments/scope-v1/fitted/initial/fit-manifest.json --output artifacts/analyses/scope-explanations-v1/initial
uv run python scripts/explain_fitted_scopes.py --fit artifacts/experiments/scope-v1/fitted/learning-v2/refined/fit-manifest.json --output artifacts/analyses/scope-explanations-v1/refined
```

本轮已经在这两个此前不存在的目录生成四份证书；历史学习资产不迁移。新证书字段、验证和重算规则见 [数据契约](../data-contracts.md)。如果再次导出同输入，文件相同可幂等复用；来源或内容改变必须使用新版本目录，不能覆盖历史。

本轮变更文件还包括 `scripts/export_schemas.py`、`tests/unit/test_baselines.py`、新增两份 scope 单元测试与一份证书集成测试、README 和本文/来源记录。没有新的运行时依赖，也没有改动 `pyproject.toml` 或 lockfile。

完整验收：`uv run pytest -q` 为 **342 passed / 150.92 秒**（保留 275 个既有测试，新增 67 项检查）；`uv run ruff check .` 与 `git diff --check` 通过。六份本地已发布的 learning（v1 initial/refined、v2 refined，各两个 Guard）均与独立逐行枚举器逐字节一致，四份新证书均重新复核通过。没有新增运行时依赖。

冻结保护审核：benchmarks、examples、`experiments/scope_v1.json`、依赖清单与 lockfile 相对 Git HEAD 无差异；644 个既有 artifact 文件均没有本轮首次代码修改后的写入时间，84 个带自摘要的既有 JSON 全部审核通过，现有来源/协议/fit 绑定审核通过。实际新增 artifact 仅四份解释证书。

**审计限制：** 初始全目录逐文件摘要快照存入了单次调用的沙箱临时目录，该目录结束后不可读取。因此不能声称已完成全部 644 个旧文件的前后逐字节对照。上述既有资产核验采用修改时间、自摘要、可信来源绑定与冻结 Git 差异检查；它们不能替代已经丢失的完整前置快照。当前资产摘要清单的集合摘要与完整验收记录保存于 [verification.json](../results/methodology-v1/verification.json)，不伪造“快照对照通过”。

## 第三部分：明确不做

- 不把所有误报改名为 spurious counterexample：缺少具体程序路径的不可实现性判定，会夸大形式化保证。
- 不把贪心 lazy 原地替换 `conjunction.v1`：可能损失顺序无关、最少条件数和有解时的搜索完整性；计数/摘要也可能漂移。
- 不把每条新反例机械转成新增条件：有些反例已被排除，有些反馈是运行错误，新增条件还可能让旧条件冗余。
- 不凭共现构造 ICE 蕴含：没有可信约束生产方，会把推测当标签，甚至引入泄漏。
- 不把有限测试未发现差异写成等价，不把等价 mutant 写成 Scope 负例：前者失去等价性可信度，后者混淆适用与正确性。
- 不用 Guard 自己生成“该被它检出”的标准、不把 timeout/解析错误计为缺陷检出：避免循环评测与工具错误冒充语义证据。
- 不在隔离前批量执行未知 mutants；没有宿主安全边界，新增代码导入也会执行。
- 不让 shrinking 改写已发布 case 或沿用旧 expected，不把 fixed 当唯一真值：会破坏契约独立性、双向证据与来源链。
- 不为了方法对齐引入 SMT、mutation 框架或 Hypothesis 运行时依赖：当前计算缓存和证书无需这些依赖；真正迁移前缺协议、隔离或 oracle，依赖无法补足这些信息。
- 不使用公开 holdout 来调新算法或产生新的盲测主张，不修改冻结标签/拆分/context/实验/历史 artifact。

下一步建议维持 D9 四方法对照的既定主线。本轮优化作为确定性与审计性补强；lazy 原型在用户确认后另开版本化实验，不能先改算法再补理由。
