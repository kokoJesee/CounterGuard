# 数据契约与摘要边界

本文说明当前持久化接口，字段校验以 `src/evidenceguard/models.py`、`predicates.py`、`features.py`、`baselines.py`、`protocol.py`、`scope.py` 和 `scope_explanations.py` 为准。JSON Schema 位于 `schemas/`，业务跨字段不变量另由严格模型与 verify 检查。

## 依赖与重算规则

当前 Evidence 只有 `artifact_digest`，没有 semantic_digest；Guard 才提供语义投影摘要。Feature 也不由 Guard 派生，而是由目标源码、声明契约和独立 module context 派生。纯 learning 依赖训练特征与适用性标签；物化 Scope/fit manifest 再绑定 Guard 和协议来源。这些分支在 Replay 汇合。

| 本层 | 摘要的直接依赖 | 上游变化时必须做什么 |
|---|---|---|
| Contract / source | 原始文件字节；实验 source pin 单独只规范 CRLF | 来源 Evidence 引用改变的文件必须重新 capture；相关目标/声明契约的 Feature 与 audit 重算。冻结实验 source pin 改变不能原地重签，需新协议 |
| Evidence | 契约、测试、buggy/fixed 目标、双向 RunRecord、日志引用摘要、版本/替代链和自身字段 | 任一引用或日志变化则旧 Evidence 验证失败；新 capture 使用新修订，重编译相关 Guard 并审核来源。时间变化或重新捕获也会改变 artifact_digest |
| Guard | artifact：Evidence 关联、完整 Guard 字段、自检与日志；semantic：固定 9 字段执行投影 | Evidence 换修订必须发布新 Guard 身份/版本，不能覆盖原资产。即使 semantic_digest 相同，guard artifact 绑定变化也要求重新物化 Scope/fit manifest；规则本身可复核后复用 |
| Feature / audit | 目标源码、声明契约、module context、自身特征；audit 还依赖样本文件、手工标注、词汇/提取器与快照 | 重提受影响目标并重新审计；context 来源或记录格式变化生成新记录版本。audit 不能靠改标注变绿。相关训练特征/标签变化须重新学习；其他目标变化无需重训无关规则 |
| Learning / Scope / fit | 纯 learning：规范排序的训练 FeatureVector+标签、算法/结果格式；Scope/fit：另绑定训练身份、Guard artifact、protocol/split/context/audit 和创建记录 | 特征、标签、成员或算法变化要重学对应 Guard/phase；仅来源绑定或结果记录格式变化可保留验证后的相同规则，但必须重新物化相关结果/manifest。旧引用不可静默换成新 digest |
| 可选 ScopeExplanation | learning artifact_digest、训练多重集 digest、正负例计数、逐条件删除见证、证书格式 | learning 或训练变化时在新目录重生成证书；该证书是旁路审计产物，不改变已有 Scope/fit/Replay 绑定，也不触发它们重物化 |
| ReplayResult（D8） | 实际 Guard、Scope、fit 来源、目标与声明契约/context/Feature、作用域 trace、真实运行及日志 | 任一实际输入绑定变化需新的 replay ID 和记录。已有 skipped/unknown 不可改为 pass；完整性失败须显式拒绝或 stale，不能自动刷新上游后继续冒充旧 replay |
| EvaluationReport（D9） | 协议/拆分、冻结标签、全部逐行预测/ReplayResult、指标实现与环境清单 | 重放或度量输入变化须新 evaluation；冻结口径变化用新协议。仅渲染修改可从同一原始 JSON 重生成展示，不重新计算事实 |

操作顺序：先定位最早变化层 → 标记其下游现有引用不可用于新工作 → 在新 ID/版本/目录重建必要产物 → 逐层 verify → 最后发布新 Replay/Evaluation。不得通过重新计算旧文件的自摘要来“修复”来源错配。

例：D6 的 AST 词汇与 15 个特征值没有改变，但 module_group 来源证明增加，导致 FeatureRecord v2 和独立 audit 必须重建，D7 fit provenance 必须更新。纯规则在相同训练值下可以一致。D8 候选计数字段升级同理：改 learning 记录格式与下游引用，不改变已冻结规则或样本真值。

## Guard 的 semantic_digest

`semantic_digest` 使用当前固定的 `guard-semantic.v1` 投影规则，由 `protocol.guard_semantic_digest` 计算。它绑定**指定身份和版本的 Guard 执行内容**；不同 Guard ID 即使断言相同，也不共享此摘要。

