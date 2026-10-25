# 攻击面排查清单

独立验证、正式 Docker runner 和本地 Registry 都有记录，validators 的固定 manifest-v5 MAC 试点也已完成。这份清单记录已检查的范围和剩余缺口，不是穷尽性的安全认证。

全文分四节：四类缺口是怎么发现的、状态与信任假设、接入检查与 CI 展示的补充边界、开工与准入。

## 四类缺口是怎样发现的

采用的是**沿信任边界检查声明与原始事实是否一致，再用受控篡改证伪**的方法，而非随机发现四个错误后停止：

1. 沿 Capture → Evidence → Guard → Scope → Replay → Evaluation / Gate / Pipeline，列出各公开入口声称验证的事实，以及事实来源：契约/源码、原始 stdout/stderr/JUnit、冻结协议和训练成员。
2. 比较独立 `verify_evidence`、`verify_guard`、`verify_replay` 与外层审核。外层已经重建某项事实，不代表独立入口也检查了它；摘要一致也不代表声明真实。
3. 只在临时副本修改一个声明，重新计算该 JSON 的自摘要，保留原始日志或源码不变，再调用公开验证器。这样能区分“发现摘要不匹配”和“真正发现事实矛盾”。
4. 对诊断边界，用缺失文件的真实 CLI 调用及模拟外部进程启动异常检查输出；只使用合成凭据，分别核对公开摘要和私有原日志。
5. 先观察失败回归，再修实现，最后跑专项和全量；保留原始历史产物。

这是一轮针对来源一致性和失败语义的定向审计。没有完成全仓模糊测试、渗透测试、形式证明或对恶意 OS/并发文件系统的审计；**未发现问题不能解释成没有问题**。

## 状态与信任假设

“已测”仅指表中具体行为有回归或实际记录；“部分”表示存在保护但覆盖不完整；“未测/未实现”不得借用其他行的测试宣称安全。已有全量回归记录包含 552 项测试；本清单新增本身没有产生新的攻击实测。

当前信任本机执行器、解释器、工作区权限和自己准备的目标代码。假设攻击者能修改被校验的记录副本，但不能同时控制可信来源、所有原始日志、验证器及其运行环境。摘要不提供签名或身份认证。直接 `guard run` 是显式目标的 smoke run，不能代替完整来源审核或 Scope 决策。

