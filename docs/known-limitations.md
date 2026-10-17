# 当前 MVP 的范围与限制

本文件记录当前可信本地 MVP 的能力边界。打包、安装和正式验收以 [发布说明](release.md) 为准；攻击面覆盖以 [排查清单](attack-surface-checklist.md) 为准。

## 输入和执行

- Python-only、pytest-only，仅支持显式目标及当前契约类型/断言模板。
- mvp.yaml 只接受 JSON 语法这一 YAML 子集；不支持通用 YAML 缩进、注释或锚点。完整内容见 [快速开始](quickstart.md)。
- 标准 Demo 使用录制候选、固定可信模板和本地 fixture，未接入实时模型或任意新 oracle 生成。
- pytest 是可选 runner extra；基础安装缺少它时，Demo/Pipeline 和执行器提前拒绝执行并提示安装，退出 3，不把缺依赖当作测试违规。检查元数据/模块存在不保证任意损坏安装的功能正常。
- 历史 v0.1.0 本机冻结版仍只面向可信本地代码；它不是本 GitHub 仓库发布的 CounterGuard tag。源码版已完成 W3-B runner、W3-C 本地 Registry，以及 validators 固定 MAC 试点。该试点使用专用 pytest 9.0.3/src 配置，只证明固定 B/F/H 快照上的 10 个 MAC case；pytest/容器隔离不是通用 Python 沙箱或结果远程证明。
- 合约/模块 context 是显式确认和审核的元数据，自动 AST 提取不会替代人的语义判断。
- Docker 授权覆盖已审核 replay/capture/compile 路径，以及新增受限字面量契约的双向捕获。任意仓库尚无通用的自动准入、完整依赖证明或自动学习 Scope；不能调用 trusted-local 入口绕过限制。

W3-A 源码版已支持 [只读仓库检查](repository-inspection.md)，v0.1.0 wheel/tag 保持原样。inspect 的 ready / affected 只表示声明的文件映射结果，不审核依赖完整性、符号存在或契约语义，不等于 Scope 判断和执行许可。所有检查结果均为 not_run，`execution_allowed` 在类型和 Schema 上恒为 false；W3-B 使用另一份来源重建授权，不翻转该字段。普通 SHA-1 Git profile 之外的布局/历史缺失保守 unknown，链接/损坏对象拒绝。宿主 Git、Docker daemon/WSL2、TOCTOU、容器内恶意目标干扰 pytest，以及正式 runner 供应链等剩余风险见 [安全模型](security-model.md)。

## 证据能证明什么

本地 Registry 的 enabled 仅表示可继续核验候选，不是 Active 或执行授权；每次使用仍重验原工作区来源，移动/损坏即拒绝。缺索引不自动重建，禁用为终态。Registry 身份角色、签名/防回滚、CI 权限与完整生命周期仍未覆盖，见 [Registry](registry.md)；validators 固定试点的范围见 [W3-D 记录](results/w3d-fork-v1/final-acceptance.json)。

Evidence 要求 buggy 实际断言失败且 fixed 通过；Guard 只保留这次已失败且修复后通过的 case。验证器对引用文件校验摘要，并从原始 JUnit 重建 case 集、结果和执行分类。pytest exit 1 只有完整且准确的断言失败映射才是 violation；2/3/4/5、收集错误、缺失/矛盾 JUnit、timeout 和 launch error 不能冒充缺陷证据。

摘要用于一致性和来源关联，**不是签名或作者身份认证**。能同时改写源码、原始日志、所有关联记录及其摘要的攻击者超出了当前信任边界。验证也不能独立证明创建时间或执行主机身份真实；本机可信工具负责如实记录实际时间。已有产物的时间/ID不会为确定性重写。

单次契约通过不证明程序等价或穷尽正确；最小失败 case 筛选不等于输入 shrinking。Scope 的不可删除条件见证不证明全局最小规则或样本外泛化。当前没有自动接受变异样本、lazy/ICE learner 或自动反例标签推断。

## 实验与 unknown

scope_v1 只有公开的 15 行示例（9 train / 6 holdout）和两族 Guard。它是工程一致性与机制验证，不是盲测，也不足以外推到任意仓库。静态特征 audit 会检查全部 15 行，训练成员与正负标签只来自冻结 train；audit 出现 holdout 身份不等于 learner 使用 holdout。

