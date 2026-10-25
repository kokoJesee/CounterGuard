# 数据契约与摘要边界

这一页按格式逐个记录字段语义、摘要边界和重算规则。Schema 是字段定义的最终来源；每个小节解释的是「为什么这样设计」以及「什么时候必须新建产物」。

## 静态接入、runner 收据与 CI 投影

`repository-admission.v2` 保留 v1 的静态 profile、条件和内部的 engineering_prerequisites，新增 `user_guidance`（当前产品支持、用户动作、维护者工作、`eta=null`、跟踪落点），`next_step` 用同样内容提供用户动作。

读取失败时会明确说明尚未分类兼容性；静态候选仍然是 `user_can_enable_verify=false`。旧 v1 报告不补签。

新增 `contract-proposal.v1` 和 `literal-test-projection.v1`：强制未审核、不可执行，绑定 commit、测试 blob/字节、选定函数、目标声明、断言 AST/原行号、带类型的字面量和工具源码。

case ID 来自确定性的语法和参数身份，不含时间、输出路径或 UUID；原断言里已表达和未表达的数量必须一致。这是一种数据提案，不能被当作 contract.v1/v2、Evidence 或 Guard 调度。

上游测试、选定提交、提取语义或工具实现发生变化，就开新的提案目录和摘要。最终契约仍然必须真实出现在 owner head 里，并在受支持的 Docker 捕获/验证链中产生新的 Evidence/Guard。没有给旧 artifact 增加授权。

| 格式 | 新增语义 | 上游变化与重算 |
|---|---|---|
| repository-admission.v1 / minimal-python.v1 | 完整提交树/显式导入根的静态兼容分类；finding 绑定前置与下一步，verify_supported/execution_allowed 固定 false；无运行时间 | 提交/导入根、检查器实现或 scanner Python 变化→新报告。它不作为 Evidence/Guard 授权来源 |
| runner-discovery.v2 | 保留 catalog/review v1 pin；先逐项核对包内 build/attacks 摘要及 image/lock/version/攻击结论，再 image inspect；收据坏则整体退出5 | 发现结果只描述本次本机状态，不复用为授权。catalog/review/构建记录的字节未变，无需重建 runner；新审核语义需新 catalog版本/pin |
| github-summary.v1 | 输入 verify v1/v2 的自摘要、decision/count/exit一致性校验后进行有限字段投影；summary.json 与 Markdown 同源 | 输入 report 变化→新公开目录；投影器变化→新投影。source_report_digest 不是身份/执行认证；不重签原 report |
| github-summary-failure.v1 | 原报告缺失/损坏/超预算时的固定安全失败，exit=5；不含原错误或路径 | 修复后另用新目录，不覆盖失败记录 |

runner 的四份收据以原字节进入包，review 仍固定原规范化摘要；公开 docs 引用只是来源标签，
运行时不联网或从目标仓库读取它。安装包内的 catalog 与所有收据核验是发现/解析的共同前置。
新实现改变全包 .py 摘要：当前源码绑定的 Inspection/授权/仓库 Evidence/Guard 需在新命名空间重物化；
不修改历史记录。本轮真实 CI 验证使用全新可信 fixture 捕获，不把旧 validators 产物补签为当前有效。
冻结 scope_v1 的标注、实现、协议与期望值不变。

## 只读准入报告

`repository-preflight.v1` 是工具生成的静态完整提交树报告，包含 exact commit、逐文件 pins、固定执行 profile、findings/warnings、依赖声明和实际源码摘要；没有执行时间，`execution_allowed=false` / not_run。

`eligible_candidate` 不等于 Inspection.ready，也不等于执行许可。原始 Git 或配置上的不确定性，不能被转换成 applicable 或 inapplicable。

`pilot-manifest.v1` 固定 URL/许可/base/head、完整树、契约提案、配置、阶段收据和准入标准。提案 admitted=false 不是可执行 Guard 契约，也不生成伪 Evidence。`pilot-admission-report.v1` 保存真实生成时间、实际实现版本/摘要、各层检查、逐 Registry Guard 的未判断原因/run=null 和计数；可重复比较的是去时间的 projection_digest。报告 accepted=false 时，两次拒绝一致也不表示 Docker 执行试点通过。源码、冻结输入或 Registry 状态变化需新目录/版本，不重签旧记录。

## Registry 事实与状态

`registry.v1` 是不可变本地身份；`registry-entry.v1` 保存实际登记时间、原工作区与 Guard ref/原始文件 digest、完整 Guard/Evidence 快照及自身摘要。`registry-event.v1` 保存全局 sequence、前驱 digest、Registry/Guard 身份与摘要、registered/disabled、实际 UTC 时间、操作者和原因。首事件无前驱，后续严格连续；disabled 不能复活。

SQLite 逐字节索引规范 JSON，并追加镜像同一事件；每次访问与完整 JSON 事实核对。缺失/损坏/不一致不调度；显式重建只能消费完整合法事实与历史。来源依旧保留在原工作区，运行前重验，不把登记快照当作永久通过证书。首次登记时间真实保留，重复相同 digest 无新事件/时间；相同 ID 不同 digest 拒绝。该存储层不改变 Guard 的 candidate 生命周期字段，亦不改变冻结实验。

本文说明当前持久化接口，字段校验以 `src/counterguard/models.py`、`predicates.py`、`features.py`、`baselines.py`、`protocol.py`、`scope.py` 和 `scope_explanations.py` 为准。JSON Schema 位于 `schemas/`，业务跨字段不变量另由严格模型与 verify 检查。

## 依赖与重算规则

后续统一入口使用 `verify-report.v2`，逐行及顶层绑定 runner review；`runner-catalog.v1` 由安装代码中的完整摘要固定，各 `runner-review.v1` 关联实际构建/隔离复验。修改配置文件并重算自摘要不能自行批准新镜像。新 image/profile 使用新审核记录、目录和代码 pin，不能改写旧收据。

固定仓库重放使用 `docker-execution-authorization.v3`，绑定 review、manifest、Inspection、Guard/Evidence、Scope、Registry 登记/状态事件 tip、请求与最小提交输入 pins。`pilot-manifest.v3` 只增加现有 owner head 历史配置名的显式兼容，不放宽契约来自 head。旧 v1/v2 授权与 v1 报告不改字段；新源码绑定要求新目录重新捕获/物化，不重签历史产物。

统一验证新增 `verify-report.v1` 和 `guard-lifecycle-event.v1`，不改变旧 Registry 事件、Guard、Scope 或冻结协议的字节。生命周期事件依赖登记身份、Guard/Evidence 摘要与前驱事件；状态变更只追加事件，不重新捕获 Evidence。未来持久 Scope 绑定需另开事件版本。

verify 报告依赖 inspection、Registry 登记与事件链快照、逐行 Scope 绑定、执行授权、RunRecord/日志及当前实现摘要。上述任一来源变化都需新输出目录；旧报告不重签。`decision_digest` 绑定规范排序的逐行来源/状态/Scope/执行类别和汇总，排除 RunRecord、运行工作目录、时间与运行 ID；完整 `artifact_digest` 仍绑定所有报告字段。两个摘要用途不同，不把重复运行的完整摘要伪造为相同。详见 [verify](verify.md)。

当前 Evidence 只有 `artifact_digest`，没有 semantic_digest；Guard 才提供语义投影摘要。Feature 也不由 Guard 派生，而是由目标源码、声明契约和独立 module context 派生。纯 learning 依赖训练特征与适用性标签；物化 Scope/fit manifest 再绑定 Guard 和协议来源。这些分支在 Replay 汇合。