| ID / 状态 | 边界与已排查行为 | 证据 | 未覆盖的范围 |
|---|---|---|---|
| A01 已测 | Evidence 重签失败 case 集、契约身份或目标模块，原始 JUnit/源码不变时拒绝 | [test_integrity.py](../tests/unit/test_integrity.py) | 同时伪造全部来源；OS 执行真实性、主机和时间认证 |
| A02 已测 | Guard 自检结构化 case 元数据必须与原始 JUnit 一致 | [test_integrity.py](../tests/unit/test_integrity.py) | 任意 Guard 模板/用户 oracle 的正确性；直接运行不等于完整 verify |
| A03 已测 | 独立 Replay 重签执行结果、known/unknown trace、Guard/Scope/protocol/契约/目标身份时拒绝 | [test_full_mvp.py](../tests/e2e/test_full_mvp.py) | 对任意新特征/契约的泛化；并发替换文件的原子快照保证 |
| A04 部分 | CLI 自产错误的绝对路径和显式凭据赋值被隐藏；启动摘要仅含异常类型，原 stderr 保留 | [test_failure_semantics.py](../tests/unit/test_failure_semantics.py)、[diagnostics.py](../src/counterguard/diagnostics.py) | Typer 自身参数错误、无上下文秘密、原日志/argv/业务数据、通用公开导出脱敏 |
| A05 已测 | pytest 1 与 2/3/4/5、收集/import/skip、缺失/歧义 case、timeout/launch 分开；unknown/inapplicable 不启动 pytest | [test_execution.py](../tests/unit/test_execution.py)、[test_replay.py](../tests/integration/test_replay.py)、[真实 unknown](results/w3a-v1/unknown.json) | 恶意进程自报 JUnit、任意子孙进程清理、资源耗尽 |
| A06 已测 | holdout 污染 train、修改标签或重签 split 被拒；learner 只收 FeatureVector，20 次乱序稳定 | [test_holdout_isolation.py](../tests/integration/test_holdout_isolation.py)、[test_scope.py](../tests/unit/test_scope.py) | 人工标签语义真伪、全局最小性、未见仓库表现 |
| A07 部分 | ArtifactRef 拒绝绝对路径、盘符、反斜杠和 `..`；引用 resolve 后检查工作区边界；路径预算含临时文件 | [test_models.py](../tests/unit/test_models.py)、[test_path_limits.py](../tests/unit/test_path_limits.py)、[protocol.py](../src/counterguard/protocol.py) | 未做完整恶意 junction/reparse/hardlink、TOCTOU、ADS/保留名/大小写/Unicode 攻击矩阵；代码检查不等于这些攻击实测 |
| A08 部分 | 同 ID 不同内容拒绝覆盖；完成/部分目录不自动重建；实际时间、代码和环境 pin 保留 | [test_mvp_flow.py](../tests/e2e/test_mvp_flow.py)、[test_demo.py](../tests/e2e/test_demo.py)、[artifacts.py](../src/counterguard/artifacts.py) | 恶意外部写者、权限提升、断电/并发写的完整故障矩阵、签名/撤销/防回滚 |
| A09 部分 | 受控 argv、无 shell、环境 allowlist、空 pytest 配置、禁 conftest 与插件自动发现 | [test_execution.py](../tests/unit/test_execution.py)、[执行策略](pytest-execution-policy.md) | 目标 Python 本身可读写宿主、访问网络；插件隔离不是沙箱 |
| A10 部分 | 声明式候选只引用可信契约 case，非法 Python/空候选拒绝；AgentContext 不含 fixed/标签/环境 | [test_independent_verifier.py](../tests/unit/test_independent_verifier.py)、[test_verification_gate.py](../tests/integration/test_verification_gate.py) | 实时模型、提示注入、任意生成代码、新 oracle 的正确性 |
| A11 部分 | 严格 Schema、JSON 子集、摘要、三格式同源及既有 Markdown 转义案例 | [test_cli_contract.py](../tests/unit/test_cli_contract.py)、[test_demo.py](../tests/e2e/test_demo.py) | 巨量/深层 JSON、恶意 XML 的拒绝服务预算、终端控制字符及全面输出注入检查 |
| W01 固定 profile 已测 | 最小输入挂载、非 root、禁网、只读、CPU/内存/PID/日志/时间、子孙清理；新 pytest9 镜像仍使用同一隔离参数 | [正式 runner 锁定记录](results/w3b-formal-v1/runner-receipt.json)；[新镜像同组四项攻击：4 passed、无 skip](results/w3d-fork-v1/attacks/acceptance.json)，记录绑定实际 image ID 和 lock；[fork 验收](results/w3d-fork-v1/final-acceptance.json) | 正式基础镜像/接受镜像字节锁定已关闭；上游身份签名、内核/daemon 漏洞、跨平台、全面资源攻击与恶意目标干扰 pytest 未覆盖 |
| W02 部分实现 | Git base/head、浅克隆、diff 路径、子模块、Git 配置和仓库链接边界；有界 batch 先检查大小再读取，逐对象校验 Git 哈希，保持路径/总量/超时预算 | [安全模型](security-model.md)；[110 项专项](results/w3d-fork-v1/specialized-tests.txt) 含 Git 历史、受污染环境、二进制/空/重复 blob 和畸形 batch/预算测试；[batch 单元测试](../tests/unit/test_git_batch.py) | 普通受限 profile 可用；不跨复核缓存。worktree 等布局、恶意并发原子性、Git 原生解析器资源隔离与全面 fuzz 未关闭；影响不明仍 unknown |
| W03 受控模式已测，项目兼容部分 | 完整提交树静态预检；显式 project-config.v2 的 src 导入根和锁定 pytest9；契约来自 H，B/F 分别授权；保持 MAC 装饰器、位置参数与固定 ValidationError 类 oracle；旧格式拒绝新授权；Scope/unknown 不伪造 pass | [早期拒绝记录](results/w3d-fork-v1/historical-capture-refusal.json)；[fork 执行验收](results/w3d-fork-v1/final-acceptance.json)、[新回归](../tests/unit/test_repository_pilot.py)：B/F 双向捕获、H 自检及独立重放 | 仅审核 validators 固定 B/F/H 的 10 个 MAC case，精确快照 Scope，不是学习作用域；其余 25 case、全仓测试、任意装饰器/oracle、显式插件/fixture/安装模式、动态依赖证明仍未覆盖；通用 preflight 不自动切换 pilot profile |
| W04 本地 Registry/生命周期已测，整体部分 | 不可变登记/事件 JSON、SQLite 核对、ID 冲突、禁用/退休终态、索引恢复、来源损坏拒绝调度；状态转换追加事件，verify 仅调度 Shadow/Active | [Registry](registry.md)、[原登记专项](results/w3c-v1/registry-tests.txt)、[fork 验收](results/w3d-fork-v1/final-acceptance.json)、[生命周期](../tests/unit/test_lifecycle.py)、[verify](../tests/unit/test_verify.py)；[真实来源链临时副本测试](../tests/integration/test_repository_registry_live.py)两项有显式 manifest 实测，非默认 CI 保证 | 本机操作者只是审计文本；身份角色、签名/防回滚、CI 凭据/上传、公开脱敏与多平台仍未关闭；固定 validators profile 已接入统一 verify，通用学习 Scope 仍未接入 |