标准 Demo 的六个训练目标都有完整元数据，因此没有 unknown；独立缺少声明契约的实际 Replay 展示 unknown/not_run/skipped，原因和退出 4 均保留，不加入六行 Demo 或留出分母。unknown 不等于已经确认 inapplicable，也不是通过。

所有历史来源/日志/代码 pin 不可自动刷新；代码或环境变化后的新运行使用新 ID/目录。旧评测、管线和报告的代码绑定只能在其原始源码下复验，不通过重签旧 manifest 冒充当前运行。失败/部分目录不会自动恢复。

## 历史验证结论的边界

**独立来源校验与诊断保护补齐之前的历史 verify 结果，不覆盖下列四类攻击面**：Evidence 重签失败集/来源身份、Guard 自检与原始 JUnit 矛盾、独立 Replay 执行/trace/身份重签，以及公开诊断回显私有路径或显式凭据。

这是按入口限定的保证：旧 Gate/Evaluation/Pipeline 已有部分原始事实重建，不能据此推断旧的每个独立 verify 都具备同样保护；诊断泄漏则属于输出边界，verify 成功本身并不证明报告可公开。四类修复及具体测试见 [A01–A04](attack-surface-checklist.md)。

历史记录只证明“指定代码和输入下，当时的检查通过”。现行验证器因源码绑定拒绝旧产物，不表示已经发现它们被篡改，也不能通过切回旧代码复验就将其升级为当前独立验证保证。目前没有证据表明自己生成的旧产物遭到这些攻击。需要当前保证时，在新 ID/版本目录重新物化可重跑的来源链并记录当前检查；冻结的 holdout 结论保持原版本和覆盖声明，不重跑调参或重签旧 manifest 刷新历史。

## 诊断和公开分享

CLI 自己生成的错误摘要移除显式凭据赋值和绝对路径；启动异常的结构化 error_detail 只保留异常类型。这个规则范围明确，不是通用秘密识别器；Typer 参数校验、任意应用字符串和无上下文秘密值并不由它完整覆盖。

原始 stdout/stderr/JUnit 仍保存原字节和摘要，RunRecord 的解释器 argv、case message、来源代码/契约也可能含本机路径或业务数据。JSON/Markdown 报告是对证据的忠实展示，**不是已经脱敏的公开导出包**。当前将这些本地证据视为私有；公开分享需要另行检查。不能边改写原日志“脱敏”，边继续声称原摘要可复验。

默认不把 API key 环境变量传给子 pytest，录制 AgentContext 也不包含环境、fixed 实现或 benchmark 标签。此边界不声称阻止可信目标主动读取本机文件或自行访问网络。

## W3-D fork 试点的新增边界

本轮接入限定为 validators 的固定 B/F/H 与 MAC 全部 10 个回归 case。
`pilot-scope.v1` 是已审核精确快照绑定，**不是学习作用域**，没有验证跨提交/仓库泛化。
其余 25 个新增区域标识符 case、全仓上游测试、pytest 插件、conftest、自定义安装和其他装饰器仍未覆盖。
元数据 dependencies=[] 不证明所有可选功能和未来执行路径都无需依赖；实际镜像没有安装 crypto extras。

仓库版本最初通过专用 Docker pilot 入口运行；统一 verify 现支持相同固定 owner head/profile。默认 preflight 仍是原 pytest8.4.2/root profile，不自动推断其他项目的 src/pytest9 能力。
不是所有旧 MVP 展示/运行入口都支持新仓库格式，不能通过 trusted-local 模式替代专用入口。
scope_v1 的数据、标签、规则、期望值与发布结论没有被扩展或重算。

H 是仓库所有者在 fork 中单独添加契约与配置的工具方提交，不是上游维护者提交；manifest 区分了两类文件。当前验收记录显示该 head 当时未从远端取得，W4 若需从远程独立复核，仍需发布该提交或提供受信制品传递。没有通过伪装外置契约或在检查器内制造提交来更换执行 head。