| 本层 | 摘要的直接依赖 | 上游变化时必须做什么 |
|---|---|---|
| Contract / source | 原始文件字节；实验 source pin 单独只规范 CRLF | 来源 Evidence 引用改变的文件必须重新 capture；相关目标/声明契约的 Feature 与 audit 重算。冻结实验 source pin 改变不能原地重签，需新协议 |
| Evidence | 契约、测试、buggy/fixed 目标、双向 RunRecord、日志引用摘要、版本/替代链和自身字段 | 任一引用或日志变化则旧 Evidence 验证失败；新 capture 使用新修订，重编译相关 Guard 并审核来源。时间变化或重新捕获也会改变 artifact_digest |
| Guard | artifact：Evidence 关联、完整 Guard 字段、自检与日志；semantic：固定 9 字段执行投影 | Evidence 换修订必须发布新 Guard 身份/版本，不能覆盖原资产。即使 semantic_digest 相同，guard artifact 绑定变化也要求重新物化 Scope/fit manifest；规则本身可复核后复用 |
| Feature / audit | 目标源码、声明契约、module context、自身特征；audit 还依赖样本文件、手工标注、词汇/提取器与快照 | 重提受影响目标并重新审计；context 来源或记录格式变化生成新记录版本。audit 不能靠改标注变绿。相关训练特征/标签变化须重新学习；其他目标变化无需重训无关规则 |
| Learning / Scope / fit | 纯 learning：规范排序的训练 FeatureVector+标签、算法/结果格式；Scope/fit：另绑定训练身份、Guard artifact、protocol/split/context/audit 和创建记录 | 特征、标签、成员或算法变化要重学对应 Guard/phase；仅来源绑定或结果记录格式变化可保留验证后的相同规则，但必须重新物化相关结果/manifest。旧引用不可静默换成新 digest |
| 可选 ScopeExplanation | learning artifact_digest、训练多重集 digest、正负例计数、逐条件删除见证、证书格式 | learning 或训练变化时在新目录重生成证书；该证书是旁路审计产物，不改变已有 Scope/fit/Replay 绑定，也不触发它们重物化 |
| ReplayResult | 实际 Guard、Scope、fit 来源、目标与声明契约/context/Feature、作用域 trace、真实运行及日志 | 任一实际输入绑定变化需新的 replay ID 和记录。已有 skipped/unknown 不可改为 pass；完整性失败须显式拒绝或 stale，不能自动刷新上游后继续冒充旧 replay |
| EvaluationReport | 协议/拆分、冻结标签、全部逐行预测/ReplayResult、指标实现与环境清单 | 重放或度量输入变化须新 evaluation；冻结口径变化用新协议。仅渲染修改可从同一原始 JSON 重生成展示，不重新计算事实 |
| Candidate / VerificationGate | 请求原始字节、白名单 AgentContext、recorded 响应指纹、可信模板测试、fixed 来源以及已验证的双向 Evidence | 请求、响应、契约、目标或模板改变，必须使用新的 request ID/修订和新 candidate/Evidence；历史完成标记只读审核。Gate 是 Evidence 的生成分支，不依赖 Scope，也不自动触发既有 Scope/评测重算 |
| Workspace / Pipeline | 场景与来源/输入镜像原字节、冻结 protocol/split、各阶段正式模型摘要、实际 Replay/JUnit、执行代码与依赖版本 | 任一来源或运行代码变化，历史结果不能在新版本下冒充当前运行。重新运行使用新的 workspace 版本目录；不得重签旧 manifest、复制旧 artifacts 充当新 capture/fit，或修改冻结配置迁就新路径 |
| Command / Demo 展示 | command-report.v1 投影原 JSON；demo-report.v1 另绑定 Pipeline 引用/摘要、demo.py/report.py 原始代码摘要、真实生成时间、规则/逐行展示与自摘要；Markdown 逐字节由该 JSON 渲染 | 只读切换格式无需任何新执行；已发布 Demo 改动/缺失即拒绝，不重新生成缺失文件。新输入/代码使用新 workspace 和 report，不重签旧记录。当前 evaluation/Pipeline 包含 cli.py/report.py 代码 pin，因此本轮展示修改也会使它们在新运行时审核失效；历史记录保留，原提交可复验 |

操作顺序：先定位最早变化层 → 标记其下游现有引用不可用于新工作 → 在新 ID/版本/目录重建必要产物 → 逐层 verify → 最后发布新 Replay/Evaluation。不得通过重新计算旧文件的自摘要来“修复”来源错配。

## 独立验证补强

自摘要和文件摘要只保证被引用的字节一致，不足以保证 JSON 中的执行声明来自这些字节。公开 `verify_evidence`、`verify_guard`、`verify_replay` 现在都调用 `execution.verify_run_record`：检查日志引用留在 workspace 内、三份日志摘要、已知 case 集，再从原始 JUnit 与实际记录的 pytest exit code 重建 outcome/case_results。记录里的未知 case、重签后的假失败集/自检结果均拒绝；timeout/launch error 没有正常返回码时不得伪造 collected cases。此检查不启动进程。

Evidence 同时核对源契约的实际 contract_id，以及 buggy/fixed 的模块、符号、原始源码与声明引用一致。Replay 明确绑定 Guard/Scope 身份、protocol 摘要、执行契约和目标源码身份；已知决策的完整 trace 从真实 FeatureVector 重建，unknown 的 trace/原因从缺失信息或当前提取失败重建。重新签名 trace 或身份字段不能替代这些交叉核对。evaluation/Pipeline 仍保留原整体来源审核，独立入口不再依赖调用者额外补一层审核才能拒绝这些矛盾声明。

没有改变现有持久化模型/Schema、Guard semantic_digest 的九字段集合、特征词汇、learner 搜索或冻结指标。加强的是 verify 接受条件：内部自洽但违背原始来源的记录应拒绝。新增 diagnostics.py 纳入执行代码摘要；CLI 自产错误诊断脱敏和 launch error 摘要收紧会改变新代码/新执行的 artifact 绑定，正式验收使用 verification-smoke 新目录，不重签旧 manifest 或覆盖历史记录。

脱敏只约束明确的公开错误摘要，不改写原始 stdout/stderr/JUnit，也不将原始 RunRecord 或报告包装为公开导出包。具体范围见 `docs/known-limitations.md`。独立 unknown 样例另外保留原 ReplayResult 与同源 CommandReport 的三种展示，不增加标准 Demo 行数或评测分母。

## CLI 与 Demo 展示

`report.py` 定义 `command-report.v1`、`ReplayPresentation`（Schema 文件为 replay-presentation.schema.json，内层行没有独立 schema_version）与三格式纯渲染器。`demo.py` 定义 `demo-report.v1`、`run_demo`、`verify_demo`，复用 Pipeline 管线而不再实现一套执行路径。

显式 `--format text|json|markdown` 都消费同一 CommandReport。payload 保存原完整 JSON，不改变内层 artifact_digest 的覆盖集合；包装层是展示 DTO，不冒充原始 artifact 或新执行证据。capture/compile/learn/evaluate 没有 Replay 时 replays=[]，不虚构适用性结论。既有命令未传 --format 保持原始 JSON 形状，新增 demo 默认 text。命令/别名、退出码和状态表见 `docs/cli.md`。

Replay 行保留 guard_id、可选 sample_id/source_ref、三种 scope_decision、五种 execution_outcome、四种 final_verdict、原始 raw_outcome/raw_verdict、失败 case、错误解释与完整 decision_trace。`RunOutcome.passed/test_failed/timeout` 分别展示 pass/fail/timeout，其余执行异常为 error；没有 RunRecord 是 not_run。原始 pass/violation 分别展示 pass/violation；两类 skipped 展示 skipped，同时保留 unknown 与 inapplicable 区别；异常与 stale 是 inconclusive。stale 可保留实际 pass 执行，但最终仍是 inconclusive，不能读成可信通过。

严格行模型拒绝 skipped 配执行、unknown 无解释、执行错误配 pass/violation；Replay CommandReport 还要与原 payload 的投影完全一致。Demo 的六行、验收、最小失败 case、规则与来源全部从已 verify 的 Pipeline/Guard/Learning/Replay 重建。规则和 trace 是原数据的解释，不新学条件、不重算指标。

Demo 首次在空 workspace 运行；report.md 先发布，report.json 最后作为展示完成标记。中途失败保留已有 Pipeline/文件，重复调用拒绝部分目录，改用新版本目录。report.json 的 digest 覆盖除自身 artifact_digest 外全部字段；Markdown 包含该摘要并要求从同一 JSON 重建逐字节相同，不在 JSON 中再包含 Markdown 摘要造成循环依赖。生成时间使用实际 UTC，重复复验不改时间。命令自身不修改 existing artifact 或冻结协议。

重复 Demo/`demo --verify-only` 先审核 Pipeline 全来源、代码/环境、原始 JUnit，再重建 JSON 事实和 Markdown；不调用 provider、pytest、compile 或 fit。自摘要正确但事实/代码/Markdown 不匹配仍拒绝。输出 ref 相对于源 cwd，内层原 artifact 引用继续遵守 w/ 命名空间。

## 独立 Workspace 与 Pipeline

`pipeline run --scenario examples/demo/mvp.yaml --workspace artifacts/demo-pipeline` 在新目录依次执行 Verification Gate recorded capture → Guard compilation 最小 compile → Scope learning initial/refined fit → Scope-aware Replay refined replay。示例 `.yaml` 内容采用 JSON 形式，当前读取器只接受此子集，使用标准库与现有 Pydantic，不引入通用 YAML 依赖。`pipeline-scenario.v1` 不允许指定新的期待指标或标签；只选择原冻结协议的两份 Guard、两份验证请求和各三个 train sample IDs。