## 接入检查与 CI 展示的补充边界

下面按功能列边界，每段对应一次新增能力和它的实测。段首的 `W01/W03` 这类编号只标明这次改动碰到哪条攻击面，不代表当前状态，也不构成新的保证。

### 研究接口

W01/W03 增加[实验性研究重放](research-replay.md)：独立授权 v6 分列 source H 与 target 提交，
保留原契约/oracle，按当前完整来源、映射、可信审核摘要及 runner/policy/code pins 在运行前后核验。
[自有 Docker 专项](../tests/integration/test_study_bridge.py)覆盖两独立 Git 历史、根→src 布局、
重复计数、独立 stdout 见证、import-time ValueError 和 Observer 故障；unknown/inapplicable 的调用数为 0。
源码/重签/晚到变化专项在[慢层](../tests/unit/test_study_replay.py)，字面量与严格字段在[快层](../tests/unit/test_study_models.py)。
W04 只增加独立研究审核事件与外部保留的摘要核对，Candidate 生产权限不提升；本机审核仍非身份认证或自动防回滚。
这不批准 colored 等外部目标，不接入 learned fit/新标签，不扩大生产快照 Scope；原四项 Docker 隔离攻击本批未复跑。
实测计数、真实 CLI 和保留的失败证据摘要见[验收回执](results/research-bridge-v1/README.md)。

W02/W03 增加[只读 RGB 映射审计](results/colored-review-v1/README.md)：全部 8 case 的字面量类型、
前景/背景角色、原消息 oracle 和 source-only 控制逐项核对；30 项专项拒绝删改/重签/自我批准，
20 次乱序语义稳定。该工具只读取现有契约/回执，不启动目标，不认证自摘要回执的来源，不能成为执行授权。
12 文件源码审读和有限谱系观察已记录，维护者裁决仍待完成；4 个越界三元组与 4 个长度错误不合并为合法反例。
W01 没有本批 Docker/隔离实测，W04 没有新增权限或跨仓库调度覆盖；研究桥接仍待单独设计确认与验收。

### 静态导出与来源绑定

W02/W03 增加[显式 static-reexport-v2](static-reexports-v2.md)：contract.v6 / binding.v4 与 closure.v2，
默认 v1 接受范围保留。多个根导出和有限 raise 类钩子必须逐角色独立重建；观察项绑定类与异常定义源码，
模块/条件/别名钩子、危险构造、转发和来源重签仍拒绝或 unknown。
[本次验收](results/static-reexport-v2/README.md)为快速层 976 passed、Git 专项 3 passed、
工具自有 Docker 专项 1 passed（无 skip），覆盖 v6 捕获、最小自检和 Registry 核验。
只读 `inspect-target` 不能成为契约或来源授权；固定 colored 的 12 文件闭包与 3 个钩子为 review_required，
未执行、未分配标签、不计为研究样本。W01 隔离策略未变，未重跑原四项攻击；W04 仍只有原受限来源链覆盖，
没有新增远程权限或跨仓库调度能力。任意 Python 效果、动态改写、完整人工源审与研究桥接仍未关闭。

W02/W03 增加[受限根包导出声明](static-reexports.md)：新 contract.v5 与 binding.v3，原公开入口保持不变，
B/F/H 分角色重建根包/定义摘要。静态专项拒绝条件/动态/重复绑定、定义漂移、未知装饰器和重签输入状态，
确认 unknown 在运输层之前停止、20 次乱序稳定；原版契约不自动获得新接受范围。
本功能[验收](results/static-reexport-v1/README.md)为快层 882 passed、真实 Docker 专项 1 passed、无 skip；
后者只执行工具自有 src 根包 fixture，覆盖双向捕获、最小自检和 Registry 来源核验，未执行 termcolor。
这不关闭任意 Python 效果、所有者身份、插件/安装或远程权限缺口。