精确字段集合为下表的 9 个顶层字段，不通过动态排除字段的方式生成：

| 字段 | 包含内容 |
|---|---|
| `guard_id` | Guard 身份 |
| `guard_version` | Guard 整数版本 |
| `contract_id` | 原业务契约身份 |
| `target_interface` | `contract_family`、`contract_version`、`interface_kind`、`symbol_signature` 四个字段 |
| `argument_types` | 完整参数名与类型映射 |
| `return_type` | 返回类型 |
| `cases` | 全部最小 case；每项包括 `case_id`、`args` 以及恰好一个 `expected` / `raises` |
| `generator_version` | 确定性测试生成器版本 |
| `test_digest` | 生成的 `test_guard.py` 原始字节摘要 |

算法：取上述字段的实际值，将嵌套模型转为 JSON 值，使用 UTF-8、键排序、紧凑分隔符、禁止 NaN 的规范 JSON，计算 SHA-256，输出 `sha256:<64 位小写十六进制>`。字段值与 case 数组顺序均参与摘要；`test_ref` 路径不参与。`guard-semantic.v1` 是这套规则的名称，**不是额外加入摘要载荷的第十个字段**。

明确排除：`schema_version`、`created_at`、`source_evidence_id/ref/digest`、`contract_digest`、`source_buggy_digest`、`source_fixed_digest`、`validation_run`（含 run ID、日志和时间）、`test_ref`、`state` 和 `artifact_digest`。完整 source contract 内容仍由协议的 source pin 和来源审核检查；最小执行内容则在 cases、接口、类型与测试摘要中固定。

排除运行期字段，使相同源码在新的可信工作区重新捕获后仍符合实验协议。它不证明来源记录有效，也不证明 Guard 适用，更不单独证明任意目标正确。

Registry / CI 的使用顺序：

1. `guard verify` 审核实际 Guard 自摘要、测试字节、Evidence、输入及日志来源链。
2. 比较协议要求的 `semantic_digest`，确认执行内容与冻结版本一致。
3. Scope 的 `guard_digest` 仍绑定本次实际 Guard 的 `artifact_digest`；新工作区重新捕获后必须重新生成该 Scope。
4. CI 仍需独立做作用域判断、执行和生命周期检查；不能只比较语义摘要就启用或放行。

增加、删除或改变投影字段必须升级投影规则和协议；不得改 `scope_v1` 的已冻结摘要或 golden 期望来消除失败。当前协议 digest 保持 D5 的 `sha256:1f401186a3f51c17e582dbbdc96f9324e47e128f90fcb91f29594690bc8daa3a`。

## FeatureVector 与 AST token

FeatureVector 只包含五个标量字段和 `ast_features`。前四项从可信契约元数据取得；`module_group` 从独立、固定摘要的 `benchmarks/context/scope_v1.json` 架构包清单取得；只有 AST 集合从源码生成。目标名称、路径、case、Oracle 和标签均在模型之外。上下文来源及 D6 更正见 `module-context-policy.md`。

`branch:none` 的历史名称表示 **Python None 身份检查**：`ast.If` 或 `ast.IfExp` 的 test 内，一个正式参数与 `None` 通过 `is` / `is not` 比较，允许左右交换。它不表示缺少分支。

| 代码形态 | `branch:none` |
|---|---|
| `if raw is None:`，raw 是参数 | 有 |
| `x if raw is not None else y` | 有 |
| `if None is raw:` | 有 |
| `if raw == None:` | 无 |
| 局部变量 `other is None`，other 不是参数 | 无 |
| `return raw is None`，未作为 If/IfExp test | 无 |
| `return x + 1` 或只有 `if x > 0` | 无 |

`branch:is_member` 同样只检查 If/IfExp test 对正式参数 `is_member` 的引用。函数体其他地方出现名字或字符串均不算。没有符合条件的分支时可以没有任何 branch token；合法的纯计算目标可以产生空 AST 集合。失败或不支持的结构则抛 `FeatureExtractionError`，不能返回空集。

保持现有 token 字符串以兼容 `scope_v1` 的冻结标注；任何将名称改成 `branch:none_check` 的迁移都留给新的词汇/协议版本。

剩余词汇的具体边界：