冻结 scope_v1 的 Guard ID、引用路径和 semantic_digest 全部保留。输出目录内的 `w/` 是独立运行 cwd，仅复制显式列举的 protocol/split/context、标注文件、源码/契约、请求/录制响应、场景及必要 package initializer。每个文件保持原始字节并记录 SHA-256；不复制源码仓库中的 artifacts、Git、凭据、缓存、依赖目录或其他文件。新 Gate/Guard/Scope 的同名业务 ID 只存在于新 namespace，与历史产物物理隔离；Guard 执行语义必须再次满足冻结 pin。

`workspace_manifest.json` 的 `InputPin.ref` 相对于来源 cwd，也相对于 `w/`，两侧必须与同一 content_digest 一致。`runtime_ref` 相对于来源 cwd，指向 `<workspace>/w`。workspace 文件集合必须完整且无额外输入，场景本身也被原字节固定。准备前校验冻结来源和完整最长路径预算；不要求原仓库预先具备可用 Guard。原仓库中的过期/损坏 artifact 不作为输入。

`run_manifest.json` 是最后发布的完成标记。其所有 `ArtifactLink.ref` 相对于**来源 cwd**，以 runtime_ref 重定位到独立运行文件；被引用的 Gate/Evidence/Guard/fit/Replay 模型内部引用继续相对于 **w/**。这是两层命名空间，不可把内部 ref 直接当作源仓库路径。所有阶段链接必须留在该运行 namespace 内，并与正式模型的 artifact_digest、身份与来源链一致。

manifest 绑定 workspace、场景、两份 Gate/Evidence/Guard、initial/refined fit/Scope/learning、六份实际 Replay、冻结 protocol/split、实际加载的 runtime 源码及 Python/pytest/Pydantic/Typer 版本。initial 为 7 行训练、refined 为 9 行训练，learner 仍只接收 TrainingExample；静态 feature audit 仍核对冻结 15 行，但 holdout 不进入学习或本次真实重放。

演示三类目标由冻结 train 标签独立决定：源 buggy 正例必须得到 applicable+violation，fixed 正例必须得到 applicable+pass，已确认合法的不适用反例必须得到 inapplicable+not_run。两份 Guard 共六行；标准成功记录包含两次 violation、两次 pass、两次 skipped_inapplicable，真实 Replay 执行四次。CLI 的 0 表示演示验收通过，不能解释为所有被测实现都通过 Guard。skip 保留自身 verdict 和 run=null。

每个执行边界都先审核已完成来源、Gate、Guard、fit/learning 与先前 Replay/JUnit。缺失引用、输入/摘要不一致不继续启动后续阶段。失败保留 `failure.json`、已完成正式 artifact 链接和原始运行日志，且不发布成功完成标记；无效输入/路径在 mkdir/运行前拒绝。失败与未完成目录拒绝自动覆盖/恢复，后续尝试用新版本目录。异常文本不序列化进 failure，保留固定原因/错误类型及真实阶段，避免自由文本或密钥回显。

`pipeline verify <run_manifest.json>` 只读复验所有输入和正式阶段模型，重新解析原始 JUnit 核对执行结果与最小 case 集，重建 manifest 的逐行摘要/验收。调用 Scope 的已有来源审核可以在内存纯重算训练规则，不能发布新 fit、调用 provider 或执行目标。相同 scenario/输出目录的重复 run 走这一路径，保留原 ID、时间、摘要和文件字节。修改 JSON 后重新计算自摘要仍无法伪造接受结论。

## 路径预算

所有新产物写入采用 **240 个 UTF-16 单元**的绝对路径预算，包含最终文件、原子发布临时文件 `.<name>.<32hex>.tmp`、运行配置/日志/JUnit 和 `.pytest_cache/v/cache/lastfailed`。非 BMP 字符按两个单元计数。240 是项目的保守兼容策略；Windows 的传统 MAX_PATH 是 260（含终止字符），启用长路径还依赖系统与应用双方支持，见 [Microsoft 路径限制文档](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation)。不改机器注册表，不依赖本机已经放开限制。

`write_immutable` 在 mkdir 前检查最长临时路径，执行器在创建运行目录/启动 pytest 前检查日志和缓存路径。Replay、Evaluation 和 Verification Gate 进一步预检完整计划布局，避免只写到一半才发现深层路径超限。超过预算返回配置错误，提示缩短输出目录/身份，不自动截断 ID、不重命名历史文件。已有长路径产物可以继续只读审核；这不保证任意未来目录布局都能写入，Gate、Pipeline、Demo 和冻结报告的代表性布局与真正运行前的预检共同防止回归。

路径保护改变了实际执行代码摘要。evaluation 两份已发布报告仍保留原文件，绑定 `b883ca3` 的运行源码；在当前源码下进行环境绑定审核会拒绝旧运行代码摘要。若要做新评测，必须用新目录和真实运行；本轮没有重跑留出集、重签旧报告或改冻结协议。新 Evidence 的身份、生成测试、实际时间和日志都是新记录；已有 Guard/Feature/Scope 的输入与记录格式没有因此改变，无需为了新 Gate 重物化。

## 独立候选与 Verification Gate

`verification-request.v1` 由可信调用方提供 `request_id`、契约路径、buggy/fixed 符号、recorded 响应路径和有限正超时。request ID 用语义修订 `_v1` 等，与开发日程无关；同一 ID/输出目录的重复调用只读审核，任何输入改变、同 ID 的其他请求文件或未完成目录都拒绝覆盖。

Provider 接口只接受严格的 `AgentContext`：契约路径/原始摘要/文本，buggy 的 TargetRef/摘要/源码。fixed 实现、benchmark 标签、目标指标和环境变量不在类型白名单里。业务契约的 expected/raises 是授权 oracle，允许进入上下文；fixed 实现和修复答案不能进入。`RecordedModelClient` 只读指定响应文件，不访问网络、不发现凭据；该类型边界不是 Docker 或操作系统沙箱，Verification Gate 只支持可信本地目标。

`candidate-test.v1` 只有契约摘要与已有 case ID 集合，禁止代码、额外 oracle、Evidence、标签与任意解释字段。候选必须完整覆盖原契约：Evidence capture 审核全部已知 case，不能用少数 case 冒充完整 capture。case IDs 去重检查后排序，20 次乱序生成相同候选与测试摘要。Guard compiler 仍然只选择实际失败 case；Verification Gate 不改它的最小 Guard 规则。新增输入、shrinking 和新 oracle 要走新的契约审核，不由 Agent 直接决定。

候选记录保存真实 UTC 时间、上下文摘要、请求/响应引用与摘要、响应大小、已准入的结构或固定拒绝码。原始未可信响应及 Pydantic 的输入回显不写入产物/日志。recorded 输入限 64 KiB，超限属于输入配置错误；响应无效时固定码为 candidate_schema / contract_digest / case_coverage。响应可能包含敏感内容，源文件由调用方保管，Gate 产物只保留指纹和必要的可信 case IDs。

Gate 从已经严格验证的契约生成 `guard-test.v2` 模板测试，调用原双向 Evidence capture。只有 buggy=`test_failed` 且 fixed=`passed`、来源摘要与输入未变化、失败集非空时，才将真实 Evidence 原字节发布到 `<workspace>/evidence/`。两次运行超时、测试收集/导入错误、buggy 未失败或 fixed 未通过时，Gate=`rejected`、`evidence_ref=null`；仅在候选 runtime 目录保留明确的 diagnostic Evidence 与原始日志，不能当作已验证证据消费。Gate 顶层 `rejection_reasons` 保留具体失败原因。

`verification-gate.v1` 的 `gate.json` 是完成标记，绑定 request、CandidateRecord、fixed pin、可信生成测试、诊断与公开 Evidence。只读 verify 重做候选准入和可信渲染，验证全部引用及双向 Evidence，并从原 JUnit 重建有 exit code 的 outcome/case Results。修改 JSON 后重新算摘要仍不能使其与真实日志矛盾。重复调用不再调用 provider、不启动 pytest、不伪造新的运行时间。退出码：0 verified，2 候选/配置无效，1 未满足双向缺陷条件，3 运行基础设施异常，5 完整性拒绝。

例：feature audit 的 AST 词汇与 15 个特征值没有改变，但 module_group 来源证明增加，导致 FeatureRecord v2 和独立 audit 必须重建，Scope learning fit provenance 必须更新。纯规则在相同训练值下可以一致。Scope-aware Replay 候选计数字段升级同理：改 learning 记录格式与下游引用，不改变已冻结规则或样本真值。

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

增加、删除或改变投影字段必须升级投影规则和协议；不得改 `scope_v1` 的已冻结摘要或 golden 期望来消除失败。当前协议 digest 保持 protocol freeze 的 `sha256:1f401186a3f51c17e582dbbdc96f9324e47e128f90fcb91f29594690bc8daa3a`。

## FeatureVector 与 AST token

FeatureVector 只包含五个标量字段和 `ast_features`。前四项从可信契约元数据取得；`module_group` 从独立、固定摘要的 `benchmarks/context/scope_v1.json` 架构包清单取得；只有 AST 集合从源码生成。目标名称、路径、case、Oracle 和标签均在模型之外。上下文来源及 feature audit 更正见 `module-context-policy.md`。

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

新记录为 `feature-extraction.v2`，外层保存 extractor/vocabulary 版本与摘要、TargetRef、目标原始字节摘要、契约引用与原始字节摘要、module_context_ref/digest、FeatureVector 和自身摘要。旧 v1 形状与摘要兼容读取，但不能用于 Scope learning fit。外层身份/来源不传入学习器。没有生成时间字段，相同输入可得到相同字节；同提取器/context/sample ID 的不同输入不能原地覆盖。

`feature-audit.v2` 报告记录数据文件摘要、独立 module context、每个样本的 expected/actual、AST `missing/unexpected`、标量 `metadata_diff`、来源 feature 引用、快照和摘要。错误行单独保留原因，不伪造 actual。审计不读取适用性、违规或 compliance 标签来提取特征；已公开 holdout 的源码与手工 AST 可以用于对账，不进入 Scope learning 拟合。历史报告与快照追加保留，分歧仲裁见 `feature-adjudication.md`。

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

evaluation 评测层另按冻结计划 §5.3 显式计算：unknown 在主混淆矩阵中属于负预测，同时独立记录 unknown_count、unknown rate 与 decision coverage。原始 Prediction/Replay 仍保留 unknown/skipped_unknown，且 run=null；不把它重命名为 inapplicable，也不调用只接受二元输入的 count_predictions。这个规则是原冻结口径，不是本轮调整标准。

## 可选作用域反例证书

`scope-explanation.v1` 由 `scope_explanations.py` 定义，包含 learner_version、label_basis=`supplied_training_labels`、原 learning_digest、training_dataset_digest、positive_count/negative_count、clause_witnesses 和自摘要。每个 witness 保存对应 ScopeClause 及删除该条件后被纳入的全部去重负例 FeatureVector；按规范 JSON 排序。重复训练行仍计入训练摘要/正负计数，证书只去重展示特征。

单条件规则删除后成为空合取，接受全部负例。多条件见证必须匹配所有其他条件，并被本条件排除；同时被其他条件排除的样本不是本条件的删除见证。严格模型检查这些逻辑不变量，`verify_scope_explanation` 再核对自摘要，并针对原学习和完整训练多重集重建证书，拒绝重新签名的虚假计数/见证。只校验自摘要不足以证明见证属于训练负例。

证书证明条件不可单独删除，不独立证明标签正确、规则泛化或任意语法上的全局最小。纯函数 `explain_scope` 保留 learner 的 feature-only 输入边界；`explain_fitted_scopes` 外层只读审核既有来源/协议/成员/自动特征，再投影训练输入。它不捕获 Evidence、不重训/更新 fit、不调用 pytest；所有组审核通过后才写独立文件。

证书没有执行/创建时间字段，因为它是确定性的派生说明，没有声称发生新执行。其 digest 覆盖全部上述字段（排除自身 artifact_digest），旧 learning/Scope/fit digest 不改变。Schema 为 `schemas/scope-explanation.schema.json`，新物化目录为 `artifacts/analyses/scope-explanations-v1/{initial,refined}/`。

外层 ScopePredicate 与 `fit-manifest.v1` 另外记录实际创建时间、sample ID、Guard artifact digest、protocol/split/context/audit 摘要。首次创建时间真实记录，重复相同输入验证后复用；不伪造时间来制造确定性。不同干净工作区的物化 Scope 摘要可能不同，纯 learning digest 保持一致。

v2 learning 的记录格式改变 artifact_digest，因此新 fit bundle 使用 `fitted/learning-v2/{initial,refined}`，旧 Scope learning 资产不覆盖。新 fit manifest 引用不可变 audit history 文件，不再绑定可被后续审计替换的最新报告副本。

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

## EvaluationReport 与指标投影（evaluation）

`evaluation-report.v1` 的 manifest 保存 eval_ 身份、真实开始/完成时间和耗时、protocol/split 引用与摘要、两阶段 fit、四方法 Scope 的实际绑定、运行实现的逐文件及集合摘要、Python/pytest/Pydantic/Typer/平台/超时环境、样本/预测/执行计数、文件摘要、验收结果及失败原因。代码摘要来自当前导入的实现，不对临时目标工作区中的空 src 目录签名。

四方法在相同六个 `(guard_id, sample_id)` 留出行上产生 24 个 Prediction 和 Replay。Prediction 是没有随机 ID/时间/耗时的确定性投影，包含方法、身份、冻结标签、原始作用域决策/trace、verdict、失败 case 和实际 RunOutcome。`replays.jsonl` 保留完整 ReplayResult、引用和真实身份/时间。新增源码缺陷复检保存在 `source-checks.jsonl`，两个学习阶段各两个来源 buggy，共四行，明确不进入留出指标分母。

`evaluation-metrics.v1` 保存 scope-v1-metrics.v1 的公式版本、显式 unknown 政策、每方法的 micro、per_guard、macro_scope 和 macro_end_to_end、自摘要。Ratio 保存 numerator、denominator、value 和 reason；零分母为 null/zero_denominator。Balanced accuracy 的任一项未定义则整体 null，保留两项的 components。macro 对有定义的逐 Guard 指标等权，显式保存 included_guards 和全部 components，不能用 micro 值冒充 macro。input-limit 的留出 Bug recall 分母为 0，macro Bug recall 只纳入 discount。

纯 metrics 与 paired-refinement 只依赖确定性的标签/决策/执行分类，重放时间和随机 ID 不参与；实际 Replay 与 manifest 另有新时间、身份和摘要。两者的确定性不能通过伪造运行时间获得。`report.md` 从同一 metrics/paired JSON 渲染，不能独立改变事实。

`experiment evaluate` 只消费已发布 fit，不重新 capture、compile、audit、fit，不读取 holdout 标签给 learner。来源绑定审核可以纯重算训练规则，但不修改上游产物。新输出目录内保留 Baseline Scope、运行日志、六份报告文件和最后发布的 manifest。发现冻结期望不满足仍发布 accepted=false 和失败原因；中途异常另存 failure.json 与已完成的原始 Replay，不制造缺失行的结果。

重复同一输出目录只做 verify；参数或绑定不同拒绝。目录已有部分产物或失败记录时要求新目录，不覆盖。真正确定性复跑使用新目录并产生新执行，比较 predictions.jsonl、metrics.json、paired-refinement.json 和 report.md 字节；replays/manifest 必须保留各次真实时间。

`experiment verify --run` 逐层审核文件摘要、冻结成员/标签、scope/fit、每份真实 Replay、运行时实现及环境、原始预测和指标重建、配对及验收摘要、Markdown 重建；不执行 pytest。返回 0 表示记录完整，不表示 accepted=true，也不表示每个 Guard 通过。`experiment evaluate` 返回 0 表示冻结实验验收通过，原始报告仍可有真实违规和错误应用；验收未通过返回 1，完整性错误返回 5。

## 只读检查的配置、Git 快照和报告

三份新 Schema 为 project-config.v1、repository-snapshot.v1、repository-inspection.v1；旧 Schema/冻结 scope_v1 未改。均继承严格 FrozenModel，配置不得加入命令、插件、环境或任意扩展字段。

| 契约/字段 | 类型与语义 |
|---|---|
| ProjectConfig | project_id、唯一 target_id 映射；每项 guard_id/source_ref/symbol/contract_ref，dependency_refs 可空；`module` 对 W3-A 兼容可空，声明时必须由 source_ref 唯一推导，W3-B 授权要求非空；ignored_paths 仅接受逐路径文档、根级仓库元数据和少量 CI 控制文件 |
| config_digest | Digest；实际读取配置原字节 SHA-256，不等于作者/审核者认证 |
| Snapshot.base_commit/head_commit | str 或 null；resolver 仅接受 40 位 SHA-1 commit ID，失败保留能解析的部分 |
| Snapshot.changes | 已验证相对路径、A/M/D/T 和原/新 mode；关闭 rename 猜测，rename 表示 D+A |
| Snapshot.files | base/head、path、Git blob object_id、实际原始内容 SHA-256；只含显式映射文件，无源码正文 |
| Inspection.status / reason_codes | ready/unknown/rejected，原因是固定码，不包含原始 Git stderr；配置无效在构造报告前拒绝 |
| Inspection.targets | target_id/guard_id/source_ref/symbol、affected/unaffected/unknown、changed_inputs、reason_codes；仅文件候选关系 |
| source_selection / mapping_trust | 固定 committed_objects_only / declared_not_semantically_verified；不把声明当作可信语义或 Scope 标签 |
| execution_allowed / execution_outcome | 固定 false / not_run；任何候选也不产生执行许可 |
| implementation_digests / artifact_digest | 实际包全部 .py 源码摘要；报告去自身摘要后的规范化 JSON 摘要 |

读取/影响分析没有时间字段，不虚构时间换确定性。请求修订字符串、选定提交、配置字节、Git/源码版本均相同时，重读逐字节相同；不同 ref 别名即使解析到同一提交，也作为不同请求进入摘要。dirty tree、原 config 或无关新 refs 不作为代码来源。引用在检查期间变化则 unknown；不声称这是 OS 原子快照或防恶意并发恢复。

输入变化时重算：配置字节/声明变化 → 新 Inspection；base/head 解析变化 → 新 Snapshot/Inspection；对象字节/路径边界变化 → 重新审核，损坏/链接拒绝；工具源码/Git 变化 → 新报告及摘要。W3-A 新模块被 CLI 导入，因此已纳入 Evaluation 的运行源码清单，当前版本不能重签旧 evaluation/MVP freeze/MVP manifest 来兼容新代码；历史按原提交保留，新运行另开目录。没有重新执行正式 holdout 或刷新历史评测。

JSON Schema 不能完整表达所有路径/大小限制，运行时校验仍权威。限额、支持布局、已测攻击和 W3-B 未关闭项见 [安全模型](security-model.md)。

## Docker 执行授权

W3-B 新增 `docker-policy.v1` 与 `docker-execution-authorization.v1`；没有修改 `repository-inspection.v1`、RunRecord v1 或任何冻结 scope_v1 文件。

| 契约/字段 | 类型与语义 |
|---|---|
| DockerPolicyV1 | 全字段 Literal 常量；固定网络/IPC、只读、UID/GID、capability、CPU/内存/PID/时间和日志上限，项目配置不能调弱 |
| inspection_digest / config_digest / head_commit | 绑定已复核 Inspection、自身原始配置字节和精确 head；Inspection 仍为 execution_allowed=false |
| input_pins | 目标的 source/contract/dependency 精确路径、Git object ID 和内容 SHA-256，排序且不重复 |
| target / contract / test | 绑定 replay role、contract ID/摘要/路径、TargetRef/摘要、测试路径/摘要、case IDs、timeout 和输出根；target.module 必须与配置和 source_ref 推导值相同 |
| image_digest / policy_digest | 本机实际 Docker image ID 与固定 policy 的规范化摘要；Docker 运行 `--pull=never` |
| artifact_digest | 去自身摘要后的规范化 JSON SHA-256；执行前后仍须从 Inspection、配置、请求和工作区重建，不能只验自摘要 |

任一上游变化都要求重新物化授权：Inspection/工具源码、配置字节、head 输入、Guard 测试、请求字段、policy 或 image ID。执行时只把 input_pins 与 test_ref 的已核对字节物化到新目录并只读挂载，未声明仓库文件不进入容器。RunRecord 保留 v1 形状，Docker 约束和 image ID 进入归一化 argv；授权本身由后续调度/Registry 作为独立来源保存。历史 W3-A 报告没有当前递归源码清单，不能被 W3-B 补签成授权，必须在新 ID/目录重跑 inspect。

## fork 版本（独立于冻结 scope_v1）

设计与范围见 [fork 设计](../integrations/pilot/design-fork-v1.md)。以下是受限 MAC 试点接口，
不是对旧版的隐式字段扩展。旧 Evidence/Guard/Registry JSON 继续按原形状序列化。

| 格式 | 新语义与依赖 |
|---|---|
| project-config.v2 | target.import_root 为 . 或 src；模块必须由根内 source_ref 唯一推导。audit_refs 固定配置/oracle 来源文件，不冒充运行依赖，不允许靠 ignored_paths 隐藏它们。v1 拒绝新字段 |
| contract.v2 | 从固定 F 新增测试静态提取 MAC 的全部 10 case；记录上游提交、测试摘要、35→10 的投影。positional_args 为单个字符串；oracle 只有 is_true / validation_error_instance；返回类模块与类名固定 |
| docker-runner-request.v2 | 仅新增受限 import_root；仍为空 pytest 配置、禁 conftest/插件发现、禁网/只读/非 root/资源上限。响应继续 v1 |
| docker-execution-authorization.v2 | phase、role、assertion_head、target_revision、workspace_ref 分别绑定。捕获目标 B/F、契约 H；自检和重放均为 H。输入 pins、镜像、固定 policy、请求和当前实现共同决定摘要；执行前后重新构造 |
| evidence.v3 | 保存 manifest、契约、生成测试、B/F 提交和工作区、两次 RunRecord/授权引用，以及真实失败 case 和双向复现结论。原始 JUnit 决定结果，基础设施错误不是缺陷 |
| guard.v2 / guard-test.v3 | 只编译 Evidence 实际失败 case；保留位置调用、装饰器以及返回类原语义。绑定 H 自检与原 F 的相同源码字节，独立验证来源和生成测试。旧 trusted-local compile/run 不接受新版仓库 Guard |
| pilot-scope.v1 | basis=audited_exact_snapshot；绑定 Guard、manifest、H、契约、源码和完整运行闭包；不包含学习标签，不声明 learned scope 或跨提交泛化 |
| registry-entry.v2 | 嵌入 guard.v2 + evidence.v3，不能与旧嵌套格式混搭。JSON 事实和状态事件不可变，SQLite 仍只索引；禁用终态和来源重验规则不变 |
| pilot-execution-report.v2 | 逐 Guard 决策/来源/未判断原因及实际 run；其他业务 unknown/disabled 的 run=null。独立审核重建授权、原始 JUnit、Scope 与计数，不能只验自摘要 |
| pilot-repeatability.v2 | 两份执行报告分别独立验证，要求独立 run ID，比较固定 H 的决策/计数投影；真实时间、UUID 和原始日志不改写 |

RunRecord v1 的 cwd="." 相对于**该记录的授权 workspace_ref**，不是验证器进程的 cwd。
新验证器重建请求时以工作区引用提供上下文；不把 cwd 偷换成宿主绝对路径。
授权请求本身绑定本机路径，不能把归档授权冒充另一台机器的新执行授权。

新派生链的重算规则：

| 上游变化 | 必须新建或重算 |
|---|---|
| 上游测试、提取规则、oracle 或调用约定 | 新契约/工具方提交/manifest，重新捕获及所有下游 |
| B/F/H 或任何包依赖字节 | 提交树/Inspection/授权、Evidence、Guard、Scope、Registry 登记、重放与报告 |
| runner/镜像/隔离协议 | 新镜像字节锁和攻击复验，再重新捕获及所有执行下游 |
| 工具实现 | 新当前源码绑定、Inspection 和授权；历史报告保留，不补签。新版捕获用新 ID/目录 |
| Registry 禁用或来源损坏 | 立即拒绝调度；历史报告不覆盖当前状态，不通过索引重建恢复 enabled |
| 只修复工具验证器且上游未变 | 保留原工具方 H，在新 manifest/产物命名空间重新验收；不用再造一个 owner 提交 |

本次 manifest-v3 / validators-fork-v1 是首轮历史；相对 cwd 解释修正后，正式复验使用
manifest-v4 / validators-fork-v2 / evd_validators_mac_complete_v2，该轮因重复来源遍历开销显式中断。
批读取 Git 专项通过后，最终版本为 manifest-v5 / validators-fork-v3 / evd_validators_mac_complete_v3。
前驱 manifest 摘要和重捕获原因逐次显式保存，owner H 始终未变。
实现以递归源码摘要识别；源码 zip 归档同时保存实际 Git 基点和 dirty 状态，
不把未提交源码伪称为某个历史 commit，也不伪造执行时间。

批输出不是无上限的 stdout：先 batch-check 每个大小与原 8 MiB 总预算，
再按预检总字节 + 每条受限头部设定输出上限；每条 body 按长度解析并重算 Git SHA-1，
仍由提交 pins 的 SHA-256 检查内容。空/binary/重复对象、截断、错头、额外字节、错哈希和大小超限均有回归。

## 只读 bootstrap 计划的依赖

`bootstrap-plan.v1` 不是执行链上的契约/Guard。[输入计划](bootstrap-plans.md)的 artifact_digest
覆盖除自身外全部字段：提交与完整文件 pins、显式目标/包根/测试函数、模块级候选闭包及边、
草案 case/unsupported/计数、引导文件的静态观察、原 whole-tree 判断、固定 false 的执行声明、
缺失能力/下一步和当前工具逐文件源码摘要。没有随机 ID、时间、宿主路径或输出目录参与摘要。
固定实现和提交的计划可重复生成到不同新目录；既有目录不覆盖。

提交、目标、包根、测试、闭包算法或工具实现变化时新建计划，保留旧计划。
本层不消费旧 Evidence/Scope，也不回写或重签任何历史执行产物。工具源码变化仍使旧执行链在新验证器下过期；
需要当前执行结论时按上表在新命名空间重物化，不能据本层“只读”豁免源码绑定。

## 通用契约与 B/F/H 绑定

受限根包导出另用 [contract.v5 / bootstrap-binding.v3](static-reexports.md)：新增 definition_module、
definition_symbol、definition_ref，根包与定义路径/内容由 B/F/H 分角色重建。公开入口和完整 runtime_refs 保留；
导出声明、任一角色源码或实现变化需新绑定与下游执行链。旧 v3/v4 契约不扩大接受范围，既有产物不补签。
v5 复用 capture.v2 / Guard v4 的完整契约摘要、生成器 v2 和当前实现约束，不改变执行格式、Scope 算法或冻结协议。

受限 `pytest.raises(..., match=...)` 的新增类型、字段与原版拒绝规则见[消息 oracle](literal-message-oracles.md)。不带 match 的已支持输入保持原契约/生成字节；新字段进入 case ID、projection digest、contract digest，并由当前绑定重建验证。

| 新版本 | 新增依赖与重算范围 |
|---|---|
| contract-proposal.v2 / contract.v4 | 完整字面量 exception_match、原 AST 与新提取器版本；模式改动需新草案/所有者 H/绑定 |
| standalone-capture.v2 | contract.v4 来源与 standalone-test.v2；当前实现改变需新 capture，旧计划不补签 |
| guard.v4 / registry-entry.v4 | Evidence 的实际失败消息 case、standalone-guard-test.v2 及双向自检；重新 compile/register，不覆写历史 |

Docker policy、runner review、RunRecord、Evidence 的来源摘要字段和精确 Scope 算法未扩张；新语义由完整上游契约摘要及新版生成器绑定。源码摘要变化使旧通用链不能借历史“已验证”状态调度，按新 ID 重建所需下游。

`contract.v3` / `standalone-literals.v1` 的[字段与流程](standalone-contracts.md)与固定 validators 的
contract.v2 分开。契约 pin B/F、显式导入映射、闭包 refs、F 内测试 blob/字节/完整投影以及受支持 case；
H SHA 不放入其自身 blob，避免提交内容自引用。H 的新增契约与未改写的 F 文件由绑定器从对象库独立核对。

`contract-preparation.v1` 保存契约字节摘要、B/F 评估、完整 case/unsupported 覆盖和当前实现，固定需人审/不执行。
当前 `bootstrap-binding.v2` 摘要覆盖除自身外所有字段：B/F/H 全树 pins、契约原始摘要与解析值、线性父子规则、
文件来源、每棵树的静态闭包/测试引导观察、完整投影/unsupported、输入状态、固定不执行和 reproduced=null 声明、
语义/身份限制及逐文件工具源码摘要。没有时间、随机 ID、宿主路径或输出位置进入摘要。
独立 verify-binding 重读 Git，重新提取并比较完整记录；自摘要或重签不能代替这个过程。

提交、契约、投影规则、闭包或工具实现变化时在新目录重新 prepare/bind；旧产物不补签。
读取/历史/内容拒绝保存独立 bootstrap-binding-failure.v1，不能被当成已绑定事实。
本层不证明 buggy 真失败，不能进入旧执行器/Registry。v2 删除旧 capture_available 提示，以
capture_entry_point/capture_authority 指向单独的当前来源授权；绑定自身始终不执行，v1 原字节保留且不补签。

## 通用 Docker 双向捕获

[独立捕获](standalone-capture.md)采用新模型/Schema，不复用或扩大旧 Evidence、授权与 Registry 语义。

| 层 / 版本 | 摘要依赖 | 变化后的处理 |
|---|---|---|
| standalone-capture.v1 | Evidence ID、真实 UTC、输出/绑定引用、binding digest、完整 runner review、审核理由及本机权限声明、生成器、超时、实现与 policy | 任一变化需新计划与双向捕获；计划摘要不用于跨运行确定性比较 |
| docker-execution-authorization.v4 | 角色、capture/binding/review/policy/实现摘要、B 或 F 提交、H、精确 image、输入 pins/origins、包根、规范测试摘要、完整请求摘要与 case ID 映射 | 每次执行前后重建；路径/超时/run ID/角色/输入变化不得复用旧授权 |
| RunRecord v1 与原始日志 | 实际 argv、角色/目标/契约、版本、时间、退出码、case 结果、原始 stdout/stderr/JUnit 及摘要 | 源码不重新执行就不能重新制造；独立重建 JUnit 分类并核对封闭 Docker argv，错配即拒绝 |
| evidence.v4 | Evidence ID/真实 UTC、capture/binding/contract、两份运行/授权引用、实际失败集、双向复现/拒绝原因 | 发布前独立重建双方；任何上游变化新建 capture，不重签历史 |

契约 case_<hex> 到运行 case-<hex> 是单射传输映射，授权保存原始 ID→运行 ID；Evidence 使用原始契约 ID。
完整 case 集合必须一致，导入/收集错误不属于 raises oracle，pytest 2/3/4/5、skip/timeout 不能冒充真实失败。
有效执行但未复现仍是 reproduced=false 的事实记录；完整性/前置失败保存 standalone-capture-failure.v1，
保留已完成记录，不留下成功 Evidence。仅最终 Evidence 文件是发布标记，独立核验不能省略。

全包 .py 摘要本轮发生变化，当前执行链需要在新命名空间重做 bind/capture；contract.v3 字节、B/F/H、
Docker policy/入口/审核镜像与 catalog 收据不变时不需改写它们。旧 binding v1 和执行证据保持原样并可能过期。
冻结 scope_v1 的算法、协议、标签、上下文与已有 artifact 均未修改。新 Evidence 通过下述受限新版本进入 Guard/Scope/Registry。

## 独立最小 Guard、快照 Scope 与统一验证

| 层 / 版本 | 必须重建的来源 | 变化后的处理 |
|---|---|---|
| standalone-compilation.v1 | 当前 reproduced Evidence、真实时间、Guard ID、新输出、语义/快照审核理由、实现摘要 | 新源码或 Evidence 变化使用新编译目录，不补签旧计划 |
| guard.v3 | compilation、Evidence、精确失败 case 集、规范最小测试、两次真实 B/F 自检/授权/原始 JUnit、Scope | 所有保留 case 在 B 都必须失败、在 F 都通过；重建后才发布 Guard |
| standalone-snapshot-scope.v1 | Guard ID、Evidence/binding、契约字节、目标/包根、B 与 F 各自完整闭包路径/摘要 | 全组精确匹配，不允许按文件混合；新快照 unknown，非学习规则 |
| Docker authorization v5 | 自检或 Registry replay 目的、角色、当前来源、请求、角色输入 origins/pins、规范测试及 ID 映射、image/review/policy/实现；replay 另绑定 Scope、entry、事件 tip 和 Inspection | 每次执行前后从原始来源重建；自检授权不能用于重放，也不能复用旧 run ID/路径 |
| registry-entry.v3 | 原工作区/仓库、guard 原始字节、完整 Guard/Evidence 值 | 旧 entry v1/v2 形状不变；v3 重新登记，JSON 为权威、SQLite 仅镜像 |
| verify-report.v3 | Inspection、Registry 状态快照、逐 Guard 来源/Scope/真实运行/原因、review、实现、汇总策略 | 仅含新 profile 时使用 v3；JSON/Markdown/公开 Summary 同源，决策摘要排除运行时间/ID等，保留原码优先级 |

Scope 绑定 Guard ID 与 Evidence；Guard 反向绑定 Scope 摘要，避免循环摘要。Candidate/Retired/disabled 不执行，
Shadow 只告警，Active 的适用违规返回 1；unknown、执行故障和完整性失败分别保留 4/3/5。
新 schema 不升级旧对象；工具版本 0.5.0 改变全包源码绑定，应在新目录重新物化需要当前结论的执行链。

单次验证内部只重建一次上游来源事实并传递运行时上下文，不把它持久化为新权威、不跨调用缓存。
每次真正执行前后仍独立加载当前事实，之后的新验证也重新读取；不通过复用旧“已验证”标记省略来源或状态校验。

## 实验性研究重放

[研究重放 v1/v2](research-replay.md)使用独立于生产 Registry replay 的格式与审核。
这两个版本仅用于工具自有 fixture；它们不冻结 scope_v2 的数据、标签、特征、接口分类或实验协议。
严格模型为 [study_models.py](../src/counterguard/study_models.py)，对应 JSON Schema 位于
[schemas/research-v1](../schemas/research-v1/)。旧 parser 不接受新授权/字段。

| 层 / 版本 | 摘要依赖与独立重建 | 上游变化后的处理 |
|---|---|---|
| study-source.v1 | 本机仓库身份摘要、当前 Guard/Evidence/binding、真实 B/F/H、H 契约和最小失败 case；重建日志与自检 | 新来源记录；上游链过期则先用新 ID 重物化，不能重签历史 |
| study-target.v1 | 固定提交的完整树、闭包 pins、导出/钩子/元数据评估、许可文件与导入布局 | 重新读完整 Git 树和评估，再建 target/map/见证/审核与运行 |
| study-call-map.v1 | source/target 摘要、全部最小 case 的断言身份、关键字映射和显式来源控制 | 重建映射及下游；位置参数、值和 oracle 直接来自来源，不接受覆盖字段 |
| study-stdout-witness.v1 | target/map 摘要、目标树内的规范依据 refs、获审子集与 stdout 字面量 | 新见证与审核；不替换来源 oracle、不自动生成合规标签 |
| study-review.v1 | source/target/map/见证、精确 runner review、policy、全包实现、fixture 接口类别、真实 UTC 与先前事件 | 新追加事件；调用方单独更新可信审核摘要。没有自动最新 tip 或签名防回滚 |
| study-replay-plan.v1 / study-admission.v1 | 严格引用、方法/用途/限额；从当前来源和匹配的可信审核摘要计算实际决定 | 方法/输入/代码变化需新准入；learned fit 未接入时仍 unknown |
| Docker authorization v6 | 独立研究用途、source H/target 提交分列、逐文件来源角色、map/review/见证/准入/计划/request/test/image/policy/实现 | 每次执行前后重建，不替代旧生产授权，不能复用 run ID 或运行路径 |
| study-replay.v1 | 实际准入、完整性、原 Run/授权/日志引用、真实时间和运行后核对 | 输出新目录；stale 保留实际 Run；verify 重建当前来源与原始 JUnit，不回写 |

确定性只对规范化输入与决策数据声明；真实审核/运行时间、随机 run ID 和本机身份摘要不会伪造为跨运行相同。
调用方提供的可信审核摘要不从可变计划自动推导；同时控制该摘要、验证器和主机的攻击不在此保证内。
现有 `standalone-snapshot-scope.v1` 与 Candidate/Shadow/Active 的生产权限规则保持原样。

研究静态特征的独立 Schema 见 [study-features.md](study-features.md) 与 `schemas/study-features-v1/`。

| 层 / 版本 | 摘要依赖 | 上游变化与重算 |
|---|---|---|
| study-feature-context.v1 | 精确 source bytes pin、所选函数、可信审核元数据/依据、真实操作者时间；独立保存的 context_anchor | 修改元数据或源码须新 context 与可信 anchor，不能只重签旧记录 |
| study-feature-record.v1 | context/source pin、ast-features.study.v1、独立词汇、parameter-shape.study.v1、逐 token 行见证、全包实现 | 改上游或实现则重新提取与逐字段对账；旧 record 不原地覆盖 |
| study-feature-audit.v1 | 完整 record、独立 expected 向量与其规范摘要、双方差异 | 修改任一侧须新对账；matched 不等于语义正确，不得自动修改另一侧 |

上述静态记录没有 Git/来源执行事实或标签审核权限；它们不能代替 fit/Scope/研究授权。
纯学习仍复用精确 `TrainingExample(FeatureVector, bool)` 与 `conjunction.v1`，不扩大冻结 v1 接受集合。

研究训练专用链见 [study-fit.md](study-fit.md)，新 Schema 独立存于 `schemas/study-fit-v1/`。

| 层 / 版本 | 摘要依赖 | 上游变化与重算 |
|---|---|---|
| study-sample / study-label-review v1 | 固定 StudyTarget、context/audit pins；独立 source/Guard、sample/target、人工标签及提交内规范依据 | 改目标/特征/标签须新样本或审核，重建实际字节，重新冻结成员；不自动裁决语义 |
| study-split / study-fit-protocol v1 | 规范成员、阶段、组/仓库身份/逻辑目标键、留出承诺、source/Guard、算法与预算 | 改任何成员或前置须新 split/protocol 与独立可信 fit review；不读取留出标签 |
| study-fit-review.v1 | protocol/split/source、真实审核事件与全包实现、可选前序事件 | 修改或撤回需新事件/可信 anchor；旧审核不自动适用于新输入/实现 |
| study-fit / study-learned-scope v1 | 实际消费 pins、phase、source/Guard/protocol/split/review、纯学习及 clause 见证、实现 | 改上游须新拟合并独立重建；拒绝结果保留且 Scope 为空；不同结果不覆盖 |

这些记录的 execution_allowed 固定 false，不构成新 Docker 授权或正式外部 scope_v2 冻结。

学习规则的[研究重放 v2](research-fitted-replay.md)采用独立新格式，旧 v1/v6 不接受它。

| 层 / 版本 | 摘要依赖与重建 | 上游变化后的处理 |
|---|---|---|
| study-replay-plan.v2 | 原 source/target/map/见证/审核/方法/限额引用，另列 initial/refined fit 与 query context/audit 引用；无标签或许可字段 | 新输入使用新 plan 与输出，不能把旧 plan 改为 v2 |
| study-review.v2 | 原来源/接口/runner/policy/实现/事件链，加独立拟合审核摘要、两份 fit、query context/audit | 新审核事件及调用方独立保存的执行锚；拟合锚不能自行批准执行 |
| study-admission.v2 | 重建同一协议/来源的两阶段 fit、查询真实定义和对账、两个可信锚；所选 Scope、三态原始 trace/原因 | 任一输入变化重新准入；refusal 为 unknown，不制造空 Scope；查询不消费适用性标签 |
| Docker authorization v7 | 原 v6 的实际执行输入/角色/来源，加拟合审核、两份 fit、context/audit 与所选 Scope 摘要 | 每次运行前后重建全部授权，旧生产/v6 parser 拒绝；inapplicable/unknown 不启动 |
| study-replay.v2 | 原 Run/授权/JUnit、真实运行时间，加新 admission 和独立 fit-review anchor | 新目录保存；独立 verify 重建两个锚与原始运行；运行后漂移保留 Run 并 stale |

本批共享静态定义核验、纯条款 evaluator 和 Docker 重放实现，没有改变 conjunction.v1 或 scope_v1。
全包源码变化令需要当前结论的旧来源/特征/fit/review 链过期，须使用新 ID 重建各层下游；历史字节不改。

## 单独获审的外部快照观察

[外部观察](external-observations.md)使用独立 v3/v8，只接受 B1 和非空独立 stdout 见证。
旧 fixture-only v1/v2/v6/v7 不扩大接受范围；新类型不能携带 fit、训练仓库或语义标签。

| 层 / 版本 | 摘要依赖与独立重建 | 上游变化后的处理 |
|---|---|---|
| study-replay-plan.v3 | source/target/map/非空 witness/review 引用、guard 或 witness lane、B1、限额和封闭外部用途 | 新输入新 plan/目录；不把旧计划改版或借旧审核执行 |
| study-review.v3 | 当前来源 Guard/Evidence/B/F/H、目标全树/闭包、完整映射、独立见证、I/O 类别、runner/policy、全包实现、真实 UTC 与可选前序事件 | 可信本机审核后追加新事件，调用方独立保留返回的摘要；不能从可变计划取得信任 |
| study-admission.v3 | 当前重建事实和独立执行审核锚；execution_policy_not_semantic_label 固定解释 | 上游变化重新准入；撤回为 unknown/run=null，损坏输入拒绝；不能生成适用性或合规标签 |
| Docker authorization v8 | 新用途、完整原 case、source H 与 target 提交分列、逐文件 pins、见证/review/admission/request/test/image/policy/实现 | 执行前后重建；沿用原封闭 Docker 路径，旧 parser 拒绝，不增加环境或本地执行通道 |
| study-replay.v3 | 实际 admission、原始 Run/授权/JUnit、lane、真实时间和运行后核对 | 新目录保存；独立 verify 重建来源与原始日志，运行后漂移保留 Run 并 stale |

见证可以只覆盖获审子集，完整 Guard 的原输入及异常/消息 oracle 不裁剪、不替换。
见证通过只说明该子集观察一致；不能提升为整个 Guard 适用、目标完全合规或研究标签。
源码变化使旧来源链失效时，原获批 H 字节未变可复用 H，在新 ID/目录重新 bind/capture/compile/review/replay；
不需要也不允许靠补签旧记录或新造 owner 提交来规避。冻结 scope_v1、生产生命周期及旧产物保持原样。

## 独立研究快照

[研究快照](research-snapshots.md)采用独立 `research-snapshot-*.v1` Schema，当前用途仅为工具自有 fixture。

| 层 | 摘要依赖与重建 | 上游变化后的处理 |
|---|---|---|
| manifest | 完整 Git commit、所有文件的路径/object ID/内容摘要/大小、收紧后的容量 | 重新读取完整提交；不能删媒体规避限额 |
| contract / binding | B/F 直接父子、H 仅新增工具文件、H 原始契约、F 原测试完整投影、原参数顺序/ID、三角色 manifest/完整包 refs、实现 | 新绑定/审核及全部下游；旧 parser 不接受新类型 |
| review | 独立 execution 或 semantics 类别、固定 fixture 用途、绑定、runner 收据、policy、容量/超时、真实 UTC 和实现 | 新记录和调用方独立保存的新锚；自签记录不能替换可信锚 |
| authorization | 实际绑定/审核锚、目标角色 manifest、完整包与 H 契约 pins、规范生成测试、用途/request/runner/policy/实现 | 每次运行前后重建；不能借给生产/外部用途 |
| evidence | 双向实际 Run、授权、日志、完整原 case 与真实失败子集、绑定/审核/契约 | 重新捕获；异常不当成真实缺陷，旧记录不覆盖 |
| guard / replay | 原 Evidence、恰好失败 case、双向自检、精确 B/F manifest 和原始运行 | 新 ID/目录重新物化；不生成跨项目标签、学习 Scope 或生产调度权 |

源码更新使全包 implementation digest 变化。旧链保留历史事实，不能只改摘要或重签旧审核。

独立比较的[专用类型](snapshot-comparisons.md)另在 `schemas/snapshot-comparison-v1/`：

| 层 | 摘要依赖与重建 | 变化处理 |
|---|---|---|
| target / map | 固定提交完整 manifest/包 refs/入口/许可与接口依据；原 Guard、目标及全部最小 case 的完整摘要 | 重新检查目标和完整映射，不能删/改输入或混用来源 |
| own-witness | 固定目标/map、提交内依据、与原 case 同一输入/身份的独立 oracle | 新 witness 与比较审核；不替换来源 oracle，不生成标签 |
| comparison-review / plan / admission | 独立来源锚、完整来源 Guard/绑定、目标/map/witness、两侧接口依据、runner/policy/超时/实现；计划方法/lane；真实三态决定和原因 | 新审核与调用方独立保存的比较锚；无 fit 的 learned 明确 unknown |
| comparison-authorization / replay | 前述全链、原 H 契约和目标包 pins、规范测试/request/argv、原始日志/JUnit、运行后完整性 | 每次运行前后重建；晚到漂移保留 Run 并 stale，旧 parser 不接受新用途 |

本组不为旧研究 fit 或生产 Registry 增加兼容分支；外部执行与新快照拟合适配仍需独立版本和验收。

## 研究 fixture 的纯指标投影

[纯汇总](study-metrics.md)的新 study-metric-input.v1 / study-metric-summary.v1 复用既有指标公式与预测类型，
增加封闭 fixture 用途、完整四方法成员、固定项目分组、逐项目指标、原配对及四项 delta。
规范行摘要覆盖排序后的全部行（含人工 fixture 标签和项目），结果摘要覆盖全部派生指标及全包实现。
输入/标签/项目/公式/实现变化需新投影；verify 从完整输入重算，不接受重签假计数。
无时间、训练、文件引用授权或目标执行；相同字节输出幂等，不同字节不得覆盖。
它不能证明输入标签语义、真实运行来源、正式协议或研究主结论，也不把外部观察转换为实验矩阵。

## 完整外部快照的独立观察

[独立外部用途](external-snapshot-observations.md)使用新 `external-snapshot-*.v1` 类型；
包范围沿用 source-only-python-snapshot.v1，旧 fixture 的审核/parser/CLI 不扩大接受范围。
中性的 contract/binding 不赋予执行权，外部源仍须重建 H blob 和完整 B/F/H。

| 层 | 摘要依赖与重建 | 上游变化后的处理 |
|---|---|---|
| external source review | 当前 binding、B/F/H LICENSE pin、独立 URL 声明、runner/policy/预算/超时、实现、实际审核时间 | 新审核及调用方独立锚；URL 不证明所有权 |
| authorization / evidence / guard | 新 capture/selfcheck 用途、源审核锚、原 H 契约、包与 request/test pins、原始 Run/JUnit、实际最小失败子集 | 新 ID/目录；不重签旧事实；旧 fixture parser 拒绝 |
| target / map / own-witness | 完整固定目标与 URL/许可/接口依据，整个最小 case 原样调用，独立自身 oracle 和目标提交内依据 | 任一输入变化重建目标、映射、见证及下游；不由观察生成标签 |
| comparison review / plan | 另一可信锚，来源审核/Guard/binding、target/map/witness、B1/lane、runner/policy/实现/超时 | 独立重新审核；withdraw 为 unknown，不能借来源锚自行批准目标 |
| admission / authorization / replay | 两锚与全来源、原契约/目标包、实际 Run/JUnit、晚到变化检查 | 每次运行前后重建；跳过 run=null；晚到漂移保留 Run 并 stale |

本版本只提供 B1 两条观察，不产生学习 Scope、标签、fit、split、正式研究协议或生产 Registry 权限。
全包源码变化使当前使用的旧链过期，须按各层规则新物化；历史字节、冻结 scope_v1 与发布标签保持原样。

## 完整快照的 fixture 训练与评测

[训练接口](snapshot-study-fit.md)和[四方法评测](snapshot-study-evaluation.md)使用独立
`tool_owned_snapshot_study_only` 类型，不扩大旧 fixture 或外部观察 parser。

| 层 | 摘要依赖与独立重建 | 上游变化后的处理 |
|---|---|---|
| source/context/feature/audit | 原 B/F/H、Evidence/Guard/JUnit、完整固定目标、实际定义字节、人工 context 锚与 expected、现有语法 | 来源变化重建 source 及全部下游；目标/context/提取变化重建特征与对账及相应 fit/查询链 |
| split/protocol/label/fit-review | 明确成员/组/仓库与逻辑目标、来源、人工标签及提交内依据、词汇表、实现、独立拟合锚 | 新版本/新审核，不从预测反推标签；holdout 没有可读取路径 |
| fit/scope | 只读取相应训练阶段，全来源/目标/特征/标签重建，原 learner/explanation、条款见证和实现 | 新拟合；refusal 明文保留而非全适用；学习摘要不伪造时间 |
| replay-plan/execution-review/admission | 原 source/target/map 与执行锚、相同两份 fit 及拟合锚、实际查询 context/audit、B2 类别、方法/runner/policy/实现 | 重新审核及准入；查询标签不参与决策；同 Guard 不得逐查询更换 fit/B2 |
| authorization/replay | 全链及实际 request/test/输入 pins、所选 Scope、原始 Run/JUnit 与真实时间 | 执行前后重建；跳过 run=null；变化保留实际运行并 stale；新目录重放 |
| evaluation-plan/query-label/review | 完整四方法与成员、来源/目标身份、人工 fixture 查询标签及原始依据、逐行 fit/执行 pins、独立评测锚和实现 | 全矩阵运行前后核对；任一输入变化另建计划/审核与新输出，不能补签旧矩阵 |
| evaluation/report/export | 原始逐项重放、全矩阵重建、固定公式/分组/配对、独立 unscoped 源自检表和实现 | 从原事实全部重算；损坏/缺行拒绝，部分运行保留 failure；报告导出先 verify |

源自检表不证明 learned Scope 的来源检出率；已知 fixture 查询不是正式留出实验。
该组没有外部标签、训练、生产 Registry 或科学结论授权。