随后[termcolor 真实来源验收](results/termcolor-source-v1/README.md)以明确获批契约和真实 owner H 通过三角色绑定、
两轮独立 Docker 捕获、最小 B/F 自检及 Registry 幂等来源核验；外部目标共 6 次 Docker 执行，Candidate 不调度。
它补充 W02/W03/W04 的一个受限外部实例，不扩大原生 pytest、通用导出/依赖、身份或远程 CI 的覆盖声明。

### 最小 Guard、Docker 捕获与运行器

W01/W03/W04 增加[独立最小 Guard 到 Shadow/verify](standalone-guards.md)：新 Guard v3、快照 Scope、
Registry entry v3 与执行授权 v5。每次最小自检/重放均重新核对来源，完整闭包不能混合 B/F；
新快照 unknown 不启动 Docker，候选/退休/禁用不调度，篡改来源即使在退休态也显示完整性失败。
见[单元专项](../tests/unit/test_standalone_guard.py)与[真实 Git/Docker 专项](../tests/integration/test_standalone_bootstrap.py)。
这不关闭 W04 的身份认证、签名/撤销、防回滚和外部贡献远程授权；本机事件不是远程 Active 权限凭据。

W01/W03 新增[受限通用 Docker 捕获](standalone-capture.md)：角色独立来源重建、可信字面量测试、
精确镜像/封闭 policy 与最小输入挂载，禁止本地 fallback。运行前后核对授权，发布 Evidence 前重建双向 JUnit/失败集，
拒绝重签结论、宽松 argv、输入/测试/超时/角色漂移与晚到的宿主输入修改，见[单元测试](../tests/unit/test_standalone_capture.py)。
[真实 Docker 专项](../tests/integration/test_standalone_capture.py)覆盖根/src、重复运行计数、conftest/配置不加载、
收集导入错误不算缺陷；同组四项隔离攻击也已复跑，见[本轮记录](results/standalone-capture-v1/README.md)。
W01 仍仅对已审核镜像/封闭 policy 的列明行为已测，W03 总体仍部分：不兼容任意原生测试/插件/安装。
人工 review_reason 只是可信本机操作记录，不能认证身份或证明恶意目标未干扰 JUnit；W04 仍部分，
新 evidence.v4 已接入上述受限 Guard/Scope/Registry，远程权限未关闭。

W02/W03 增加 [contract.v3 与 B/F/H 来源绑定](standalone-contracts.md)：契约必须读取 H blob，
F 唯一父提交为 B、H 唯一父提交为 F 且只新增契约；case/测试投影/闭包 refs 和完整源 pins 独立重建。
[专项](../tests/unit/test_bootstrap_binding.py)覆盖 H 夹带源码/测试改动、外置/缺失契约、oracle/来源/闭包漂移、
合并/错误父提交、重签执行/复现声明、实现过期、JSON 歧义与发布/读取预算、20 次乱序。
[真实 Git 专项](../tests/integration/test_bootstrap_binding.py)覆盖根与 src、dirty tree 不替代 H、重复绑定及独立重建；
目标包、原测试和 conftest 均带拒绝执行哨兵，未运行。来源核对不认证所有者身份、不证明 oracle/缺陷语义，
来源绑定本身不提供 Docker 捕获或消费旧 Registry 的路径；单独捕获与编译见上。任意项目兼容与 W04 远程权限仍未闭环。

W02/W03 增加[只读 bootstrap 计划](bootstrap-plans.md)：完整提交树 pins 与模块级候选闭包并列，
包初始化、相对/子模块/条件导入、冲突/遮蔽、动态与资源访问提示、配置节观察、20 次乱序及输出不覆盖，
见[单元测试](../tests/unit/test_bootstrap_plan.py)。
[真实 Git 专项](../tests/integration/test_bootstrap_plan.py)中 dirty tree 的依赖和删除的 conftest 均不能替换提交事实；
包/测试/conftest 内的拒绝执行哨兵从未运行。它不是准入授权，不能进入已有 Guard 模型或 Registry，
固定 execution_allowed=false 且 CLI 总是返回 4。Docker policy、catalog 与旧 strict profile 语义未改变。
动态别名、任意副作用/资源和 oracle 独立性仍需审核；任意 Guard/oracle 与上游 pytest 引导仍未覆盖，W03 保持部分。