- `decimal:multiply/subtract` 是目标函数体中的 `BinOp(Mult/Sub)`，名字不承诺完成 Decimal 类型推导。
- `int:parse` 为未被局部/模块绑定遮蔽的内建 `int` 调用，也支持显式导入 `builtins.int` 的别名。
- `regex:ascii_digits` 只认已解析的 `re.fullmatch` 调用与字符串字面量 `[0-9]` / `[0-9]+`；显式 import 别名可识别。`\d+`、`re.match`、动态 pattern 不算。
- `range:check` 要求同一个 If/IfExp test 中，对同一个 Name/Attribute/Subscript 表达式出现两个方向的数值上下界比较。支持 `< <= > >=`、链式比较和正负数值字面量；不同值、单边比较、分别位于不同 test 的比较、动态界变量都不算。它是语法存在性特征，不证明区间逻辑正确。
- `round:half_up` 为加载已解析的 `decimal.ROUND_HALF_UP`，支持显式 import 别名，排除遮蔽。
- `str:isascii/isdecimal` 为对应 attribute 的 Call；仅引用方法不算，也不承诺推导接收对象的类型。

`ast-features.v1` 只支持唯一、无装饰器的同步顶层函数。只遍历它的函数体，不读其他函数体、默认参数或模块表达式作为特征。嵌套作用域、lambda、推导式、async、yield、循环、with、try、match、函数内 import、global/nonlocal 等明确拒绝；扩展支持时需增加边界验收，必要时升级提取器版本。全过程只读并解析 AST，不导入或执行目标模块。

## FeatureRecord 与对账报告

新记录为 `feature-extraction.v2`，外层保存 extractor/vocabulary 版本与摘要、TargetRef、目标原始字节摘要、契约引用与原始字节摘要、module_context_ref/digest、FeatureVector 和自身摘要。旧 v1 形状与摘要兼容读取，但不能用于 D7 fit。外层身份/来源不传入学习器。没有生成时间字段，相同输入可得到相同字节；同提取器/context/sample ID 的不同输入不能原地覆盖。

`feature-audit.v2` 报告记录数据文件摘要、独立 module context、每个样本的 expected/actual、AST `missing/unexpected`、标量 `metadata_diff`、来源 feature 引用、快照和摘要。错误行单独保留原因，不伪造 actual。审计不读取适用性、违规或 compliance 标签来提取特征；已公开 holdout 的源码与手工 AST 可以用于对账，不进入 D7 拟合。历史报告与快照追加保留，分歧仲裁见 `feature-adjudication.md`。

退出 0 要求所有行 matched；差异返回 1，配置或词汇错误返回 2，提取失败返回 3，不可变资产冲突返回 5。混合失败时优先级为 5、3、2、1。错误和差异都会先写出报告。

## Learner 类型边界与确定性

`learn_scope(examples: tuple[TrainingExample, ...]) -> ScopeLearningResult` 是纯规则搜索入口；它不接收 Guard、FeatureRecord、样本 ID 或路径。TrainingExample 只有精确的 FeatureVector 和严格 bool 适用性标签。严格模型拒绝额外字段，运行时入口拒绝其他模型、dict、FeatureRecord 和带额外属性的 FeatureVector 子类，并重新校验输入。正例角色、标签来源、合法反例、协议、来源和成员资格由外层 `fit_scopes` 审核后再投影。

这是类型注解、严格模型和运行时校验共同执行的输入边界；不把 Python 动态运行时描述成任意代码无法绕过的安全沙箱。测试覆盖整份 FeatureRecord、外层 JSON、混入身份/Oracle 字段、子类和伪造模型输入；正常 API 都会拒绝。

搜索只从正例生成标量 eq / AST contains 候选，枚举 1–3 条 AND，保留 FP=FN=0 且每条条件有独立负例支持的规则。并列顺序为：条件数更少、AST 条件更少、固定字段顺序、规范 JSON 字典序。字段顺序固定为 family、version、interface、signature、module_group、AST；候选输出按规范字段/操作/值排序。

新 `scope-learning.v2` 保存纯训练特征与标签的无序规范摘要、规则、混淆计数，以及 predicate_count / combination_count；没有时间和样本 ID，其 artifact_digest 是乱序验收所比较的确定性摘要。旧 v1 的 candidate_count 实际代表组合数，保持原形状和摘要兼容读取。

| 场景（initial/refined 均相同） | predicate_count | combination_count |
|---|---:|---:|
| discount | 8（5 个标量 + 3 个 AST） | 92 = C(8,1)+C(8,2)+C(8,3) |
| input-limit | 10（5 个标量 + 5 个 AST） | 175 = C(10,1)+C(10,2)+C(10,3) |