首轮相对 cwd 解释错误导致捕获记录被独立验证器拒绝，未发布 Guard；
第二轮完成真实自检，但完整来源复核出现二十多分钟的重复开销，因此显式中断，没有宣称整轮通过。
两轮原始记录、失败/中断说明、原实现源码都保留。最终在第三个命名空间重新验收，
不是把失败记录重签成成功。

Git 读取优化仅合并 blob I/O：先检查大小，再批读并逐个验证 Git 对象哈希。
映射路径/文件数、单 blob 1 MiB、总 blob 8 MiB、5 秒单进程和 30 秒单次读取预算不变；
批输出上限按已预检总字节及受限头部计算，不读取未设上限的数据，不跨复核缓存。
重复来源链复核仍有额外开销，不声称已完成性能优化；耗时应看命令的真实记录，不能只看 pytest 内执行时间。

本机 Windows + Docker Linux 固定 profile 的记录不覆盖其他平台、恶意目标干扰 pytest/JUnit、
daemon/内核漏洞、Git 原生解析器完整资源隔离、上游身份签名或 W4 的 CI 角色/凭据权限。
源码绑定变更后的旧执行授权不是当前实现的凭据；恢复旧源码复验也不能扩大原覆盖范围。

## 统一 verify 的当前边界

`contract draft` 只投影受限测试语法，不运行目标、不证明原测试正确或独立，也不输出可执行契约。
真实 boltons 试走记录的是遇阻时间，未产生 Evidence/Scope/Shadow；完整完成时间仍未知。
预检 v2 的工程前置是维护者责任，用户不能自己设置开关获得通用支持；没有承诺 ETA。

[接入清单](onboarding.md)把首次准备拆为六项人工决策；没有用户实测能支持“30 分钟内接入”或项目覆盖比例。
新 minimal-python 静态检查只分类免安装/免插件候选，不能穷尽动态 Python 行为，也不替代单独的通用 Docker 授权或补齐通用 Guard。
初次没有合法反例时只有经审核的精确快照边界；新的源码版本仍可能频繁 unknown。

[CI Summary](github-actions.md)是有限字段的展示投影，不是通用脱敏器或执行认证。
受控 workflow 没有实际 GitHub 运行记录；它不解决本机绝对路径来源的可携带交付、远程 Active 权限或签名/撤销。
本地真实 Docker 测试通过不能当作 Beta CI/跨平台验收完成。

统一入口支持 `guard.v1` / `project-config.v1` 根布局已审核快照，以及固定 validators owner head 的 `src`/pytest9 profile。同一文件的其他版本、其他项目的依赖闭包和通用学习 Scope 绑定仍为 unknown；没有为推进而降低既有 Docker 或契约来源约束。生命周期是本地追加审阅记录，不提供用户身份、角色、签名或防回滚保证，远程 CI 授权仍未实现。

已审核 runner 的目录随安装包固定摘要，只读发现不会构建、拉取或运行镜像。当前未发布 OCI 镜像仓库或公开离线归档；其他机器仍需取得或重新审核构建产物。没有 Docker/镜像时明确 unavailable，不能用相同 tag 或任意新 ID 代替。

[通用 Docker 捕获](standalone-capture.md)只支持已审核的 source-only 字面量契约与线性 B/F/H。
review_reason 是本机审计文本，不认证用户/所有者，也不证明静态闭包穷尽 Python 动态行为。
它不加载项目 pytest 配置、conftest、插件或原生测试；目标若需要这些能力，不能靠忽略 finding 强行捕获。
容器内恶意目标仍可能干扰 pytest/JUnit，宿主全链重写没有签名保障。新 evidence.v4 仅通过受限[最小 Guard/Scope/Shadow](standalone-guards.md)消费，
不扩展到任意 oracle、装饰器、原生测试或跨版本学习；
工具自有 Docker fixture 的成功不构成第二个外部项目成功或 30 分钟用户接入实测。

新增实现会改变全包源码绑定。已有 Inspection、Docker 授权和仓库 Evidence/Guard 在当前验证器下可能过期；保留其原字节，在新命名空间重新物化，不重签历史记录。冻结 scope_v1 的数据、算法、标签与期望值没有因此改变。详见 [统一验证](verify.md)。