新增只读契约草案边界见 [contract-drafts.md](contract-drafts.md)。
[单元测试](../tests/unit/test_contract_draft.py)覆盖提交来源 pin、20 次稳定结果、字面量类型、
参数/局部变量与异常名遮蔽、预算、未知 helper/控制流/嵌套调用的拒绝，以及断言覆盖对账。
[真实 Git 专项](../tests/integration/test_contract_draft.py)确认 dirty tree 和 conftest 不会被执行或替代提交断言。
`contract-proposal.v1` 强制需审核/不可执行，旧 Guard 模型拒绝它；没有新增执行授权。
未覆盖任意测试的语义等价、动态模块重绑、fixture/setup 迁移或所有 AST 拒绝服务形态；
语法 import 绑定必须人工审核，完整原测试也没有被宣称可在当前 runner 运行。
一次 [boltons 试走](results/onboarding-boltons-v1/README.md)只证明材料/阻塞与提取实测，
不将未知项目标成可执行，也不扩大现有 W01–W04 的通过范围。

W03 增加[免安装/免插件静态候选检查](preflight.md#免安装免插件候选检查)：完整提交树、
显式包根、依赖/导入、conftest/plugins/fixture 和动态代码的已知形态；仍然不生成执行许可。
[单元测试](../tests/unit/test_admission.py)含 20 次乱序、别名与条件缺项；
[真实 Git 专项](../tests/integration/test_admission.py)检查工作树删除 conftest 不能隐藏提交内容。
任意 Python 的动态依赖/fixture 完备性不由静态分析证明。

W01/W03 增加[包内收据逐项核验](../tests/unit/test_runner_catalog.py)：catalog 仍由可信代码 pin，
build/attacks 缺失、改写、重签或超预算都在 image inspect 前拒绝；未知镜像不能借同名目录获准。
这不是重新执行四项攻击、校验远程签名或防止整个安装包/主机失陷；Docker policy/容器源码未改变。

### CI 投影

W04 的 CI 展示与上传范围已有[有限字段投影测试](../tests/unit/test_github_report.py)、
[workflow 权限/触发/固定上传路径检查](../tests/unit/test_github_workflow.py)及
[本地真实 Docker 驱动专项](../tests/integration/test_ci_fixture.py)。
Shadow/Active/unknown/异常退出策略、JSON/Markdown 计数同源、公开输出不含任意来源文本已覆盖。
模板仅人工触发可信 fixture，不在 .github 下启用；实际 GitHub job、可携带来源/Registry、
远程角色/撤销与宿主可信性仍未关闭。Beta 新增[固定交付模板](../examples/github-actions/counterguard-beta.yml)，
从版本化 Release 核对 wheel、二进制依赖清单和已审核 runner 归档的摘要；
[模板检查](../tests/unit/test_beta_workflow.py)约束权限、来源 pin 与上传范围。
本地安装驱动不能替代实际 GitHub job；公开材料是否已发布以 [Beta 交付说明](beta-release.md)及同版验收记录为准。
W04 整体保持**部分**，不标为全面已测。

## 开工与准入

独立[研究快照](research-snapshots.md)增加工具自有 fixture 范围的检查，原 W01/W03/W04 总体状态均保持**部分**：

- W02/W03：完整 B/F/H 清单和分批容量读取；H 只新增工具文件、原断言/参数完整投影、完整包输入；原 profile 和容量不变。
- W01/W03：执行仅使用原已审核 Docker transport；新增 fixture 检查列于 [Git 专项](../tests/integration/test_snapshot_admission.py)和 [Docker 专项](../tests/integration/test_snapshot_docker.py)。原 pytest 配置/conftest 不加载，不安装依赖，不允许本地 fallback。
- W04：新 Schema 及 fixture-only purpose、执行/语义审核分列、调用方独立可信锚、逐次来源与授权重建；重签记录不能代替锚。没有生产 Registry、Shadow/Active 或外部用途路由。

本轮结果见[自有 fixture 回执](results/research-snapshot-fixture-v1/README.md)。容量/审核通过不证明动态依赖完整、oracle 独立性、仓库所有权或恶意目标未干扰容器内 JUnit；远程认证/签名/撤销、防回滚和原子快照也未因此关闭。未执行 TTE/webcolors，不增加真实研究场景数。

随后[独立比较资格](results/snapshot-comparison-fixture-v1/README.md)增加新 target/map/own-witness/review/plan/admission/authorization/replay：W02/W03 覆盖目标完整提交、全最小 case 原样映射、独立 oracle 不改输入；W01 覆盖原 transport 上的 9 个自有实际容器、跳过真实零启动及迟到修改保留 Run；W04 覆盖来源锚与比较锚分开、错误锚和新旧类型拒绝。见[纯专项](../tests/unit/test_snapshot_comparison.py)、[Git 专项](../tests/integration/test_snapshot_comparison_data.py)与 [Docker 专项](../tests/integration/test_snapshot_comparison_docker.py)。没有重跑原六项 transport 攻击，不新增外部用途、生产权限或标签；三个整体状态仍为部分。

[独立外部完整快照用途](external-snapshot-observations.md)另经[自有 fixture 资格](results/external-snapshot-fixture-v1/README.md)：
W01 复跑网络/写入/环境/时间/内存/PID 六类实际攻击；W03 验证原配置/conftest 隔离、完整包与原最小 case；
W04 验证外部/fixture 的 JSON 与 Python 实例类型分离、源与目标双锚、许可 pin、撤回零启动和晚到变化保留 Run。
本批实际 30 个自有容器（新用途 21、旧用途回归 9），外部执行 0，不产生标签或生产权限。
三个整体状态仍为部分；这份资格不关闭远程身份/签名、最新撤回、防回滚或容器内 JUnit 干扰。

异常消息 oracle 的补充边界见[受限语法](literal-message-oracles.md)与[专项测试](../tests/unit/test_exception_match.py)：扫描不执行模式表达式或编译任意 regex；复杂模式明确 unsupported，旧模型不能忽略消息字段。新捕获/Guard/Registry 版本绑定原始 H 投影，消息修改后重签仍不能调度。该项不扩大 legacy、插件、依赖或 CI 权限支持，W01/W03/W04 的其余未覆盖项保持原状态。

runner 与固定仓库统一入口补充：[两类镜像各四项复验](results/runner-catalog-v1/README.md)，[目录与错误镜像拒绝测试](../tests/unit/test_runner_catalog.py)，[新运行目录授权 v3 测试](../tests/unit/test_repository_verify.py)。新目录由代码 pin，发现仅 inspect、不执行镜像；跨未经审核仓库/布局仍 unknown。真实重复重放的独立来源审核由 [显式 opt-in 专项](../tests/integration/test_repository_verify_live.py) 覆盖，只有提供实际 manifest/两份报告时才运行。

本次 [统一试点验收](results/repository-verify-v1/README.md) 实际提供了新 manifest 与两份真实报告：两次计数/决策摘要一致且 run ID 不同，独立审核 1 passed；完整快速层 605 passed。该实测不把 opt-in 专项升级为默认 CI 保证。

本地生命周期与统一 verify 的补充覆盖：追加状态事件、完整转换矩阵、退休/禁用不复活、重建索引保留状态、重签非法转换拒绝，见 [生命周期测试](../tests/unit/test_lifecycle.py)。[verify 回归](../tests/unit/test_verify.py)覆盖非零前报告、来源损坏、unknown 不执行、执行后禁用保留实际运行与 Shadow/Active 策略；[真实 Git/Docker 专项](../tests/e2e/test_verify.py)检查相同违规的不同阻断策略、独立重复计数及无本地回退。该实现只覆盖已审核原始源码快照，不能扩大 validators profile 或学习 Scope 的范围；操作者认证、角色、签名、防回滚、CI 权限与公开导出仍未关闭。

W01–W04 是未关闭事项，每项 W3 安全边界都必须单独审核，即使 MVP 验收已通过。接入新仓库时，把每项拆成 `docs/security-model.md` 中的可信资产、攻击者能力、实现责任模块、攻击 fixture、预期拒绝和实测记录；新发现的边界追加 ID，不把“未测”改成空白。

固定 profile 的只读检查、正式镜像的同组四项复验和本地 Registry 已有准入记录；这不替代候选仓库/契约/Guard/Scope 的审核。早期 validators 尝试因准入不足而停止，相关拒绝记录仍以历史结果保存，不计为执行通过。

最终 [manifest-v5 验收记录](results/w3d-fork-v1/final-acceptance.json)显示：契约和配置位于 H 的真实提交 blob，上游文件与固定 fork 基线逐字节一致；只读准入、双向 Evidence、最小 Guard 和 Registry 核验通过后，才执行 Docker replay。Inspection.execution_allowed 仍恒为 false；执行能力由独立且逐次重建的 authorization.v2 授予，没有配置布尔开关或本地回退。该结论限于固定快照 MAC 集成，不扩大旧轮次或 scope_v1 的结论。

validators 固定 fork 试点已按全部检查点完成。未来接入其他仓库时仍需各自通过这些前置检查；失败时保留诊断并停止执行，不用可信本地模式绕过。Registry/CI 的身份与权限仍是 W4 的未关闭事项。此流程不改变 scope_v1 的标签、指标或历史验收。

历史“verify 通过”的解释见 [旧验证结论的边界](known-limitations.md#历史结论的边界)。

MVP 冻结补充：A09 的依赖缺失预检由 [test_runner_dependency.py](../tests/unit/test_runner_dependency.py) 和[安装验收](results/mvp-freeze-v1/final-checks.json)覆盖；缺 pytest 元数据或模块时，CLI 给出 runner 安装提示、执行器不启动进程。这不关闭 W01 的未知代码隔离缺口。

### 研究链的补充检查

研究特征的补充检查见[接口说明](study-features.md)与[专项](../tests/unit/test_study_features.py)：
For/GeneratorExp 的词法遮蔽、第一个 iterable 的外层解析、独立条件不拼范围、源码行见证、
原始字节/独立 context anchor 与重签事实重建、AST/字节预算、外层字段不能进入纯 learner、
无负样本拒绝和 20 次乱序稳定均有自有 fixture 覆盖。
静态命令不执行目标代码；手工标注不一致保留双方，不自动改数据。
这不证明可信审核元数据或标签语义、不提供 Git 来源认证、不吸收 helper、不做动态/流敏感分析，
也没有让 learned replay 获得执行权限。W01/W03/W04 的执行、插件和远程权限状态未因此升级。

[训练专用研究链](study-fit.md)新增[纯检查](../tests/unit/test_study_fit.py)、
[完整来源替身专项](../tests/unit/test_study_fit_provenance.py)及[真实 Git 专项](../tests/integration/test_study_fit.py)：
成员/逻辑目标/组和仓库的训练—留出分离、来源组排除、初始不读未来成员、holdout 无文件引用、
原始 source/target/context/audit/规范依据重建、静态导出实际定义、重签一致假学习链拒绝、
无负例的可核验 refusal、20 次乱序、追加撤回、输出限制和旧 parser 拒绝均有自有 fixture 覆盖。
人工分组/标签语义与 own-contract 确认仍是可信审核输入，不提供远程身份、原子快照或外部数据结论。
这不是新的 Docker 攻击实测；没有扩大 C1 或生产执行权限，W01/W03/W04 状态不因此升级。

学习规则通过[独立研究重放 v2](research-fitted-replay.md)接入自有 fixture；
旧 v1/v6 的 learned 行为不变。W01/W03 的增量范围限于新版 v7 授权对拟合/查询事实的绑定、
真实工具自有 Docker 执行及零启动分支；W04 只增加独立拟合锚与执行锚、原事件链和全来源重建。
[来源/篡改专项](../tests/unit/test_study_fitted.py)检查两份 fit/阶段/锚/查询/审核变化拒绝、
输出不能进入训练仓库、运行后变化保留实际 Run；[真实 Git/Docker 专项](../tests/integration/test_study_fitted.py)
检查四方法的原最小 oracle、重复计数、refined 执行、refusal=unknown 与跳过零启动。
范围与实际结果见[回执](results/research-fitted-replay-v1/README.md)。
原四项隔离攻击没有重跑；未执行外部目标、未新增正式研究标签、未提升生产 Candidate 权限。
可信人工语义、谱系、身份/签名/防回滚、原子快照、任意插件/依赖和恶意目标干扰 JUnit 仍未覆盖，
W01/W03/W04 的整体状态仍为部分，不因此声称全面通过。

### 外部观察与真实来源

[colored 只读准入复核](results/colored-readiness-v1/README.md)重新检查固定全树/闭包、原8case映射、
H 原始契约及旧 Evidence 的当前过期拒绝；没有新增执行能力。现有 fixture-only purpose 保持封闭，
没有用外部源码伪造 fixture context 或放宽 FORCE_COLOR/conftest/TTY。
四条可推导见证与四条缺规范的长度输入分开保留，不形成自动标签；35 项既有映射/严格版本检查通过。
这不是新的 W01 隔离攻击实测或 W04 外部授权验收，W01/W03/W04 的整体状态不变。

[单独获审的外部观察 v3/v8](external-observations.md)现增加 W01/W03/W04 的受限覆盖：
只允许 B1、完整原 Guard 和必需的独立 stdout 子集；旧 fixture-only 版本不接受新用途，
拒绝 fit/训练/标签输入，可信执行审核锚与可变计划分离。
来源/映射/见证/审核的同格式重签拒绝，撤回 unknown/run=null 不发现 Docker，晚到变化保留实际 Run 并 stale，
均有[完整来源专项](../tests/unit/test_study_observation.py)；[工具自有真实 Docker 项](../tests/integration/test_study_observation.py)
先验证 8-case/4-witness、宿主环境不转发、本地 executor/import 哨兵、原始 JUnit 及重复独立核验。

[固定 termcolor → colored 实测](results/colored-observation-v1/README.md)随后使用独立外部审核：
来源捕获/自检 4 容器、目标完整 Guard 两次及见证两次共 4 容器，总计 8，没有额外重跑。
它新增一个固定外部观察实例，未提升生产生命周期、未分配研究标签、未冻结正式协议。
原四项隔离攻击本批未重跑；恶意目标干扰 pytest/JUnit、原子快照、任意原生插件/依赖、
远程身份/签名/防回滚及可信主机整体被控制仍未覆盖，W01/W03/W04 整体继续为部分。

[固定 TerminalTextEffects → webcolors 实测](results/tte-webcolors-observation-v1/README.md)使用另一组独立外部快照类型：
H 只增加原六 case 契约，fork Actions 在发布前显式关闭；来源完整树/许可、双审核锚、精确 runner、
全最小 case identity map 和独立自身 oracle 均重建。实际外部容器为来源捕获/自检 4、目标两 lane 重复 4，
共 8；宿主 import 和本地 executor 为 0。两次零容器的编排/网络失败另行保留，没有退额度或改 oracle。
这增加固定外部用途的实测覆盖，但不关闭远程签名、防回滚、最新撤回、并发原子快照或恶意目标干扰 JUnit；
W01/W03/W04 整体仍为部分，也不授予生产 Shadow/Active 权限。

### 训练与评测层

[独立快照训练层](snapshot-study-fit.md)增加 W04 的局部覆盖：完整 fixture 来源重建、源执行/拟合双锚、
严格新用途、固定Git目标、定义绑定/特征对账、训练成员与标签pins、holdout早拒绝及无文件读取入口。
重签/旧类型/子类/撤回/分组交叉/输出逃逸有单元覆盖；[真实来源专项](results/snapshot-study-fit-fixture-v1/README.md)
另完成4个自有Docker容器和原始来源核验，拟合未启动目标。
该层没有四方法快照执行、外部标签或生产调度入口，不增加新的隔离攻击实测；W01/W03/W04整体仍为部分。

[研究纯指标投影](study-metrics.md)只增加完整四方法成员、固定项目分组、unknown/执行故障/空分母、
20 次乱序和合法 Schema 重签后完整重算的算术覆盖；没有新增执行或标签授权。
输入只声明可信人工 fixture 标签，不能证明真实 Run/JUnit 或语义来源。
无 Docker/fit/holdout 读取入口，W01/W03/W04 的执行及远程权限状态不因此升级。

[完整快照四方法桥接](snapshot-study-evaluation.md)增加独立 fixture 用途的执行/拟合/评测锚，
完整N×4成员、逐Guard固定fit/B2、查询标签依据与逐项Run/JUnit重建、三态结果和部分失败留痕。
[单元专项](../tests/unit/test_snapshot_study_evaluation.py)覆盖先审全部标签、变更/撤回拒绝、
重签假计数拒绝和运行后变化保留记录；[实际资格状态](results/snapshot-study-replay-fixture-v1/README.md)
分别记录Docker与快层结果。来源Bug表明确只是unscoped自检，不声称学习后的来源检出保持。
本批不运行外部仓库，不增加真实标签或生产权限，不重跑隔离攻击矩阵；W01/W03/W04整体仍为部分。