组合数记录实际枚举的全部 1–3 条组合，包含后来因 FN/FP 或冗余被丢弃的组合。它不是成功规则数。v2 模型核对组合公式，测试对两个真实场景分别固定数字；不把 discount 的 8/92 当成所有 Guard 的常数。

当前计算实现缓存各谓词的训练覆盖位集，再做组合交集；完整枚举、固定排名、删除见证与记录形状保持 `conjunction.v1`。独立逐行枚举器逐字节对照，因此不需要重新签名或重新物化现有学习资产。它不是 lazy 算法，组合空间并未缩小。

`count_predictions` 只接受严格 bool 标签与 applicable/inapplicable 两种预测；unknown、执行 verdict 和隐式整数标签被拒绝，不能混入二元混淆矩阵。覆盖率与 unknown 数量另行报告，不暗改冻结实验的分母。

D9 评测层另按冻结计划 §5.3 显式计算：unknown 在主混淆矩阵中属于负预测，同时独立记录 unknown_count、unknown rate 与 decision coverage。原始 Prediction/Replay 仍保留 unknown/skipped_unknown，且 run=null；不把它重命名为 inapplicable，也不调用只接受二元输入的 count_predictions。这个规则是原冻结口径，不是本轮调整标准。

## 可选作用域反例证书

`scope-explanation.v1` 由 `scope_explanations.py` 定义，包含 learner_version、label_basis=`supplied_training_labels`、原 learning_digest、training_dataset_digest、positive_count/negative_count、clause_witnesses 和自摘要。每个 witness 保存对应 ScopeClause 及删除该条件后被纳入的全部去重负例 FeatureVector；按规范 JSON 排序。重复训练行仍计入训练摘要/正负计数，证书只去重展示特征。

单条件规则删除后成为空合取，接受全部负例。多条件见证必须匹配所有其他条件，并被本条件排除；同时被其他条件排除的样本不是本条件的删除见证。严格模型检查这些逻辑不变量，`verify_scope_explanation` 再核对自摘要，并针对原学习和完整训练多重集重建证书，拒绝重新签名的虚假计数/见证。只校验自摘要不足以证明见证属于训练负例。

证书证明条件不可单独删除，不独立证明标签正确、规则泛化或任意语法上的全局最小。纯函数 `explain_scope` 保留 learner 的 feature-only 输入边界；`explain_fitted_scopes` 外层只读审核既有来源/协议/成员/自动特征，再投影训练输入。它不捕获 Evidence、不重训/更新 fit、不调用 pytest；所有组审核通过后才写独立文件。

证书没有执行/创建时间字段，因为它是确定性的派生说明，没有声称发生新执行。其 digest 覆盖全部上述字段（排除自身 artifact_digest），旧 learning/Scope/fit digest 不改变。Schema 为 `schemas/scope-explanation.schema.json`，新物化目录为 `artifacts/analyses/scope-explanations-v1/{initial,refined}/`。

外层 ScopePredicate 与 `fit-manifest.v1` 另外记录实际创建时间、sample ID、Guard artifact digest、protocol/split/context/audit 摘要。首次创建时间真实记录，重复相同输入验证后复用；不伪造时间来制造确定性。不同干净工作区的物化 Scope 摘要可能不同，纯 learning digest 保持一致。

v2 learning 的记录格式改变 artifact_digest，因此新 fit bundle 使用 `fitted/learning-v2/{initial,refined}`，旧 D7 资产不覆盖。新 fit manifest 引用不可变 audit history 文件，不再绑定可被后续审计替换的最新报告副本。

## ReplayResult 与执行边界

`replay-result.v1` 显式绑定 Guard/Scope/protocol/fit 的引用与摘要、目标原始字节摘要、声明契约和 module context、自动 FeatureRecord、决策 trace、最终 verdict、失败 case 和 RunRecord。unknown 时 FeatureVector/FeatureRecord 可为空；绝不制造空特征向量代表提取失败。

| scope_decision | verdict | run | 执行返回码 |
|---|---|---|---:|
| inapplicable | skipped_inapplicable | null | 0 |
| unknown | skipped_unknown | null | 4 |
| applicable | pass | 实际 passed RunRecord | 0 |
| applicable | violation | 实际 test_failed RunRecord，列稳定 case ID | 1 |
| applicable | collection_error / execution_error / timeout | 实际错误 RunRecord | 3 |
| applicable | stale | 若已运行则保留实际 RunRecord，否则 null | 5 |

报告仅统计 verdict=pass 为通过；skipped/unknown 不进入 pass。模型禁止 unknown 变成 inapplicable、skipped 配 run、无真实 run 的 pass、以及错误运行冒充 violation。未知特征以明确 reason、null FeatureVector 和未匹配 trace 保留。

重放前完整核对 Guard 来源、Scope/fit/learning/训练 Feature/audit 及冻结协议；不写回、不自动 capture/refit 上游。规则重算只用于核对固定来源，发现差异就拒绝。完整性失败不能变成普通不适用。适用时再启动 pytest；执行后再次审核输入，变化则 stale 并保留运行证据。

新目标语法错误、未支持结构或缺少声明契约产生 skipped_unknown；无法解析目标标识/源文件的配置错误返回 2。pytest exit 1 只有实际失败断言才是 violation；exit 2 的 interrupted 未细分原因时按 execution_error 记录，不能自称已确认 collection error。

`replay verify` 的退出 0 表示记录及当前输入/日志完整性审核通过，不表示 verdict=pass，也不重新执行 pytest。历史 violation/unknown 可完整审核通过；来源已变化的旧记录会拒绝供当前工作使用。

## EvaluationReport 与指标投影（D9）

`evaluation-report.v1` 的 manifest 保存 eval_ 身份、真实开始/完成时间和耗时、protocol/split 引用与摘要、两阶段 fit、四方法 Scope 的实际绑定、运行实现的逐文件及集合摘要、Python/pytest/Pydantic/Typer/平台/超时环境、样本/预测/执行计数、文件摘要、验收结果及失败原因。代码摘要来自当前导入的实现，不对临时目标工作区中的空 src 目录签名。

四方法在相同六个 `(guard_id, sample_id)` 留出行上产生 24 个 Prediction 和 Replay。Prediction 是没有随机 ID/时间/耗时的确定性投影，包含方法、身份、冻结标签、原始作用域决策/trace、verdict、失败 case 和实际 RunOutcome。`replays.jsonl` 保留完整 ReplayResult、引用和真实身份/时间。新增源码缺陷复检保存在 `source-checks.jsonl`，两个学习阶段各两个来源 buggy，共四行，明确不进入留出指标分母。

`evaluation-metrics.v1` 保存 scope-v1-metrics.v1 的公式版本、显式 unknown 政策、每方法的 micro、per_guard、macro_scope 和 macro_end_to_end、自摘要。Ratio 保存 numerator、denominator、value 和 reason；零分母为 null/zero_denominator。Balanced accuracy 的任一项未定义则整体 null，保留两项的 components。macro 对有定义的逐 Guard 指标等权，显式保存 included_guards 和全部 components，不能用 micro 值冒充 macro。input-limit 的留出 Bug recall 分母为 0，macro Bug recall 只纳入 discount。

纯 metrics 与 paired-refinement 只依赖确定性的标签/决策/执行分类，重放时间和随机 ID 不参与；实际 Replay 与 manifest 另有新时间、身份和摘要。两者的确定性不能通过伪造运行时间获得。`report.md` 从同一 metrics/paired JSON 渲染，不能独立改变事实。

`experiment evaluate` 只消费已发布 fit，不重新 capture、compile、audit、fit，不读取 holdout 标签给 learner。来源绑定审核可以纯重算训练规则，但不修改上游产物。新输出目录内保留 Baseline Scope、运行日志、六份报告文件和最后发布的 manifest。发现冻结期望不满足仍发布 accepted=false 和失败原因；中途异常另存 failure.json 与已完成的原始 Replay，不制造缺失行的结果。

重复同一输出目录只做 verify；参数或绑定不同拒绝。目录已有部分产物或失败记录时要求新目录，不覆盖。真正确定性复跑使用新目录并产生新执行，比较 predictions.jsonl、metrics.json、paired-refinement.json 和 report.md 字节；replays/manifest 必须保留各次真实时间。

`experiment verify --run` 逐层审核文件摘要、冻结成员/标签、scope/fit、每份真实 Replay、运行时实现及环境、原始预测和指标重建、配对及验收摘要、Markdown 重建；不执行 pytest。返回 0 表示记录完整，不表示 accepted=true，也不表示每个 Guard 通过。`experiment evaluate` 返回 0 表示冻结实验验收通过，原始报告仍可有真实违规和错误应用；验收未通过返回 1，完整性错误返回 5。
